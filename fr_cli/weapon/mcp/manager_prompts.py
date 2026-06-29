"""
MCPServerManagerPromptsMixin —— MCP prompts(模板)

- _list_prompts_async  私有:异步获取 prompts 列表
- _do_list_prompts     静态:从 session 拿 prompts
- list_prompts         同步:某服务器 prompts 列表
- list_all_prompts     同步:全部已启用服务器 prompts
- _get_prompt_async    私有:异步获取单个 prompt
- get_prompt_sync      同步:获取 prompt 内容
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

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


class MCPServerManagerPromptsMixin:
    """MCP prompts mixin"""

    async def _list_prompts_async(self, srv: MCPServer) -> List[Dict]:
        """异步获取某服务器的 prompts 列表"""
        if srv.transport == "stdio":
            params = self._server_to_params(srv)
            if params is None:
                return []
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await self._do_list_prompts(session, srv.name)
        elif srv.transport in ("streamable_http", "http"):
            if not _STREAMABLE_HTTP_AVAILABLE:
                return [{
                    "name": f"{srv.name}_error",
                    "description": "streamable_http 不可用",
                    "server": srv.name, "_error": True,
                }]
            headers = srv.headers or {}
            async with streamablehttp_client(srv.url, headers=headers) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await self._do_list_prompts(session, srv.name)
        elif srv.transport == "sse":
            if not _SSE_AVAILABLE:
                return [{
                    "name": f"{srv.name}_error",
                    "description": "SSE 不可用",
                    "server": srv.name, "_error": True,
                }]
            headers = srv.headers or {}
            async with sse_client(srv.url, headers=headers) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await self._do_list_prompts(session, srv.name)
        return []

    @staticmethod
    async def _do_list_prompts(session, server_name: str) -> List[Dict]:
        """内部:从 session 拿 prompts"""
        try:
            result = await session.list_prompts()
        except Exception as e:
            return [{
                "name": "_error",
                "description": f"list_prompts 失败: {e}",
                "server": server_name, "_error": True,
            }]
        prompts = []
        for p in result.prompts:
            prompts.append({
                "name": getattr(p, "name", ""),
                "description": getattr(p, "description", ""),
                "arguments": [
                    {
                        "name": getattr(a, "name", ""),
                        "description": getattr(a, "description", ""),
                        "required": getattr(a, "required", False),
                    }
                    for a in (getattr(p, "arguments", []) or [])
                ],
                "server": server_name,
            })
        return prompts

    def list_prompts(self, server_name: str) -> List[Dict]:
        """同步列出某服务器的 prompts"""
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
            return asyncio.run(self._list_prompts_async(srv))
        except Exception as e:
            return [{
                "name": f"{server_name}_error",
                "description": f"获取 prompts 失败: {e}",
                "server": server_name, "_error": True,
            }]

    def list_all_prompts(self) -> List[Dict]:
        """列出所有已启用服务器的 prompts"""
        all_prompts = []
        for name in self.servers:
            all_prompts.extend(self.list_prompts(name))
        return all_prompts

    async def _get_prompt_async(self, srv: MCPServer, name: str,
                                 arguments: Optional[Dict] = None) -> Any:
        """异步获取 prompt"""
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
            return None, f"MCP server [{srv.name}] 传输类型不支持"

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
                    result = await session.get_prompt(name, arguments=arguments or {})
                except Exception as e:
                    return None, f"get_prompt({name}) 失败: {e}"
                # 提取 messages
                messages = []
                for msg in result.messages:
                    messages.append({
                        "role": getattr(msg, "role", ""),
                        "content": getattr(msg, "content", ""),
                    })
                return {
                    "description": getattr(result, "description", ""),
                    "messages": messages,
                }, None

    def get_prompt_sync(self, server_name: str, name: str,
                        arguments: Optional[Dict] = None) -> Any:
        """同步获取 prompt 内容"""
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
            return asyncio.run(self._get_prompt_async(srv, name, arguments))
        except Exception as e:
            return None, f"MCP get_prompt 失败: {e}"
