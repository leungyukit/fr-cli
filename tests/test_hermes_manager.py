"""
Hermes 独立守护进程管理器测试
"""
from unittest.mock import patch, MagicMock

import pytest

from fr_cli.agent.hermes_manager import HermesManager, _write_pid, STOP_FILE


@pytest.fixture
def isolated_manager(tmp_path, monkeypatch):
    """提供使用临时 PID/STOP/CONFIG 路径的管理器"""
    pid_file = tmp_path / "daemon.pid"
    stop_file = tmp_path / "daemon.stop"
    cfg_file = tmp_path / "daemon.json"
    monkeypatch.setattr("fr_cli.agent.hermes_manager.PID_FILE", pid_file)
    monkeypatch.setattr("fr_cli.agent.hermes_manager.STOP_FILE", stop_file)
    monkeypatch.setattr("fr_cli.agent.hermes_manager.CONFIG_FILE", cfg_file)
    return HermesManager()


class TestHermesManagerLifecycle:
    def test_status_not_running(self, isolated_manager):
        assert "未运行" in isolated_manager.status()
        assert isolated_manager.is_running() is False

    def test_stop_when_not_running(self, isolated_manager):
        result = isolated_manager.stop()
        assert result.is_fail()

    def test_start_writes_pid_and_config(self, isolated_manager, tmp_path, monkeypatch):
        daemon_script = tmp_path / "hermes_daemon_process.py"
        daemon_script.write_text("# dummy script\n", encoding="utf-8")
        monkeypatch.setattr(
            isolated_manager, "_daemon_script_path", lambda: daemon_script
        )

        proc = MagicMock()
        proc.poll.return_value = None

        def _fake_popen(args, **kwargs):
            _write_pid(12345)
            return proc

        monkeypatch.setattr(isolated_manager, "_is_pid_alive", lambda pid: True)
        with patch("subprocess.Popen", side_effect=_fake_popen):
            result = isolated_manager.start(port=9999)

        assert result.is_ok()
        assert isolated_manager.is_running() is True

    def test_stop_sends_stop_marker(self, isolated_manager, monkeypatch):
        _write_pid(12345)

        alive_calls = {"count": 0}

        def _fake_alive(pid):
            alive_calls["count"] += 1
            return alive_calls["count"] < 3

        monkeypatch.setattr(isolated_manager, "_is_pid_alive", _fake_alive)
        result = isolated_manager.stop()
        assert result.is_ok()
        assert not STOP_FILE.exists()
