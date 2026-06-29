"""
chat.py 拆分后的辅助函数

- auto_compress_messages 长对话 token 阈值自动摘要
- record_usage 记录 LLM 用量
- fetch_mcp_tools MCP 工具名列表
- fetch_mcp_desc MCP 工具描述(注入 prompt)
- fold_result 命令输出折叠(头/尾保留)
"""
from __future__ import annotations

from typing import Any, Dict, List

from fr_cli.ui.ui import DIM, RESET
from fr_cli.memory.compress import maybe_compress


def auto_compress_messages(state, messages):
    """如果估算 token 超过阈值,对较早对话轮次进行摘要压缩。"""
    threshold = getattr(state, "context_compress_threshold", 4000)
    keep_recent = getattr(state, "context_compress_keep_recent", 5)
    if threshold <= 0 or len(messages) <= keep_recent * 2 + 1:
        return
    # 自适应阈值:不超过模型 token 上限的 60%,避免小上限模型未触发压缩
    limit = getattr(state, "limit", 0) or 0
    effective_threshold = min(threshold, int(limit * 0.6)) if limit > 0 else threshold
    try:
        compressed, did_compress, before, after = maybe_compress(
            messages,
            state.client,
            state.model_name,
            lang=state.lang,
            threshold=effective_threshold,
            keep_recent=keep_recent,
        )
        if did_compress:
            saved = max(0, before - after)
            print(f"{DIM}💡 已压缩早期对话摘要(估算节省约 {saved} tokens){RESET}")
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


def fetch_mcp_tools(mcp_manager) -> List[Dict[str, Any]]:
    """MCP 工具摘要(用于工具列表展示 + intent 判定)。"""
    if not mcp_manager:
        return []
    tools = []
    try:
        servers = getattr(mcp_manager, "servers", None) or {}
        for srv_name, srv in servers.items():
            srv_tools = getattr(srv, "tools", None) or []
            for t in srv_tools:
                name = t.get("name") if isinstance(t, dict) else getattr(t, "name", None)
                if name:
                    tools.append({"server": srv_name, "name": name})
    except Exception:
        return []
    return tools


def fetch_mcp_desc(mcp_manager) -> str:
    """MCP 工具描述,作为附加段落注入 system prompt。"""
    if not mcp_manager:
        return ""
    try:
        servers = getattr(mcp_manager, "servers", None) or {}
        if not servers:
            return ""
        lines = []
        for srv_name, srv in servers.items():
            srv_tools = getattr(srv, "tools", None) or []
            if not srv_tools:
                continue
            lines.append(f"- {srv_name}: " + ", ".join(
                t.get("name") if isinstance(t, dict) else getattr(t, "name", "")
                for t in srv_tools
            ))
        if not lines:
            return ""
        return "\n=== MCP 外部神通 ===\n" + "\n".join(lines)
    except Exception:
        return ""


def fold_result(text: str, max_lines: int = 30, head: int = 15, tail: int = 5) -> str:
    """命令执行结果折叠,头/尾各保留若干行,中间用省略号表示。"""
    if not text:
        return ""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    keep_head = lines[:head]
    keep_tail = lines[-tail:]
    hidden = len(lines) - head - tail
    return "\n".join(keep_head) + f"\n... (省略 {hidden} 行) ...\n" + "\n".join(keep_tail)
