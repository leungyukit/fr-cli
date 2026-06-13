"""
MCP 真实协议测试（基于 mcp SDK）
使用 tests/mcp_echo_server.py 作为 stdio 服务器。
"""
import sys
from pathlib import Path

import pytest

from fr_cli.weapon.mcp import MCPServerManager, _MCP_AVAILABLE


@pytest.fixture
def echo_server_manager(tmp_path, monkeypatch):
    """创建指向 echo 测试服务器的 MCPServerManager"""
    if not _MCP_AVAILABLE:
        pytest.skip("MCP SDK 未安装")
    server_path = str(Path(__file__).with_name("mcp_echo_server.py").resolve())
    cfg = {"mcp": {"servers": []}}
    mgr = MCPServerManager(cfg=cfg)
    mgr.add_server(
        name="echo",
        transport="stdio",
        command=sys.executable,
        args=[server_path],
    )
    return mgr


def test_mcp_get_tools(echo_server_manager):
    tools = echo_server_manager.get_tools("echo")
    assert len(tools) == 1
    assert tools[0]["name"] == "echo"
    assert "message" in tools[0]["inputSchema"]["properties"]


def test_mcp_call_tool_sync(echo_server_manager):
    result, error = echo_server_manager.call_tool_sync("echo", "echo", {"message": "hello"})
    assert error is None
    assert "hello" in result
