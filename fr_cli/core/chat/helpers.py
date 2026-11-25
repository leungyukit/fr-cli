"""
chat.py 拆分后的辅助函数

- auto_compress_messages 长对话 token 阈值自动摘要
- record_usage 记录 LLM 用量
- fetch_mcp_tools MCP 工具摘要(含 description / inputSchema)
- fetch_mcp_desc MCP 工具描述 + 参数 schema(注入 prompt)
- fold_result 命令输出折叠(头/尾保留)
"""
from __future__ import annotations

from typing import Any, Dict, List

from fr_cli.ui.ui import DIM, RESET, print_styled
from fr_cli.memory.compress import maybe_compress
from fr_cli.weapon.mcp.models import mcp_tool_name


def auto_compress_messages(state, messages):
    """如果估算 token 超过阈值,对较早对话轮次进行摘要压缩。"""
    threshold = getattr(state, "context_compress_threshold", 4000)
    keep_recent = getattr(state, "context_compress_keep_recent", 5)
    if threshold <= 0 or len(messages) <= keep_recent * 2 + 1:
        return
    # 自适应阈值:不超过模型 token 上限的 60%,避免小上限模型未触发压缩
    limit = getattr(state, "limit", 0) or 0
    effective_threshold = min(threshold, int(limit * 0.6)) if limit > 0 else threshold
    # v2.8.7(P1-5):分层摘要段数(1 = 单段合并的旧行为)
    tiers = getattr(state, "context_compress_tiers", 3)
    try:
        compressed, did_compress, before, after = maybe_compress(
            messages,
            state.client,
            state.model_name,
            lang=state.lang,
            threshold=effective_threshold,
            keep_recent=keep_recent,
            tiers=tiers,
        )
        if did_compress:
            saved = max(0, before - after)
            print_styled(f"{DIM}已压缩早期对话摘要(估算节省约 {saved} tokens){RESET}")
            messages[:] = compressed
    except Exception:
        pass


def record_usage(state, usage):
    """记录 LLM 单次调用的 token 用量 + 估算费用。"""
    try:
        from fr_cli.core.usage import UsageTracker
        tracker = getattr(state, "usage", None)
        if tracker is None:
            tracker = UsageTracker()
            state.usage = tracker
        provider = getattr(state, "provider", "") or ""
        tracker.record(
            provider=provider,
            model=getattr(state, "model_name", "") or "",
            usage=usage,
        )
    except Exception:
        pass


def _normalize_mcp_tool(server_name: str, tool: Any) -> Dict[str, Any]:
    """把 MCP 工具条目归一化成统一结构。

    兼容 dict 与对象两种形态(MCP SDK 返回对象,内部缓存用 dict)。
    """
    if isinstance(tool, dict):
        name = tool.get("name") or ""
        desc = tool.get("description") or ""
        schema = tool.get("inputSchema") or tool.get("input_schema") or {}
        server = tool.get("server") or server_name or ""
    else:
        name = getattr(tool, "name", "") or ""
        desc = getattr(tool, "description", "") or ""
        schema = getattr(tool, "inputSchema", None) or {}
        server = server_name or ""
    if not isinstance(schema, dict):
        schema = {}
    return {
        "server": str(server),
        "name": str(name),
        "description": str(desc),
        "inputSchema": schema,
    }


def _collect_mcp_tools(mcp_manager) -> List[Dict[str, Any]]:
    """收集所有 MCP 工具(含 description 与 inputSchema)。

    优先使用 server 对象上已挂载的 tools(内存态,零成本);
    否则回落到 ``manager.list_all_tools()``(内部带 TTL 缓存,不会反复建连)。
    """
    if not mcp_manager:
        return []
    try:
        servers = getattr(mcp_manager, "servers", None) or {}
    except Exception:
        return []

    tools: List[Dict[str, Any]] = []
    for srv_name, srv in (servers or {}).items():
        try:
            srv_tools = getattr(srv, "tools", None) or []
        except Exception:
            srv_tools = []
        for t in srv_tools:
            item = _normalize_mcp_tool(srv_name, t)
            if item["name"]:
                tools.append(item)
    if tools:
        return tools

    # 回落:实时发现(带缓存)
    # 优先用**只读缓存**的 peek_tools —— system prompt 组装是热路径,
    # MCP server 可能不可达, 实时发现会阻塞最多 tool_fetch_timeout 秒。
    # 缓存由启动时的后台预热填充。
    lister = getattr(mcp_manager, "peek_tools", None)
    if not callable(lister):
        lister = getattr(mcp_manager, "list_all_tools", None)
    if not callable(lister):
        return tools
    try:
        for t in lister() or []:
            item = _normalize_mcp_tool("", t)
            if item["name"]:
                tools.append(item)
    except Exception:
        return tools
    return tools


