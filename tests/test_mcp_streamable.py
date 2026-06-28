"""MCP Streamable HTTP 测试"""
import json
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

from fr_cli.weapon.mcp import (
    MCPServer, MCPServerManager, _STREAMABLE_HTTP_AVAILABLE, _SSE_AVAILABLE,
)


class TestServerConfig(unittest.TestCase):
    def test_stdio(self):
        s = MCPServer(name="test", transport="stdio", command="node", args=["x.js"])
        d = s.to_dict()
        self.assertEqual(d["transport"], "stdio")
        self.assertEqual(d["command"], "node")

    def test_streamable_http(self):
        s = MCPServer(name="http-server", transport="streamable_http", url="http://x.com")
        d = s.to_dict()
        self.assertEqual(d["transport"], "streamable_http")
        self.assertEqual(d["url"], "http://x.com")

    def test_sse(self):
        s = MCPServer(name="sse", transport="sse", url="http://y.com")
        self.assertEqual(s.transport, "sse")


class TestManagerTransports(unittest.TestCase):
    def setUp(self):
        self.mgr = MCPServerManager(cfg={"mcp": {"servers": {}}})

    def test_add_streamable_http(self):
        result = self.mgr.add_server(
            name="http1",
            transport="streamable_http",
            url="http://example.com/mcp",
            headers={"Authorization": "Bearer xxx"},
        )
        self.assertTrue(result)
        srv = self.mgr.get_server("http1")
        self.assertEqual(srv.transport, "streamable_http")
        self.assertEqual(srv.url, "http://example.com/mcp")
        self.assertEqual(srv.headers["Authorization"], "Bearer xxx")

    def test_add_sse(self):
        result = self.mgr.add_server(
            name="sse1",
            transport="sse",
            url="http://example.com/sse",
        )
        self.assertTrue(result)

    def test_get_tools_streamable_http_not_available(self):
        self.mgr.add_server(name="http_x", transport="streamable_http", url="http://x")
        # 如果 SDK 没装 streamable_http,get_tools 返回错误标记
        if not _STREAMABLE_HTTP_AVAILABLE:
            tools = self.mgr.get_tools("http_x")
            self.assertEqual(len(tools), 1)
            self.assertTrue(tools[0].get("_error"))

    def test_call_tool_unsupported_transport(self):
        self.mgr.add_server(name="ws", transport="websocket", url="ws://x")
        # 未实现的 transport
        result, err = self.mgr.call_tool_sync("ws", "x", {})
        self.assertIsNotNone(err)


class TestStreamableHTTPAvailable(unittest.TestCase):
    def test_module_loads(self):
        # 验证 streamable_http 模块能 import
        try:
            from mcp.client.streamable_http import streamablehttp_client
            self.assertTrue(callable(streamablehttp_client))
        except ImportError:
            self.skipTest("mcp.client.streamable_http not available")


class TestServerParams(unittest.TestCase):
    def test_stdio_params(self):
        s = MCPServer(name="x", transport="stdio", command="node", args=["a.js"])
        mgr = MCPServerManager(cfg={"mcp": {"servers": {}}})
        params = mgr._server_to_params(s)
        self.assertIsNotNone(params)
        self.assertEqual(params.command, "node")

    def test_http_no_params(self):
        s = MCPServer(name="x", transport="streamable_http", url="http://x")
        mgr = MCPServerManager(cfg={"mcp": {"servers": {}}})
        params = mgr._server_to_params(s)
        self.assertIsNone(params)


if __name__ == "__main__":
    unittest.main()