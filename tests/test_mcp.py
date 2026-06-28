"""
MCP (Model Context Protocol) 测试
覆盖 MCPServerManager 的配置管理、增删启停、状态查询、文本描述生成等。

注意:
- 纯逻辑测试(mock mcp SDK 或直接测管理逻辑)不依赖外部 MCP server
- 真实 MCP 协议测试用 stdio_client 连接本地 mock server
- mcp SDK 缺失时大部分测试 skip
"""
import os
import sys
import json
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _have_mcp():
    try:
        from mcp import ClientSession, StdioServerParameters  # noqa
        return True
    except ImportError:
        return False


# ==================== MCPServer 数据类 ====================

class TestMCPServerDataclass:

    def test_basic_construction(self):
        from fr_cli.weapon.mcp import MCPServer
        srv = MCPServer(
            name="test",
            transport="stdio",
            command="echo",
            args=["hello"],
        )
        assert srv.name == "test"
        assert srv.transport == "stdio"
        assert srv.command == "echo"
        assert srv.args == ["hello"]
        assert srv.enabled is True  # 默认

    def test_disabled_default_false(self):
        from fr_cli.weapon.mcp import MCPServer
        srv = MCPServer(name="t", transport="stdio", enabled=False)
        assert srv.enabled is False

    def test_to_dict(self):
        from fr_cli.weapon.mcp import MCPServer
        srv = MCPServer(
            name="test",
            transport="stdio",
            command="echo",
            args=["a", "b"],
        )
        d = srv.to_dict()
        assert d["name"] == "test"
        assert d["transport"] == "stdio"
        assert d["command"] == "echo"
        assert d["args"] == ["a", "b"]
        assert d["enabled"] is True


# ==================== 配置管理 ====================

class TestConfigManagement:

    def test_load_empty_config(self):
        """空 config:无 servers"""
        from fr_cli.weapon.mcp import MCPServerManager
        mgr = MCPServerManager(cfg={})
        assert mgr.servers == {}

    def test_load_from_cfg_dict(self):
        """从 cfg 字典加载"""
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {
            "mcp": {
                "servers": [
                    {
                        "name": "fs",
                        "transport": "stdio",
                        "command": "npx",
                        "args": ["-y", "@mcp/filesystem"],
                    },
                ]
            }
        }
        mgr = MCPServerManager(cfg=cfg)
        assert "fs" in mgr.servers
        assert mgr.servers["fs"].command == "npx"

    def test_load_invalid_servers_ignored(self):
        """servers 不是列表应被忽略"""
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {"mcp": {"servers": "not a list"}}
        mgr = MCPServerManager(cfg=cfg)
        assert mgr.servers == {}

    def test_load_server_without_name_skipped(self):
        """没有 name 的 server 应被跳过"""
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {
            "mcp": {
                "servers": [
                    {"transport": "stdio", "command": "echo"},
                ]
            }
        }
        mgr = MCPServerManager(cfg=cfg)
        assert mgr.servers == {}

    def test_load_non_dict_servers_skipped(self):
        """server 不是字典应被跳过"""
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {"mcp": {"servers": ["string", 123, None]}}
        mgr = MCPServerManager(cfg=cfg)
        assert mgr.servers == {}

    def test_load_multiple_servers(self):
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {
            "mcp": {
                "servers": [
                    {"name": "fs", "transport": "stdio", "command": "npx"},
                    {"name": "git", "transport": "stdio", "command": "git"},
                    {"name": "remote", "transport": "http", "url": "http://example.com"},
                ]
            }
        }
        mgr = MCPServerManager(cfg=cfg)
        assert len(mgr.servers) == 3
        assert mgr.servers["fs"].transport == "stdio"
        assert mgr.servers["remote"].transport == "http"


# ==================== 增删启停 ====================

