"""
MCPServerManagerToolsMixin —— MCP 工具发现

- _server_to_params   私有:将 MCPServer 转换为 SDK StdioServerParameters
- _get_tools_async    私有:异步获取某服务器的工具列表
- _list_tools         静态:从 session 拿 tools
- get_tools           同步获取某服务器工具
- list_all_tools      列出所有已启用服务器的工具
- get_server_tools_desc  生成所有 MCP 服务器的描述文本(用于 system prompt)

依赖 SDK:_server_to_params 返回 StdioServerParameters,
         _get_tools_async 调用 stdio_client / streamablehttp_client / sse_client
"""
from __future__ import annotations

import asyncio
import os
from typing import Dict, List

from fr_cli.weapon.mcp.models import (
    MCPServer,
    _MCP_AVAILABLE,
    _SSE_AVAILABLE,
    _STREAMABLE_HTTP_AVAILABLE,
)

# 延迟 import SDK(仅在调用时 import)
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    ClientSession = None
    StdioServerParameters = None
    stdio_client = None

try:
    from mcp.client.streamable_http import streamablehttp_client
except ImportError:
    streamablehttp_client = None

try:
    from mcp.client.sse import sse_client
except ImportError:
    sse_client = None


class MCPServerManagerToolsMixin:
    """MCP 工具发现 mixin"""

    def _server_to_params(self, srv: MCPServer):
        """将内部 MCPServer 转换为 mcp SDK 的 StdioServerParameters"""
        if not srv.command:
            return None
        env = os.environ.copy()
        return StdioServerParameters(
            command=srv.command,
            args=srv.args or [],
            env=env,
        )

    async def _get_tools_async(self, srv: MCPServer) -> List[Dict]:
        """异步获取某服务器的工具列表(支持 stdio / streamable_http / sse)"""
        if srv.transport == "stdio":
            params = self._server_to_params(srv)
            if params is None:
                return []
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await self._list_tools(session, srv.name)
        elif srv.transport in ("streamable_http", "http"):
            if not _STREAMABLE_HTTP_AVAILABLE:
                return [{
                    "name": f"{srv.name}_error",
                    "description": "streamable_http 不可用,请升级 mcp SDK",
                    "inputSchema": {"type": "object"},
                    "server": srv.name, "_error": True,
                }]
            headers = srv.headers or {}
            async with streamablehttp_client(srv.url, headers=headers) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await self._list_tools(session, srv.name)
        elif srv.transport == "sse":
            if not _SSE_AVAILABLE:
                return [{
                    "name": f"{srv.name}_error",
                    "description": "SSE 不可用,请升级 mcp SDK",
                    "inputSchema": {"type": "object"},
                    "server": srv.name, "_error": True,
                }]
            headers = srv.headers or {}
            async with sse_client(srv.url, headers=headers) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await self._list_tools(session, srv.name)
        return []

    @staticmethod
    async def _list_tools(session, server_name: str) -> List[Dict]:
        """内部工具:从 session 拿 tools"""
        result = await session.list_tools()
        tools = []
        for tool in result.tools:
            tools.append({
                "name": tool.name,
                "description": tool.description or "",
                "inputSchema": tool.inputSchema,
                "server": server_name,
            })
        return tools

    def get_tools(self, name: str) -> List[Dict]:
        """获取 MCP 工具列表(真实调用 tools/list)"""
        if not _MCP_AVAILABLE:
            return []
        if name not in self.servers:
            return []
        srv = self.servers[name]
        if not srv.enabled:
            return []
        if srv.transport not in ("stdio", "streamable_http", "http", "sse"):
            return []
        try:
            return asyncio.run(self._get_tools_async(srv))
        except Exception as e:
            return [{
                "name": f"{name}_error",
                "description": f"获取工具列表失败: {e}",
                "inputSchema": {"type": "object", "properties": {}},
                "server": name,
                "_error": True,
            }]

    def list_all_tools(self) -> List[Dict]:
        """列出所有已启用服务器的工具"""
        all_tools = []
        for name in self.servers:
            all_tools.extend(self.get_tools(name))
        return all_tools

    def get_server_tools_desc(self) -> str:
        """生成所有 MCP 服务器的描述文本(注入到 system prompt)"""
        if not self.servers:
            return ""
        lines = ["[MCP servers]"]
        for name, srv in self.servers.items():
            enabled = "enabled" if srv.enabled else "DISABLED"
            lines.append(f"- {name} ({enabled}, transport={srv.transport})")
            if srv.transport == "stdio" and srv.command:
                args_repr = ", ".join(repr(a) for a in (srv.args or []))
                lines.append(f"  command: {srv.command}({args_repr})")
            elif srv.transport in ("http", "sse") and srv.url:
                lines.append(f"  url: {srv.url}")
        return "\n".join(lines)
