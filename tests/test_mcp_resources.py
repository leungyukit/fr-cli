"""MCP Resources 测试"""
import json
import unittest
from unittest.mock import patch, MagicMock, AsyncMock

from fr_cli.weapon.mcp import (
    MCPServer, MCPServerManager, _STREAMABLE_HTTP_AVAILABLE, _SSE_AVAILABLE,
)


class TestResources(unittest.TestCase):
    """测试 MCP Resources API(list_resources / read_resource)"""

    def test_list_resources_stdio(self):
        """std 服务器应该能调用 list_resources"""
        mgr = MCPServerManager(cfg={"mcp": {"servers": {}}})
        srv = MCPServer(name="test", transport="stdio", command="echo", args=[])
        mgr.servers["test"] = srv

        # mock _list_resources_async 返回示例数据
        with patch.object(mgr, "_list_resources_async",
                          return_value=[
                              {"uri": "file:///x", "name": "x", "server": "test"}
                          ]):
            with patch("asyncio.run", return_value=[{"uri": "file:///x", "name": "x", "server": "test"}]):
                resources = mgr.list_resources("test")
                self.assertEqual(len(resources), 1)
                self.assertEqual(resources[0]["uri"], "file:///x")

    def test_list_resources_unsupported_transport(self):
        """websocket 等不支持"""
        mgr = MCPServerManager(cfg={"mcp": {"servers": {}}})
        srv = MCPServer(name="ws", transport="websocket", url="ws://x")
        mgr.servers["ws"] = srv
        resources = mgr.list_resources("ws")
        self.assertEqual(resources, [])

    def test_list_resources_disabled(self):
        mgr = MCPServerManager(cfg={"mcp": {"servers": {}}})
        srv = MCPServer(name="d", transport="stdio", command="x")
        srv.enabled = False
        mgr.servers["d"] = srv
        self.assertEqual(mgr.list_resources("d"), [])

    def test_list_all_resources(self):
        mgr = MCPServerManager(cfg={"mcp": {"servers": {}}})
        srv1 = MCPServer(name="a", transport="stdio", command="x")
        srv2 = MCPServer(name="b", transport="stdio", command="y")
        mgr.servers["a"] = srv1
        mgr.servers["b"] = srv2

        with patch.object(mgr, "list_resources",
                          side_effect=[[{"uri": "u1"}], [{"uri": "u2"}]]):
            all_res = mgr.list_all_resources()
            self.assertEqual(len(all_res), 2)

    def test_read_resource_sync_unsupported_transport(self):
        mgr = MCPServerManager(cfg={"mcp": {"servers": {}}})
        srv = MCPServer(name="ws", transport="websocket", url="ws://x")
        mgr.servers["ws"] = srv
        result, err = mgr.read_resource_sync("ws", "file:///x")
        self.assertIsNotNone(err)
        self.assertIn("不支持", err)

    def test_read_resource_sync_disabled(self):
        mgr = MCPServerManager(cfg={"mcp": {"servers": {}}})
        srv = MCPServer(name="d", transport="stdio", command="x")
        srv.enabled = False
        mgr.servers["d"] = srv
        result, err = mgr.read_resource_sync("d", "uri")
        self.assertIsNotNone(err)
        self.assertIn("禁用", err)

    def test_read_resource_sync_unknown_server(self):
        mgr = MCPServerManager(cfg={"mcp": {"servers": {}}})
        result, err = mgr.read_resource_sync("never", "uri")
        self.assertIsNotNone(err)
        self.assertIn("Unknown", err)


if __name__ == "__main__":
    unittest.main()