class TestAddDelEnableDisable:

    def test_add_server(self):
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {}
        mgr = MCPServerManager(cfg=cfg)
        result = mgr.add_server("fs", "stdio", command="npx", args=["-y", "x"])
        assert result is True
        assert "fs" in mgr.servers

    def test_add_overwrites(self):
        """同名 server 应覆盖"""
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {}
        mgr = MCPServerManager(cfg=cfg)
        mgr.add_server("fs", "stdio", command="old_cmd")
        mgr.add_server("fs", "stdio", command="new_cmd")
        assert mgr.servers["fs"].command == "new_cmd"

    def test_del_existing(self):
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {}
        mgr = MCPServerManager(cfg=cfg)
        mgr.add_server("fs", "stdio", command="x")
        result = mgr.del_server("fs")
        assert result is True
        assert "fs" not in mgr.servers

    def test_del_nonexistent(self):
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {}
        mgr = MCPServerManager(cfg=cfg)
        result = mgr.del_server("never_existed")
        assert result is False

    def test_enable_server(self):
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {}
        mgr = MCPServerManager(cfg=cfg)
        mgr.add_server("fs", "stdio", command="x")
        mgr.disable_server("fs")
        assert mgr.servers["fs"].enabled is False
        result = mgr.enable_server("fs")
        assert result is True
        assert mgr.servers["fs"].enabled is True

    def test_disable_server(self):
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {}
        mgr = MCPServerManager(cfg=cfg)
        mgr.add_server("fs", "stdio", command="x")
        result = mgr.disable_server("fs")
        assert result is True
        assert mgr.servers["fs"].enabled is False

    def test_enable_nonexistent(self):
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {}
        mgr = MCPServerManager(cfg=cfg)
        result = mgr.enable_server("never_existed")
        assert result is False

    def test_disable_nonexistent(self):
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {}
        mgr = MCPServerManager(cfg=cfg)
        result = mgr.disable_server("never_existed")
        assert result is False


# ==================== 查询 ====================

class TestQuery:

    def test_list_servers(self):
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {}
        mgr = MCPServerManager(cfg=cfg)
        mgr.add_server("a", "stdio", command="x")
        mgr.add_server("b", "stdio", command="y")
        servers = mgr.list_servers()
        assert len(servers) == 2
        names = [s["name"] for s in servers]
        assert "a" in names and "b" in names

    def test_get_server_existing(self):
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {}
        mgr = MCPServerManager(cfg=cfg)
        mgr.add_server("fs", "stdio", command="x")
        srv = mgr.get_server("fs")
        assert srv is not None
        assert srv.name == "fs"

    def test_get_server_nonexistent(self):
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {}
        mgr = MCPServerManager(cfg=cfg)
        srv = mgr.get_server("never")
        assert srv is None


# ==================== _server_to_params ====================

class TestServerToParams:

    def test_stdio_with_command(self):
        """stdio + command 应能生成 params"""
        from fr_cli.weapon.mcp import MCPServerManager, MCPServer
        mgr = MCPServerManager(cfg={})
        srv = MCPServer(name="x", transport="stdio", command="echo", args=["hello"])
        params = mgr._server_to_params(srv)
        assert params is not None
        assert params.command == "echo"
        assert params.args == ["hello"]

    def test_stdio_no_command_returns_none(self):
        """stdio 但没有 command → 返回 None"""
        from fr_cli.weapon.mcp import MCPServerManager, MCPServer
        mgr = MCPServerManager(cfg={})
        srv = MCPServer(name="x", transport="stdio", command=None)
        assert mgr._server_to_params(srv) is None

    def test_args_default_empty(self):
        from fr_cli.weapon.mcp import MCPServerManager, MCPServer
        mgr = MCPServerManager(cfg={})
        srv = MCPServer(name="x", transport="stdio", command="echo")
        params = mgr._server_to_params(srv)
        assert params.args == []


# ==================== 描述生成 ====================

class TestServerToolsDesc:

    def test_empty_returns_empty_string(self):
        from fr_cli.weapon.mcp import MCPServerManager
        mgr = MCPServerManager(cfg={})
        assert mgr.get_server_tools_desc() == ""

    def test_includes_server_info(self):
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {}
        mgr = MCPServerManager(cfg=cfg)
        mgr.add_server("fs", "stdio", command="npx", args=["-y", "@mcp/fs"])
        desc = mgr.get_server_tools_desc()
        assert "fs" in desc
        assert "stdio" in desc
        assert "npx" in desc

    def test_disabled_server_marked(self):
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {}
        mgr = MCPServerManager(cfg=cfg)
        mgr.add_server("fs", "stdio", command="x")
        mgr.disable_server("fs")
        desc = mgr.get_server_tools_desc()
        assert "DISABLED" in desc or "disabled" in desc.lower()

    def test_http_server_includes_url(self):
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {}
        mgr = MCPServerManager(cfg=cfg)
        mgr.add_server("remote", "http", url="http://example.com/mcp")
        desc = mgr.get_server_tools_desc()
        assert "remote" in desc
        assert "http://example.com/mcp" in desc

    def test_multiple_servers_listed(self):
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {}
        mgr = MCPServerManager(cfg=cfg)
        mgr.add_server("a", "stdio", command="cmd_a")
        mgr.add_server("b", "stdio", command="cmd_b")
        desc = mgr.get_server_tools_desc()
        assert "a" in desc and "b" in desc


# ==================== get_tools / call_tool (mock) ====================

