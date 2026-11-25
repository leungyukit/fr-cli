"""
MCPServerManagerInvocationMixin —— MCP 工具调用

- _call_tool_async  私有:异步调用 MCP 工具(带超时保护)
- _invoke_async     私有:按 transport 建立会话并调用
- _do_call          静态:实际调用 tool 并提取文本内容
- call_tool_sync    同步:外部 API,带前置校验 + 超时 + 兼容运行中 event loop
- call_tool         异步:外部 API,带前置校验 + 超时

超时说明:
  MCP server 可能永不返回(挂死的 stdio 进程 / 无响应的 HTTP 端点),
  因此所有调用都套一层 asyncio.wait_for,默认 30 秒后放弃并返回错误,
  绝不无限期挂住调用方(REPL / bot worker 线程)。
"""
from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any, Callable, Dict, Optional

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


# MCP 调用默认超时(秒)—— 可在调用时用 timeout 参数覆盖
DEFAULT_CALL_TIMEOUT = 30.0


def _format_seconds(value: float) -> str:
    """把秒数格式化成紧凑文本: 30.0 → "30", 0.5 → "0.5"。"""
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)


def _run_in_new_thread(coro_factory: Callable[[], Any]) -> Any:
    """在独立线程的新 event loop 中执行协程,并把结果取回当前线程。

    用于"当前线程已有运行中 event loop"的场景(bot 的多线程网关):
    asyncio.run 不能在运行中的 loop 里调用,只能另起线程执行。
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro_factory())
        return future.result()


def run_coroutine_sync(coro_factory: Callable[[], Any]) -> Any:
    """同步执行协程 —— 兼容"当前线程已有运行中 event loop"的场景。

    asyncio.run() 在已经运行 event loop 的线程里会抛 RuntimeError
    ("Runner.run() cannot be called from a running event loop"),
    此时退回到独立线程(ThreadPoolExecutor)里新建 loop 执行。

    Args:
        coro_factory: 无参可调用,返回待执行的协程。
            用工厂而非协程对象,是为了异常后可安全重试(协程只能被 await 一次)。

    Returns:
        协程的返回值。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # 当前线程没有运行中的 loop —— 常规路径
        try:
            return asyncio.run(coro_factory())
        except RuntimeError as e:
            msg = str(e)
            if "already running" in msg or "running event loop" in msg:
                return _run_in_new_thread(coro_factory)
            raise
    # 当前线程已有运行中的 loop —— 换线程执行
    return _run_in_new_thread(coro_factory)


class MCPServerManagerInvocationMixin:
    """MCP 工具调用 mixin"""

    async def _call_tool_async(self, srv: MCPServer, tool_name: str, arguments: Dict,
                                timeout: Optional[float] = None) -> Any:
        """异步调用 MCP 工具(支持 stdio / streamable_http / sse),带超时保护。

        Args:
            srv: MCP 服务器配置
            tool_name: 目标工具名
            arguments: 工具参数
            timeout: 超时秒数;None → 默认 30 秒;<=0 表示不设超时

        Returns:
            ``(结果文本, None)`` 或 ``(None, 错误描述)``
        """
        effective_timeout = DEFAULT_CALL_TIMEOUT if timeout is None else timeout
        try:
            if effective_timeout and effective_timeout > 0:
                return await asyncio.wait_for(
                    self._invoke_async(srv, tool_name, arguments),
                    timeout=effective_timeout,
                )
            return await self._invoke_async(srv, tool_name, arguments)
        except asyncio.TimeoutError:
            return None, f"MCP 调用超时 ({_format_seconds(effective_timeout)}s)"

    async def _invoke_async(self, srv: MCPServer, tool_name: str, arguments: Dict) -> Any:
        """按 transport 建立会话并调用工具(不含超时逻辑)。"""
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

    def call_tool_sync(self, server_name: str, tool_name: str, arguments: Dict,
                       timeout: Optional[float] = None) -> Any:
        """同步调用 MCP 工具。

        Args:
            server_name: MCP 服务器名
            tool_name: 工具名
            arguments: 工具参数
            timeout: 超时秒数;None → 默认 30 秒

        Returns:
            ``(结果文本, None)`` 或 ``(None, 错误描述)``
        """
        if not _MCP_AVAILABLE:
            return None, "MCP SDK 未安装,请执行: pip install mcp"
        if server_name not in self.servers:
            return None, f"Unknown MCP server: {server_name}"
        srv = self.servers[server_name]
        if not srv.enabled:
            return None, f"MCP server [{server_name}] 已禁用"
        if srv.transport not in ("stdio", "streamable_http", "http", "sse"):
            return None, f"MCP server [{server_name}] 传输类型 '{srv.transport}' 不支持"
        effective_timeout = DEFAULT_CALL_TIMEOUT if timeout is None else timeout
        try:
            return run_coroutine_sync(
                lambda: self._call_tool_async(srv, tool_name, arguments, effective_timeout)
            )
        except Exception as e:
            return None, f"MCP 调用失败: {e}"

    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict,
                        timeout: Optional[float] = None) -> Any:
        """异步调用 MCP 工具(带超时)"""
        if not _MCP_AVAILABLE:
            raise NotImplementedError("MCP SDK 未安装")
        if server_name not in self.servers:
            raise ValueError(f"Unknown MCP server: {server_name}")
        srv = self.servers[server_name]
        return await self._call_tool_async(srv, tool_name, arguments, timeout)
