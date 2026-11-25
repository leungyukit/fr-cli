"""
MCP 模型与可用性标志

包含:
- MCPServer dataclass(单个 MCP 服务器配置)
- _MCP_AVAILABLE / _STREAMABLE_HTTP_AVAILABLE / _SSE_AVAILABLE 全局标志

模块拆分:
- fr_cli.weapon.mcp.models  本文件(MCPServer + SDK 可用性)
- fr_cli.weapon.mcp.manager  MCPServerManager 类
- fr_cli.weapon.mcp          re-export
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional


def mcp_tool_name(server: str, tool: str) -> str:
    """生成 MCP 工具在统一注册表中的工具名: ``mcp_<server>_<tool>``。

    server / tool 名里的非字母数字字符统一替换为下划线,
    保证生成的工具名是合法标识符。

    Args:
        server: MCP 服务器名
        tool: MCP 工具名

    Returns:
        规范化后的注册表工具名(如 ``mcp_filesystem_read_file``)
    """

    def _clean(value: str) -> str:
        cleaned = re.sub(r"[^0-9a-zA-Z_]+", "_", str(value or "")).strip("_")
        return cleaned or "unknown"

    return f"mcp_{_clean(server)}_{_clean(tool)}"


@dataclass
class MCPServer:
    """MCP 服务器配置

    Attributes:
        name: 服务器名(用户引用 key)
        transport: stdio / streamable_http / http / sse
        command: stdio 模式的启动命令
        args: stdio 模式的参数列表
        url: http / sse 模式的 URL
        headers: HTTP 模式的自定义 headers
        auth_type: oauth / api_key
        enabled: 是否启用
    """
    name: str
    transport: str  # stdio, http, sse
    command: Optional[str] = None
    args: Optional[List[str]] = None
    url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    auth_type: Optional[str] = None
    enabled: bool = True

    def to_dict(self) -> Dict:
        return asdict(self)


# SDK 可用性检测 —— 在 manager 里使用
_MCP_AVAILABLE: bool = False
try:
    from mcp import ClientSession, StdioServerParameters  # noqa: F401
    from mcp.client.stdio import stdio_client  # noqa: F401
    from mcp.types import TextContent  # noqa: F401
    _MCP_AVAILABLE = True
except ImportError:
    pass

_STREAMABLE_HTTP_AVAILABLE: bool = False
try:
    from mcp.client.streamable_http import streamablehttp_client  # noqa: F401
    _STREAMABLE_HTTP_AVAILABLE = True
except ImportError:
    pass

_SSE_AVAILABLE: bool = False
try:
    from mcp.client.sse import sse_client  # noqa: F401
    _SSE_AVAILABLE = True
except ImportError:
    pass
