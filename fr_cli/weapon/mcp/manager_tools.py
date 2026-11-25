"""
MCPServerManagerToolsMixin —— MCP 工具发现

- _server_to_params   私有:将 MCPServer 转换为 SDK StdioServerParameters
- _get_tools_async    私有:异步获取某服务器的工具列表
- _list_tools         静态:从 session 拿 tools
- get_tools           同步获取某服务器工具(带 TTL 缓存)
- list_all_tools      列出所有已启用服务器的工具
- get_server_tools_desc  生成所有 MCP 服务器的描述文本(用于 system prompt)
- invalidate_cache    清除工具列表缓存(手动刷新)

缓存说明:
  每次 tools/list 都要新建 MCP session(起子进程 / 连 HTTP),在多线程场景下
  频繁调用非常慢。因此按 server 名缓存工具列表,默认 TTL 300 秒,
  可通过实例属性调整: ``mgr.tool_cache_ttl = 60``
  (设为 0 表示禁用缓存,每次都实时拉取)。

依赖 SDK:_server_to_params 返回 StdioServerParameters,
         _get_tools_async 调用 stdio_client / streamablehttp_client / sse_client
"""
from __future__ import annotations

import asyncio
import os
import threading
import time
from typing import Any, Dict, List, Optional

from fr_cli.weapon.mcp.manager_invocation import run_coroutine_sync
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

    # 工具列表缓存 TTL(秒)—— 可用实例属性覆盖: mgr.tool_cache_ttl = 60
    tool_cache_ttl: float = 300.0
    # 工具发现超时(秒)—— 可用实例属性覆盖: mgr.tool_fetch_timeout = 10
    tool_fetch_timeout: float = 15.0
    # 类级可重入锁:保护缓存存储的初始化与读写(多线程下安全)
    _cache_lock = threading.RLock()

    # ---------------- 缓存 ----------------

    def _cache_store(self) -> Dict[str, Dict[str, Any]]:
        """返回(必要时初始化)本实例的工具缓存存储。"""
        with self._cache_lock:
            store = getattr(self, "_tool_cache_store", None)
            if store is None:
                store = {}
                self._tool_cache_store = store
            return store

    def _cached_tools(self, name: str) -> Optional[List[Dict]]:
        """取缓存的工具列表;未命中或已过期返回 None。"""
        with self._cache_lock:
            entry = self._cache_store().get(name)
            if not entry:
                return None
            try:
                ttl = float(getattr(self, "tool_cache_ttl", 300.0))
            except (TypeError, ValueError):
                ttl = 300.0
            if ttl <= 0:
                return None
            if time.time() - float(entry.get("timestamp", 0)) > ttl:
                return None
            return entry.get("tools")

    def _store_tools(self, name: str, tools: List[Dict]) -> None:
        """写入缓存。错误结果不入缓存(避免把临时故障固化 5 分钟)。"""
        if not tools:
            return
        if any(isinstance(t, dict) and t.get("_error") for t in tools):
            return
        with self._cache_lock:
            self._cache_store()[name] = {"tools": tools, "timestamp": time.time()}

    def invalidate_cache(self, name: Optional[str] = None) -> int:
        """清除工具列表缓存。

        Args:
            name: 指定 server 名;None 表示清除全部

        Returns:
            被清除的缓存条目数
        """
        with self._cache_lock:
            store = self._cache_store()
            if name is None:
                count = len(store)
                store.clear()
                return count
            if name in store:
                del store[name]
                return 1
            return 0

    # ---------------- 工具发现 ----------------

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

    async def _get_tools_with_timeout(self, srv: MCPServer, timeout: Optional[float]) -> List[Dict]:
        """带超时的工具发现(避免 server 挂死时无限等待)。"""
        if not timeout or timeout <= 0:
            return await self._get_tools_async(srv)
        return await asyncio.wait_for(self._get_tools_async(srv), timeout=timeout)

    def get_tools(self, name: str) -> List[Dict]:
        """获取 MCP 工具列表(真实调用 tools/list,TTL 内命中缓存不重复建连)

        Returns:
            工具列表,每项含 name / description / inputSchema / server 四个字段
            (结构与既有调用方保持一致)
        """
        if not _MCP_AVAILABLE:
            return []
        if name not in self.servers:
            return []
        srv = self.servers[name]
        if not srv.enabled:
            return []
        if srv.transport not in ("stdio", "streamable_http", "http", "sse"):
            return []
        # 缓存命中 —— 不再新建 MCP session
        cached = self._cached_tools(name)
        if cached is not None:
            return cached
        timeout = getattr(self, "tool_fetch_timeout", 15.0)
        try:
            tools = run_coroutine_sync(
                lambda: self._get_tools_with_timeout(srv, timeout)
            )
        except asyncio.TimeoutError:
            tools = [{
                "name": f"{name}_error",
                "description": f"获取工具列表超时 ({timeout}s)",
                "inputSchema": {"type": "object", "properties": {}},
                "server": name,
                "_error": True,
            }]
        except Exception as e:
            tools = [{
                "name": f"{name}_error",
                "description": f"获取工具列表失败: {e}",
                "inputSchema": {"type": "object", "properties": {}},
                "server": name,
                "_error": True,
            }]
        self._store_tools(name, tools)
        return tools

    def list_all_tools(self) -> List[Dict]:
        """列出所有已启用服务器的工具"""
        all_tools = []
        for name in self.servers:
            all_tools.extend(self.get_tools(name))
        return all_tools

    def peek_tools(self) -> List[Dict]:
        """**只读缓存**地列出所有工具 —— 绝不触发网络请求。

        用途:system prompt 组装等**热路径**。MCP server 可能不可达,
        实时发现会阻塞最多 ``tool_fetch_timeout`` 秒, 拖慢每一轮对话。
        缓存由启动时的后台预热(``register_mcp_tools``)填充。
        """
        all_tools = []
        try:
            store = self._cache_store()
        except Exception:
            return []
        for name in self.servers:
            entry = store.get(name)
            if not entry:
                continue
            all_tools.extend(entry.get("tools") or [])
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
