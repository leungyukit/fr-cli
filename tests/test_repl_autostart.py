"""
/autostart 一键启动命令测试
"""
from unittest.mock import MagicMock

import pytest

from fr_cli.repl.commands.system import _cmd_autostart


@pytest.fixture
def mock_state():
    state = MagicMock()
    state.lang = "zh"

    # MasterAgent
    state.master_agent.is_enabled.return_value = False

    # Agent server
    server = MagicMock()
    server.is_running.return_value = False
    server.start.return_value = MagicMock()
    server.start.return_value.is_ok.return_value = True
    server.start.return_value.unwrap_or.return_value = "运行中: http://127.0.0.1:17890"
    state.agent_server = server

    results = {
        "master_agent": MagicMock(),
        "agent_server": MagicMock(),
        "hermes_daemon": MagicMock(),
        "gatekeeper": MagicMock(),
        "cron": MagicMock(),
    }
    for r in results.values():
        r.is_ok.return_value = True
        r.unwrap_or.return_value = "ok"
        r.is_fail.return_value = False
        r.error = None
    state.start_all_services.return_value = results
    return state


class TestAutostartCommand:
    def test_default_start(self, mock_state, capsys):
        _cmd_autostart(mock_state, ["/autostart"])
        out = capsys.readouterr().out
        assert "一键启动" in out
        assert "MasterAgent" in out
        mock_state.start_all_services.assert_called_once()

    def test_with_ports(self, mock_state, capsys):
        _cmd_autostart(mock_state, ["/autostart", "--agent-server", "9999", "--hermes", "8888"])
        args, kwargs = mock_state.start_all_services.call_args
        assert kwargs["ports"] == {"agent_server": 9999, "hermes": 8888}

    def test_partial_failure_shown(self, mock_state, capsys):
        results = mock_state.start_all_services.return_value
        results["hermes_daemon"].is_ok.return_value = False
        results["hermes_daemon"].is_fail.return_value = True
        results["hermes_daemon"].error = "端口被占用"
        _cmd_autostart(mock_state, ["/autostart"])
        out = capsys.readouterr().out
        assert "端口被占用" in out
