"""
MCPServerManagerInvocationMixin —— MCP 工具调用

- _call_tool_async  私有:异步调用 MCP 工具
- _do_call          静态:实际调用 tool 并提取文本内容
- call_tool_sync    同步:外部 API,带前置校验
- call_tool         异步:外部 API,带前置校验
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict

from fr_cli.weapon.mcp.models import (
    MCPServer,
    _MCP_AVAILABLE,
    _SSE_AVAILABLE,
    _STREAMABLE_HTTP_AVAILABLE,
)

try:
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client
    from mcp.types import TextContent
except ImportError:
    ClientSession = None
    stdio_client = None
    TextContent = None

try:
    from mcp.client.streamable_http import streamablehttp_client
except ImportError:
    streamablehttp_client = None

try:
    from mcp.client.sse import sse_client
except ImportError:
    sse_client = None


class MCPServerManagerInvocationMixin:
    """MCP 工具调用 mixin"""

    async def _call_tool_async(self, srv: MCPServer, tool_name: str, arguments: Dict) -> Any:
        """异步调用 MCP 工具(支持 stdio / streamable_http / sse)"""
        if srv.transport == "stdio":
            params = self._server_to_params(srv)
            if params is None:
                return None, f"MCP server [{srv.name}] 缺少启动命令"
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await self._do_call(session, tool_name, arguments)
        elif srv.transport in ("streamable_http", "http"):
            if not _STREAMABLE_HTTP_AVAILABLE:
                return None, "streamable_http 不可用,请升级 mcp SDK (pip install --upgrade mcp)"
            headers = srv.headers or {}
            async with streamablehttp_client(srv.url, headers=headers) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await self._do_call(session, tool_name, arguments)
        elif srv.transport == "sse":
            if not _SSE_AVAILABLE:
                return None, "SSE 不可用,请升级 mcp SDK"
            headers = srv.headers or {}
            async with sse_client(srv.url, headers=headers) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await self._do_call(session, tool_name, arguments)
        return None, f"MCP server [{srv.name}] 传输类型 '{srv.transport}' 不支持"

    @staticmethod
    async def _do_call(session, tool_name: str, arguments: Dict) -> Any:
        """内部:实际调用 tool"""
        result = await session.call_tool(tool_name, arguments=arguments or {})
        texts = []
        for content in result.content:
            if isinstance(content, TextContent):
                texts.append(content.text)
            else:
                texts.append(str(content))
        return "\n".join(texts), None

    def call_tool_sync(self, server_name: str, tool_name: str, arguments: Dict) -> Any:
        """同步调用 MCP 工具"""
        if not _MCP_AVAILABLE:
            return None, "MCP SDK 未安装,请执行: pip install mcp"
        if server_name not in self.servers:
            return None, f"Unknown MCP server: {server_name}"
        srv = self.servers[server_name]
        if not srv.enabled:
            return None, f"MCP server [{server_name}] 已禁用"
        if srv.transport not in ("stdio", "streamable_http", "http", "sse"):
            return None, f"MCP server [{server_name}] 传输类型 '{srv.transport}' 不支持"
        try:
            return asyncio.run(self._call_tool_async(srv, tool_name, arguments))
        except Exception as e:
            return None, f"MCP 调用失败: {e}"

    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict) -> Any:
        """异步调用 MCP 工具"""
        if not _MCP_AVAILABLE:
            raise NotImplementedError("MCP SDK 未安装")
        if server_name not in self.servers:
            raise ValueError(f"Unknown MCP server: {server_name}")
        srv = self.servers[server_name]
        return await self._call_tool_async(srv, tool_name, arguments)
