"""
MCPServerManagerResourcesMixin —— MCP 资源

- _list_resources_async  私有:异步获取资源列表
- _do_list_resources     静态:从 session 拿 resources
- list_resources         同步:某服务器资源列表
- list_all_resources     同步:全部已启用服务器资源
- _read_resource_async   私有:异步读取资源
- read_resource_sync     同步:读取资源内容
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from fr_cli.weapon.mcp.models import (
    MCPServer,
    _MCP_AVAILABLE,
    _SSE_AVAILABLE,
    _STREAMABLE_HTTP_AVAILABLE,
)

try:
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client
except ImportError:
    ClientSession = None
    stdio_client = None

try:
    from mcp.client.streamable_http import streamablehttp_client
except ImportError:
    streamablehttp_client = None

try:
    from mcp.client.sse import sse_client
except ImportError:
    sse_client = None


class MCPServerManagerResourcesMixin:
    """MCP 资源 mixin"""

    async def _list_resources_async(self, srv: MCPServer) -> List[Dict]:
        """异步获取某服务器的资源列表"""
        if srv.transport == "stdio":
            params = self._server_to_params(srv)
            if params is None:
                return []
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await self._do_list_resources(session, srv.name)
        elif srv.transport in ("streamable_http", "http"):
            if not _STREAMABLE_HTTP_AVAILABLE:
                return [{
                    "uri": "_error", "name": f"{srv.name}_error",
                    "description": "streamable_http 不可用",
                    "server": srv.name, "_error": True,
                }]
            headers = srv.headers or {}
            async with streamablehttp_client(srv.url, headers=headers) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await self._do_list_resources(session, srv.name)
        elif srv.transport == "sse":
            if not _SSE_AVAILABLE:
                return [{
                    "uri": "_error", "name": f"{srv.name}_error",
                    "description": "SSE 不可用",
                    "server": srv.name, "_error": True,
                }]
            headers = srv.headers or {}
            async with sse_client(srv.url, headers=headers) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await self._do_list_resources(session, srv.name)
        return []

    @staticmethod
    async def _do_list_resources(session, server_name: str) -> List[Dict]:
        """内部:从 session 拿 resources"""
        try:
            result = await session.list_resources()
        except Exception as e:
            return [{
                "uri": "_error", "name": "_error",
                "description": f"list_resources 失败: {e}",
                "server": server_name, "_error": True,
            }]
        resources = []
        for r in result.resources:
            resources.append({
                "uri": getattr(r, "uri", ""),
                "name": getattr(r, "name", ""),
                "description": getattr(r, "description", ""),
                "mimeType": getattr(r, "mimeType", ""),
                "server": server_name,
            })
        return resources

    def list_resources(self, server_name: str) -> List[Dict]:
        """同步列出某服务器的资源"""
        if not _MCP_AVAILABLE:
            return []
        if server_name not in self.servers:
            return []
        srv = self.servers[server_name]
        if not srv.enabled:
            return []
        if srv.transport not in ("stdio", "streamable_http", "http", "sse"):
            return []
        try:
            return asyncio.run(self._list_resources_async(srv))
        except Exception as e:
            return [{
                "uri": "_error", "name": f"{server_name}_error",
                "description": f"获取资源失败: {e}",
                "server": server_name, "_error": True,
            }]

    def list_all_resources(self) -> List[Dict]:
        """列出所有已启用服务器的资源"""
        all_resources = []
        for name in self.servers:
            all_resources.extend(self.list_resources(name))
        return all_resources

    async def _read_resource_async(self, srv: MCPServer, uri: str) -> Any:
        """异步读取资源"""
        session_cm = None
        if srv.transport == "stdio":
            params = self._server_to_params(srv)
            if params is None:
                return None, f"MCP server [{srv.name}] 缺少启动命令"
            session_cm = stdio_client(params)
        elif srv.transport in ("streamable_http", "http"):
            if not _STREAMABLE_HTTP_AVAILABLE:
                return None, "streamable_http 不可用"
            headers = srv.headers or {}
            session_cm = streamablehttp_client(srv.url, headers=headers)
        elif srv.transport == "sse":
            if not _SSE_AVAILABLE:
                return None, "SSE 不可用"
            headers = srv.headers or {}
            session_cm = sse_client(srv.url, headers=headers)
        else:
            return None, f"MCP server [{srv.name}] 传输类型 '{srv.transport}' 不支持"

        async with session_cm as conn_args:
            if srv.transport == "stdio":
                read, write = conn_args
            elif srv.transport in ("streamable_http", "http"):
                read, write, _ = conn_args
            else:  # sse
                read, write = conn_args

            async with ClientSession(read, write) as session:
                await session.initialize()
                try:
                    result = await session.read_resource(uri)
                except Exception as e:
                    return None, f"read_resource({uri}) 失败: {e}"
                # 提取文本内容
                texts = []
                for content in result.contents:
                    if hasattr(content, "text") and content.text:
                        texts.append(content.text)
                    elif hasattr(content, "blob"):
                        texts.append(f"[blob: {len(content.blob)} bytes]")
                    else:
                        texts.append(str(content))
                return "\n".join(texts), None

    def read_resource_sync(self, server_name: str, uri: str) -> Any:
        """同步读取资源"""
        if not _MCP_AVAILABLE:
            return None, "MCP SDK 未安装"
        if server_name not in self.servers:
            return None, f"Unknown MCP server: {server_name}"
        srv = self.servers[server_name]
        if not srv.enabled:
            return None, f"MCP server [{server_name}] 已禁用"
        if srv.transport not in ("stdio", "streamable_http", "http", "sse"):
            return None, f"MCP server [{server_name}] 传输类型不支持"
        try:
            return asyncio.run(self._read_resource_async(srv, uri))
        except Exception as e:
            return None, f"MCP read_resource 失败: {e}"
