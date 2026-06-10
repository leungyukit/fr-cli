"""命令处理器 —— mcp"""

import json
from fr_cli.command.registry import register

@register(
    name="mcp_list",
    description="列出已配置的 MCP 服务器及其可用工具",
    params={},
    aliases=["/mcp_list"],
)
def _mcp_list(deps, **kwargs):
    mcp = getattr(deps, "mcp", None)
    if not mcp:
        return None, "MCP 管理器未初始化"
    servers = mcp.list_servers()
    if not servers:
        return "暂无 MCP 服务器配置。", None
    lines = ["📡 MCP 服务器列表:"]
    for s in servers:
        status = f"{GREEN}● 启用{RESET}" if s.get("enabled", True) else f"{RED}● 禁用{RESET}"
        lines.append(f"  [{s['name']}] {status} | 传输: {s.get('transport', 'stdio')} | 命令: {s.get('command', 'N/A')}")
    return "\n".join(lines), None


@register(
    name="mcp_call",
    description="调用指定 MCP 服务器的工具",
    params={"server": str, "tool": str, "arguments": dict},
    aliases=["/mcp_call"],
)
def _mcp_call(deps, **kwargs):
    mcp = getattr(deps, "mcp", None)
    if not mcp:
        return None, "MCP 管理器未初始化"
    server = kwargs.get("server", "")
    tool = kwargs.get("tool", "")
    arguments = kwargs.get("arguments", {})
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except Exception:
            arguments = {}
    result, err = mcp.call_tool_sync(server, tool, arguments)
    return (result, None) if not err else (None, err)

