"""MCP Prompts 测试"""
import unittest
from unittest.mock import patch

from fr_cli.weapon.mcp import (
    MCPServer, MCPServerManager,
)


class TestPrompts(unittest.TestCase):
    """测试 MCP Prompts API"""

    def test_list_prompts_stdio(self):
        mgr = MCPServerManager(cfg={"mcp": {"servers": {}}})
        srv = MCPServer(name="p", transport="stdio", command="x")
        mgr.servers["p"] = srv

        with patch("asyncio.run", return_value=[
            {"name": "summarize", "description": "总结", "arguments": [
                {"name": "text", "required": True}
            ], "server": "p"}
        ]):
            prompts = mgr.list_prompts("p")
            self.assertEqual(len(prompts), 1)
            self.assertEqual(prompts[0]["name"], "summarize")
            self.assertEqual(prompts[0]["arguments"][0]["name"], "text")

    def test_list_prompts_unsupported(self):
        mgr = MCPServerManager(cfg={"mcp": {"servers": {}}})
        srv = MCPServer(name="ws", transport="websocket", url="ws://x")
        mgr.servers["ws"] = srv
        self.assertEqual(mgr.list_prompts("ws"), [])

    def test_list_prompts_disabled(self):
        mgr = MCPServerManager(cfg={"mcp": {"servers": {}}})
        srv = MCPServer(name="d", transport="stdio", command="x")
        srv.enabled = False
        mgr.servers["d"] = srv
        self.assertEqual(mgr.list_prompts("d"), [])

    def test_list_all_prompts(self):
        mgr = MCPServerManager(cfg={"mcp": {"servers": {}}})
        srv1 = MCPServer(name="a", transport="stdio", command="x")
        srv2 = MCPServer(name="b", transport="stdio", command="y")
        mgr.servers["a"] = srv1
        mgr.servers["b"] = srv2

        with patch.object(mgr, "list_prompts",
                          side_effect=[[{"name": "p1"}], [{"name": "p2"}]]):
            all_p = mgr.list_all_prompts()
            self.assertEqual(len(all_p), 2)

    def test_get_prompt_sync_unsupported(self):
        mgr = MCPServerManager(cfg={"mcp": {"servers": {}}})
        srv = MCPServer(name="ws", transport="websocket", url="ws://x")
        mgr.servers["ws"] = srv
        result, err = mgr.get_prompt_sync("ws", "x")
        self.assertIsNotNone(err)

    def test_get_prompt_sync_disabled(self):
        mgr = MCPServerManager(cfg={"mcp": {"servers": {}}})
        srv = MCPServer(name="d", transport="stdio", command="x")
        srv.enabled = False
        mgr.servers["d"] = srv
        result, err = mgr.get_prompt_sync("d", "x")
        self.assertIsNotNone(err)
        self.assertIn("禁用", err)

    def test_get_prompt_sync_unknown(self):
        mgr = MCPServerManager(cfg={"mcp": {"servers": {}}})
        result, err = mgr.get_prompt_sync("nope", "x")
        self.assertIsNotNone(err)


if __name__ == "__main__":
    unittest.main()