class TestGetToolsMocked:

    def test_get_tools_mcp_unavailable(self, monkeypatch):
        """MCP SDK 未装 → 返回空列表"""
        from fr_cli.weapon.mcp import MCPServerManager
        import fr_cli.weapon.mcp as mcp_mod
        monkeypatch.setattr(mcp_mod, "_MCP_AVAILABLE", False)

        cfg = {}
        mgr = MCPServerManager(cfg=cfg)
        mgr.add_server("fs", "stdio", command="echo")
        assert mgr.get_tools("fs") == []

    def test_get_tools_unknown_server(self):
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {}
        mgr = MCPServerManager(cfg=cfg)
        assert mgr.get_tools("never") == []

    def test_get_tools_disabled_server(self):
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {}
        mgr = MCPServerManager(cfg=cfg)
        mgr.add_server("fs", "stdio", command="echo")
        mgr.disable_server("fs")
        assert mgr.get_tools("fs") == []

    def test_get_tools_non_stdio_transport(self):
        """v2.8+:非 stdio transport(streamable_http / sse)走异步路径"""
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {}
        mgr = MCPServerManager(cfg=cfg)
        mgr.add_server("remote", "streamable_http", url="http://127.0.0.1:1")
        # 不会连上,所以应该失败;只验证返回 list 且不 hang
        # patch asyncio.run 避免真 hang
        with patch("asyncio.run", return_value=[]):
            tools = mgr.get_tools("remote")
            assert isinstance(tools, list)


class TestCallToolMocked:

    def test_call_tool_unknown_server(self):
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {}
        mgr = MCPServerManager(cfg=cfg)
        result, err = mgr.call_tool_sync("never", "tool", {})
        assert result is None
        assert "Unknown" in err or "unknown" in err

    def test_call_tool_disabled_server(self):
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {}
        mgr = MCPServerManager(cfg=cfg)
        mgr.add_server("fs", "stdio", command="echo")
        mgr.disable_server("fs")
        result, err = mgr.call_tool_sync("fs", "tool", {})
        assert result is None
        assert "禁用" in err or "disabled" in err.lower()

    def test_call_tool_non_stdio(self):
        """v2.8+:非 stdio transport 走对应 SDK 客户端"""
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {}
        mgr = MCPServerManager(cfg=cfg)
        mgr.add_server("remote", "streamable_http", url="http://127.0.0.1:1")
        # mock asyncio.run 避免 hang
        with patch("asyncio.run", return_value=(None, "mocked error")):
            result, err = mgr.call_tool_sync("remote", "tool", {})
            # 要么 result 非空(成功),要么 err 有合理消息
            assert err is not None
            assert "mocked error" in err


# ==================== from_config_file ====================

class TestFromConfigFile:

    def test_load_standard_config(self, tmp_path):
        """加载标准 MCP 配置(Claude Desktop 格式)"""
        from fr_cli.weapon.mcp import MCPServerManager
        config = {
            "mcpServers": {
                "fs": {
                    "command": "npx",
                    "args": ["-y", "@mcp/filesystem", "/tmp"],
                },
                "remote": {
                    "url": "http://example.com/mcp",
                },
            }
        }
        cfg_file = tmp_path / "mcp_config.json"
        cfg_file.write_text(json.dumps(config), encoding="utf-8")

        mgr = MCPServerManager.from_config_file(str(cfg_file))
        assert "fs" in mgr.servers
        assert mgr.servers["fs"].command == "npx"
        assert "remote" in mgr.servers
        assert mgr.servers["remote"].url == "http://example.com/mcp"

    def test_load_nonexistent_file(self, tmp_path):
        """文件不存在:返回空 manager"""
        from fr_cli.weapon.mcp import MCPServerManager
        mgr = MCPServerManager.from_config_file(str(tmp_path / "missing.json"))
        assert mgr.servers == {}

    def test_load_invalid_json(self, tmp_path):
        """JSON 损坏:返回空 manager(不崩)"""
        from fr_cli.weapon.mcp import MCPServerManager
        cfg_file = tmp_path / "bad.json"
        cfg_file.write_text("not valid json", encoding="utf-8")
        mgr = MCPServerManager.from_config_file(str(cfg_file))
        assert mgr.servers == {}

    def test_load_empty_config(self, tmp_path):
        from fr_cli.weapon.mcp import MCPServerManager
        cfg_file = tmp_path / "empty.json"
        cfg_file.write_text("{}", encoding="utf-8")
        mgr = MCPServerManager.from_config_file(str(cfg_file))
        assert mgr.servers == {}


# ==================== 单例 ====================

