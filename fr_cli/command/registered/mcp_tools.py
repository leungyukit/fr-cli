"""
MCP 工具接入统一注册表 —— 让 AI 能像调内置工具一样调用 MCP 外部神通。

三种调用形态:

1. **动态注册(主路径)** —— 启动时由 AppState 调用 :func:`register_mcp_tools`,
   为每个 enabled MCP server 的每个工具注册一个**独立**注册表工具:
       工具名: ``mcp_<server>_<tool>``   例: ``mcp_filesystem_read_file``
       调用:   ``【调用:mcp_filesystem_read_file({"path": "/tmp/a.txt"})】``
   参数类型由工具的 ``inputSchema.properties`` 推导,
   ``required`` 里的属性登记为注册表必填参数(可选属性仍可透传)。

2. **通用入口(静态注册)** —— :func:`_mcp_tool`(工具名 ``mcp_tool``),
   显式给出 server + tool + arguments, 用于调用未注册/临时新增的工具:
       ``【调用:mcp_tool({"server": "fs", "tool": "read_file", "arguments": {...}})】``

3. **既有通用入口** —— ``mcp_call``(由 agent_data_mcp.py 静态注册,语义同上),
   本模块只在它缺失时补注册,避免覆盖其更严格的 MCP 安全级别。

清理: :func:`unregister_mcp_tools` 移除全部动态注册的 MCP 工具
      (静态工具 mcp_call / mcp_list / mcp_tool 始终保留)。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set

from fr_cli.command.registry import get_registry, register
from fr_cli.core.result import Result
from fr_cli.weapon.mcp.models import _MCP_AVAILABLE, mcp_tool_name

# 动态注册的 MCP 工具前缀
MCP_TOOL_PREFIX = "mcp_"

# 静态注册(非动态)的 MCP 相关工具 —— 清理动态工具时必须保留
PROTECTED_TOOL_NAMES = frozenset({"mcp_call", "mcp_list", "mcp_tool"})

# JSON Schema 类型 → Python 类型
SCHEMA_TYPES: Dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


# ------------------------------------------------------------------
# 参数推导
# ------------------------------------------------------------------

def schema_params(schema: Any) -> Dict[str, Any]:
    """从 inputSchema 推导注册表 params。

    注册表把 params 里的每个键都视为**必填**(dispatch 会拒绝缺失参数),
    因此这里只登记 ``required`` 里的属性;可选属性调用时若提供,
    handler 会一并转发给 MCP server。

    Args:
        schema: 工具的 inputSchema(dict)

    Returns:
        ``{参数名: Python 类型}``
    """
    if not isinstance(schema, dict):
        return {}
    props = schema.get("properties")
    if not isinstance(props, dict) or not props:
        return {}
    required = schema.get("required")
    required_set: Set[str] = set(required) if isinstance(required, (list, tuple, set)) else set()
    params: Dict[str, Any] = {}
    for pname, pdef in props.items():
        if pname not in required_set:
            continue
        ptype = str
        if isinstance(pdef, dict):
            ptype = SCHEMA_TYPES.get(str(pdef.get("type") or "string").lower(), str)
        params[pname] = ptype
    return params


def schema_arg_keys(schema: Any) -> Set[str]:
    """取出 inputSchema 里声明的属性名(用于区分控制参数与业务参数)。"""
    if not isinstance(schema, dict):
        return set()
    props = schema.get("properties")
    if not isinstance(props, dict):
        return set()
    return set(props.keys())


def _extract_arguments(kwargs: Dict[str, Any], allowed: Optional[Set[str]] = None) -> Dict[str, Any]:
    """从 kwargs 中提取 MCP 工具参数。

    - 显式 ``arguments``(dict 或 JSON 字符串)优先
    - 其余平铺参数(模型直接散传)按 schema 白名单合并进来
    """
    arguments: Dict[str, Any] = {}
    raw = kwargs.get("arguments")
    if raw is not None and not (allowed and "arguments" in allowed):
        if isinstance(raw, dict):
            arguments.update(raw)
        elif isinstance(raw, str) and raw.strip():
            try:
                parsed = json.loads(raw)
            except (ValueError, TypeError):
                parsed = None
            if isinstance(parsed, dict):
                arguments.update(parsed)
    for key, value in kwargs.items():
        if key in ("server", "tool", "arguments") and not (allowed and key in allowed):
            continue
        if allowed is not None and key not in allowed:
            continue
        arguments[key] = value
    return arguments


# ------------------------------------------------------------------
# Handler
# ------------------------------------------------------------------

def make_mcp_handler(server_name: str, tool_name: str,
                     allowed: Optional[Set[str]] = None,
                     prefer_explicit: bool = False):
    """生成 MCP 工具的调用 handler(闭包绑定 server / tool)。

    Args:
        server_name: 绑定的 MCP 服务器名(通用入口传空串)
        tool_name: 绑定的 MCP 工具名(通用入口传空串)
        allowed: 该工具 inputSchema 声明的属性名(白名单);None 表示不限制
        prefer_explicit: 是否优先使用调用方显式传入的 server / tool
            (通用入口为 True;按工具注册的为 False —— 工具名已绑定 server/tool)

    Returns:
        ``handler(deps, **kwargs) -> Result``
    """

    def handler(deps, **kwargs):
        manager = getattr(deps, "mcp", None)
        if manager is None:
            return Result.fail("MCP 管理器未初始化")
        if not _MCP_AVAILABLE:
            return Result.fail("MCP SDK 未安装,请执行: pip install mcp")

        server = server_name
        tool = tool_name
        if prefer_explicit:
            server = kwargs.get("server") or server_name
            tool = kwargs.get("tool") or tool_name
        if not server or not tool:
            return Result.fail("MCP 调用缺少 server 或 tool")

        arguments = _extract_arguments(kwargs, allowed)
        try:
            result, err = manager.call_tool_sync(server, tool, arguments)
        except Exception as e:
            return Result.fail(f"MCP 调用失败: {e}")
        return Result.from_tuple(result, err)

    handler.__name__ = f"mcp_{server_name or 'any'}_{tool_name or 'any'}"
    return handler


# ------------------------------------------------------------------
# 静态注册:通用入口
# ------------------------------------------------------------------

@register(
    name="mcp_tool",
    description="调用 MCP 外部神通工具(通用入口: server + tool + arguments)",
    params={"server": str, "tool": str, "arguments": dict},
    security="sec_exec",
    aliases=["/mcp_tool"],
)
def _mcp_tool(deps, **kwargs):
    """通用 MCP 调用入口(不依赖启动时的工具发现结果)。"""
    handler = make_mcp_handler("", "", None, prefer_explicit=True)
    return handler(deps, **kwargs)


# ------------------------------------------------------------------
# 动态注册:逐个 MCP 工具
# ------------------------------------------------------------------

def register_mcp_tools(mcp_manager) -> int:
    """把 MCP 工具注册进统一注册表。

    - 先清理上一轮动态注册的 ``mcp_`` 工具(静态工具保留),避免重复累积
    - 为每个 enabled server 的每个工具注册独立工具 ``mcp_<server>_<tool>``
    - 确保通用入口 ``mcp_call`` 存在(已存在则保留原有安全级别)

    Args:
        mcp_manager: MCPServerManager 实例(可为 None)

    Returns:
        本次注册的 MCP 工具数量
    """
    registry = get_registry()
    # 清理旧的动态工具(保留静态注册的 MCP 工具)
    registry.unregister_prefix(MCP_TOOL_PREFIX, exclude=PROTECTED_TOOL_NAMES)

    if not mcp_manager:
        return 0
    try:
        tools = mcp_manager.list_all_tools() or []
    except Exception:
        tools = []

    count = 0
    for t in tools:
        if not isinstance(t, dict) or t.get("_error"):
            continue
        server = str(t.get("server") or "")
        tool_name = str(t.get("name") or "")
        if not tool_name:
            continue
        schema = t.get("inputSchema") or {}
        params = schema_params(schema)
        allowed = schema_arg_keys(schema)
        handler = make_mcp_handler(server, tool_name, allowed, prefer_explicit=False)
        name = mcp_tool_name(server, tool_name)
        desc = t.get("description") or tool_name
        registry.register(
            name=name,
            description=f"[MCP:{server}] {desc}",
            params=params,
            security="sec_exec",
            aliases=[f"/{name}"],
        )(handler)
        count += 1

    _ensure_generic_dispatcher(registry)
    return count


def _ensure_generic_dispatcher(registry) -> bool:
    """确保通用入口 ``mcp_call`` 存在。

    已有静态注册(agent_data_mcp.py,安全级别 sec_mcp_call)时保持不变 ——
    不覆盖更严格的 MCP 专属安全类别。

    Returns:
        本次是否补注册了 mcp_call
    """
    names = {t.get("name") for t in registry.get_tools()}
    if "mcp_call" in names:
        return False
    registry.register(
        name="mcp_call",
        description="调用指定 MCP 服务器的工具(server + tool + arguments)",
        params={"server": str, "tool": str, "arguments": dict},
        security="sec_exec",
        aliases=["/mcp_call"],
    )(make_mcp_handler("", "", None, prefer_explicit=True))
    return True


def unregister_mcp_tools() -> int:
    """清理动态注册的 MCP 工具(静态 MCP 工具保留)。

    Returns:
        被清理的工具数量
    """
    registry = get_registry()
    removed = registry.unregister_prefix(MCP_TOOL_PREFIX, exclude=PROTECTED_TOOL_NAMES)
    return len(removed)


def list_mcp_tools() -> List[str]:
    """列出当前注册表里的 MCP 工具名(含静态入口)。"""
    registry = get_registry()
    return sorted(
        t.get("name") for t in registry.get_tools()
        if str(t.get("name", "")).startswith(MCP_TOOL_PREFIX)
    )
