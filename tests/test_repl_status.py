"""
/status 全局状态命令测试
"""
import json
from unittest.mock import MagicMock

import pytest

from fr_cli.repl.commands.system import _cmd_status


@pytest.fixture
def mock_state():
    state = MagicMock()
    state.status_summary.return_value = {
        "provider": "zhipu",
        "model": "glm-4-flash",
        "api_key_configured": True,
        "autonomous_mode": "sandbox_auto",
        "master_agent": {"enabled": True, "total_interactions": 5},
        "agent_server": {"running": True, "status": "运行中"},
        "hermes_daemon": {"running": True, "status": "运行中 (PID: 12345)"},
        "hermes_engine": "Hermes 状态",
        "hermes_tasks": {"pending": 1, "running": 0, "completed": 2, "failed": 0, "paused": 0},
        "gatekeeper": {"running": False, "status": "未运行"},
        "review_queue": {"pending": 3, "total": 4},
        "cron_jobs": 2,
        "plugins": 5,
        "agents": 3,
        "errors": {
            "hermes_failed_tasks": [{"id": "err-1", "description": "task desc", "error": "boom"}],
            "dynamic_builder_selftest_failures": [{"id": "err-2", "source_id": "bad_tool", "error": "self-test failed"}],
            "review_queue_rejected": [{"id": "err-3", "source_id": "rev-1", "error": "rejected"}],
            "master_failure_patterns": {"top_failures": [["read_file::FileNotFound", 3]], "failure_hints": []},
        },
    }
    return state


class TestStatusCommand:
    def test_text_output(self, mock_state, capsys):
        _cmd_status(mock_state, ["/status"])
        out = capsys.readouterr().out
        assert "fr-cli 全局状态" in out
        assert "glm-4-flash" in out
        assert "Hermes 守护进程" in out
        assert "审核队列" in out

    def test_json_output(self, mock_state, capsys):
        _cmd_status(mock_state, ["/status", "json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["provider"] == "zhipu"
        assert data["hermes_tasks"]["pending"] == 1

    def test_errors_output(self, mock_state, capsys):
        _cmd_status(mock_state, ["/status", "errors"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert len(data["hermes_failed_tasks"]) == 1
        assert len(data["dynamic_builder_selftest_failures"]) == 1
        assert len(data["review_queue_rejected"]) == 1

    def test_error_summary_line(self, mock_state, capsys):
        _cmd_status(mock_state, ["/status"])
        out = capsys.readouterr().out
        assert "最近错误" in out
        assert "/status errors" in out