def _describe_schema_params(schema: Dict[str, Any]) -> str:
    """把 inputSchema 转成参数说明文本。

    格式: ``path(string, 必填), content(string, 可选)``
    schema 为空(无 properties)时返回空串。
    """
    if not isinstance(schema, dict):
        return ""
    props = schema.get("properties")
    if not isinstance(props, dict) or not props:
        return ""
    required = schema.get("required")
    required_set = set(required) if isinstance(required, (list, tuple, set)) else set()
    items = []
    for pname, pdef in props.items():
        ptype = "string"
        if isinstance(pdef, dict):
            ptype = str(pdef.get("type") or "string")
        mark = "必填" if pname in required_set else "可选"
        items.append(f"{pname}({ptype}, {mark})")
    return ", ".join(items)


def fetch_mcp_tools(mcp_manager) -> List[Dict[str, Any]]:
    """MCP 工具摘要(用于工具列表展示 + intent 判定)。

    返回结构向后兼容: ``[{"server", "name"}]``,
    并新增 ``description`` 与 ``inputSchema`` 两个字段。
    """
    if not mcp_manager:
        return []
    try:
        return _collect_mcp_tools(mcp_manager)
    except Exception:
        return []


def fetch_mcp_desc(mcp_manager) -> str:
    """MCP 工具描述,作为附加段落注入 system prompt。

    每个工具一段,带完整参数 schema(类型 + 必填标记)与可调用名:
        - server/tool: 描述
            参数: path(string, 必填), content(string, 可选)
            调用: 【调用:mcp_server_tool({...})】
    schema 为空时只输出工具名。
    """
    if not mcp_manager:
        return ""
    try:
        servers = getattr(mcp_manager, "servers", None) or {}
        if not servers:
            return ""
        tools = _collect_mcp_tools(mcp_manager)
        if not tools:
            return ""
        lines = []
        for t in tools:
            server = t.get("server") or ""
            name = t.get("name") or ""
            if not name:
                continue
            desc = t.get("description") or ""
            lines.append(f"- {server}/{name}: {desc}" if desc else f"- {server}/{name}")
            params = _describe_schema_params(t.get("inputSchema") or {})
            if params:
                lines.append(f"    参数: {params}")
            lines.append(f"    调用: 【调用：{mcp_tool_name(server, name)}({{...}})】")
        if not lines:
            return ""
        return "\n=== MCP 外部神通 ===\n" + "\n".join(lines)
    except Exception:
        return ""


def fold_result(text: str, max_lines: int = 30, head: int = 15, tail: int = 5) -> str:
    """命令执行结果折叠,头/尾各保留若干行,中间用省略号表示。

    v2.8.7(UX)：被省略的内容不再**直接丢弃** —— 登记到
    ``fr_cli/core/collapse.py``，REPL 里按 Ctrl+O 可以原样展开。
    """
    if not text:
        return ""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    keep_head = lines[:head]
    keep_tail = lines[-tail:]
    hidden = lines[head:len(lines) - tail]
    try:
        from fr_cli.core.collapse import register
        register("\n".join(hidden), meta=f"命令输出 {len(hidden)} 行")
    except Exception:
        pass
    return "\n".join(keep_head) + f"\n... (省略 {len(hidden)} 行, Ctrl+O 展开) ...\n" + "\n".join(keep_tail)