class TestSingleton:

    def test_get_mcp_manager_returns_singleton(self):
        from fr_cli.weapon import mcp as mcp_mod
        mcp_mod.reset_mcp_manager()
        mgr1 = mcp_mod.get_mcp_manager(cfg={"mcp": {"servers": [{"name": "x", "transport": "stdio", "command": "echo"}]}})
        mgr2 = mcp_mod.get_mcp_manager()
        # 应返回同一个实例
        assert mgr1 is mgr2
        assert "x" in mgr1.servers

    def test_reset_mcp_manager(self):
        from fr_cli.weapon import mcp as mcp_mod
        mgr1 = mcp_mod.get_mcp_manager(cfg={})
        mcp_mod.reset_mcp_manager()
        mgr2 = mcp_mod.get_mcp_manager(cfg={})
        # 重置后应是新实例
        assert mgr1 is not mgr2

    def test_singleton_thread_safe(self):
        """线程安全单例"""
        from fr_cli.weapon import mcp as mcp_mod
        mcp_mod.reset_mcp_manager()

        import threading
        results = []

        def get_mgr():
            results.append(mcp_mod.get_mcp_manager())

        threads = [threading.Thread(target=get_mgr) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 所有线程应拿到同一个实例
        assert all(r is results[0] for r in results)


# ==================== 真实 MCP 协议测试 ====================

@pytest.mark.skipif(not _have_mcp(), reason="需要 mcp SDK")
class TestRealMcpProtocol:

    """用一个简单的 mock MCP server 测试真实 JSON-RPC over stdio 协议"""

    @pytest.fixture
    def mock_mcp_server_script(self, tmp_path):
        """写一个最小的 mock MCP server 脚本(使用 mcp SDK)"""
        script = tmp_path / "mock_mcp_server.py"
        script.write_text('''
"""最简 MCP server,实现一个 echo 工具"""
import sys
from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

server = Server("mock-mcp")

@server.list_tools()
async def handle_list_tools():
    return [
        Tool(
            name="echo",
            description="回显输入文本",
            inputSchema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        ),
        Tool(
            name="add",
            description="两数相加",
            inputSchema={
                "type": "object",
                "properties": {
                    "a": {"type": "number"},
                    "b": {"type": "number"},
                },
                "required": ["a", "b"],
            },
        ),
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict):
    if name == "echo":
        return [TextContent(type="text", text=arguments.get("text", ""))]
    elif name == "add":
        result = arguments["a"] + arguments["b"]
        return [TextContent(type="text", text=str(result))]
    return [TextContent(type="text", text=f"unknown tool: {name}")]

async def main():
    async with mcp.server.stdio.stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())

import asyncio
asyncio.run(main())
''')
        return str(script)

    def test_get_tools_real_mcp(self, mock_mcp_server_script):
        """真实 MCP 协议:连接 mock server 获取工具列表"""
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {}
        mgr = MCPServerManager(cfg=cfg)
        mgr.add_server(
            "mock",
            "stdio",
            command=sys.executable,
            args=[mock_mcp_server_script],
        )

        tools = mgr.get_tools("mock")
        assert len(tools) >= 2
        tool_names = [t["name"] for t in tools]
        assert "echo" in tool_names
        assert "add" in tool_names
        # 描述应存在
        for tool in tools:
            assert tool.get("description")
            assert tool.get("inputSchema")
            assert tool.get("server") == "mock"

    def test_call_tool_real_mcp(self, mock_mcp_server_script):
        """真实 MCP 协议:调用 echo 工具"""
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {}
        mgr = MCPServerManager(cfg=cfg)
        mgr.add_server(
            "mock",
            "stdio",
            command=sys.executable,
            args=[mock_mcp_server_script],
        )

        result, err = mgr.call_tool_sync("mock", "echo", {"text": "hello fr-cli"})
        assert err is None, f"err: {err}"
        assert result == "hello fr-cli"

    def test_call_tool_add_numbers(self, mock_mcp_server_script):
        """真实 MCP 协议:调用 add 工具计算"""
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {}
        mgr = MCPServerManager(cfg=cfg)
        mgr.add_server(
            "mock",
            "stdio",
            command=sys.executable,
            args=[mock_mcp_server_script],
        )

        result, err = mgr.call_tool_sync("mock", "add", {"a": 3, "b": 5})
        assert err is None
        assert result == "8"

    def test_call_unknown_tool(self, mock_mcp_server_script):
        """调用不存在的工具"""
        from fr_cli.weapon.mcp import MCPServerManager
        cfg = {}
        mgr = MCPServerManager(cfg=cfg)
        mgr.add_server(
            "mock",
            "stdio",
            command=sys.executable,
            args=[mock_mcp_server_script],
        )

        # mock server 返回 unknown tool 文本而不是抛错
        result, err = mgr.call_tool_sync("mock", "nonexistent_tool", {})
        # 取决于 mock server 实现,可能 ok 也可能 err
        assert result is not None or err is not None
