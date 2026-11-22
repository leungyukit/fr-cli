"""
Gatekeeper 守护进程管理器测试

覆盖生命周期 + 守护进程累积修复（与 Hermes 同款机制，无端口探测）：
- 身份校验（pid 回收不误报「在运行」）
- 收养（pid 文件丢失时找到现存守护进程，而不是再 spawn 一个）
- spawn 卫生（独立会话 + stderr 落日志）
"""
import subprocess
import sys
import time
from unittest.mock import patch, MagicMock

import pytest

from fr_cli.gatekeeper import manager as manager_module
from fr_cli.gatekeeper.manager import GatekeeperManager


@pytest.fixture
def isolated_manager(tmp_path, monkeypatch):
    """提供使用临时 PID/STOP/LOG 路径的管理器"""
    pid_file = tmp_path / "daemon.pid"
    stop_file = tmp_path / "daemon.stop"
    log_file = tmp_path / "daemon.log"
    monkeypatch.setattr(manager_module, "PID_FILE", pid_file)
    monkeypatch.setattr(manager_module, "STOP_FILE", stop_file)
    monkeypatch.setattr(manager_module, "LOG_FILE", log_file)

    # 配置读写也隔离到 tmp 目录
    import fr_cli.conf.paths as paths_mod
    fake_root = tmp_path / "home" / ".fr_cli"
    fake_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(paths_mod._root_holder, "value", fake_root)

    mgr = GatekeeperManager()
    monkeypatch.setattr(mgr, "_scan_daemon_pids", lambda: [])
    return mgr


def _write_pid(pid):
    manager_module.PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    manager_module.PID_FILE.write_text(str(pid), encoding="utf-8")


class TestGatekeeperManagerLifecycle:
    def test_status_not_running(self, isolated_manager):
        assert "未运行" in isolated_manager.status()
        assert isolated_manager.is_running() is False

    def test_stop_when_not_running(self, isolated_manager):
        assert isolated_manager.stop().is_fail()

    def test_start_writes_pid(self, isolated_manager, tmp_path, monkeypatch):
        daemon_script = tmp_path / "daemon.py"
        daemon_script.write_text("# dummy script\n", encoding="utf-8")
        monkeypatch.setattr(
            isolated_manager, "_daemon_script_path", lambda: daemon_script
        )

        def _fake_popen(args, **kwargs):
            _write_pid(12345)
            return MagicMock(poll=lambda: None)

        monkeypatch.setattr(isolated_manager, "_pid_is_daemon", lambda pid: True)
        with patch("subprocess.Popen", side_effect=_fake_popen):
            result = isolated_manager.start()

        assert result.is_ok()
        assert isolated_manager.is_running() is True

    def test_stop_sends_stop_marker(self, isolated_manager, monkeypatch):
        _write_pid(12345)

        alive_calls = {"count": 0}

        def _fake_alive(pid):
            alive_calls["count"] += 1
            return alive_calls["count"] < 3

        monkeypatch.setattr(isolated_manager, "_pid_is_daemon", lambda pid: True)
        monkeypatch.setattr(isolated_manager, "_is_pid_alive", _fake_alive)
        result = isolated_manager.stop()
        assert result.is_ok()
        assert not manager_module.STOP_FILE.exists()


class TestGatekeeperManagerSpawnHygiene:
    def test_start_spawns_detached_with_stderr_log(
        self, isolated_manager, tmp_path, monkeypatch
    ):
        daemon_script = tmp_path / "daemon.py"
        daemon_script.write_text("# dummy script\n", encoding="utf-8")
        monkeypatch.setattr(
            isolated_manager, "_daemon_script_path", lambda: daemon_script
        )

        captured = {}

        def _fake_popen(args, **kwargs):
            captured.update(kwargs)
            _write_pid(777)
            return MagicMock(poll=lambda: None)

        monkeypatch.setattr(isolated_manager, "_pid_is_daemon", lambda pid: True)
        with patch("subprocess.Popen", side_effect=_fake_popen):
            result = isolated_manager.start()

        assert result.is_ok()
        assert captured.get("start_new_session") is True
        assert captured.get("close_fds") is True
        assert hasattr(captured.get("stderr"), "write")


class TestGatekeeperManagerHardening:
    def test_dead_pid_cleans_pid_file(self, isolated_manager):
        _write_pid(999999)
        assert isolated_manager.is_running() is False
        assert not manager_module.PID_FILE.exists()

    def test_recycled_pid_not_treated_as_running(self, isolated_manager, monkeypatch):
        """pid 被系统回收到别的进程：不能误报「在运行」"""
        _write_pid(12345)
        monkeypatch.setattr(isolated_manager, "_pid_is_daemon", lambda pid: False)
        assert isolated_manager.is_running() is False
        assert not manager_module.PID_FILE.exists()

    def test_adopts_daemon_when_pid_file_missing(self, isolated_manager, monkeypatch):
        """pid 文件丢失但守护进程活着：收养，而不是再 spawn 一个"""
        monkeypatch.setattr(isolated_manager, "_scan_daemon_pids", lambda: [4242])
        assert isolated_manager.is_running() is True
        assert isolated_manager._read_pid() == 4242

    def test_adopts_daemon_when_pid_recycled(self, isolated_manager, monkeypatch):
        _write_pid(12345)
        monkeypatch.setattr(isolated_manager, "_pid_is_daemon", lambda pid: False)
        monkeypatch.setattr(isolated_manager, "_scan_daemon_pids", lambda: [4242])
        assert isolated_manager.is_running() is True
        assert isolated_manager._read_pid() == 4242

    def test_start_refuses_when_daemon_running(self, isolated_manager, monkeypatch):
        monkeypatch.setattr(isolated_manager, "_scan_daemon_pids", lambda: [4242])
        result = isolated_manager.start()
        assert result.is_fail()
        assert "已在运行" in (result.error or "")

    def test_adopts_real_process_with_marker(self, isolated_manager, monkeypatch):
        """真进程 + 真 ps 扫描：命令行含标记的进程被收养，退出后自愈"""
        from fr_cli.core import procutil

        marker = "fr-cli-gatekeeper-manager-test-4712"
        monkeypatch.setattr(isolated_manager, "_daemon_marker", lambda: marker)
        monkeypatch.setattr(
            isolated_manager, "_scan_daemon_pids", lambda: procutil.scan_daemon_pids(marker)
        )
        proc = subprocess.Popen(
            [sys.executable, "-c", f"import time; time.sleep(30)  # {marker}"]
        )
        try:
            assert isolated_manager.is_running() is True
            assert isolated_manager._read_pid() == proc.pid
            proc.terminate()
            proc.wait(timeout=5)
            assert isolated_manager.is_running() is False
            assert not manager_module.PID_FILE.exists()
        finally:
            if proc.poll() is None:
                proc.kill()

    def test_save_daemon_config_skips_unchanged(self, monkeypatch):
        writes = []

        class _Store:
            def read(self):
                return {"cron_jobs": []}

            def write(self, cfg):
                writes.append(cfg)

        monkeypatch.setattr(manager_module, "_daemon_store", lambda: _Store())
        assert GatekeeperManager.save_daemon_config({"cron_jobs": []}).is_ok()
        assert writes == []
        assert GatekeeperManager.save_daemon_config({"cron_jobs": [{"cmd": "x"}]}).is_ok()
        assert len(writes) == 1


class TestGatekeeperManagerDaemonOwnership:
    """跨实例误收养修复：spawn 带归属标记 + 收养只认本实例（与 Hermes 同款）"""

    def test_spawn_cmdline_carries_home_marker(
        self, isolated_manager, tmp_path, monkeypatch
    ):
        import fr_cli.conf.paths as paths_mod

        daemon_script = tmp_path / "daemon.py"
        daemon_script.write_text("# dummy script\n", encoding="utf-8")
        monkeypatch.setattr(
            isolated_manager, "_daemon_script_path", lambda: daemon_script
        )

        captured = {}

        def _fake_popen(args, **kwargs):
            captured["args"] = args
            _write_pid(555)
            return MagicMock(poll=lambda: None)

        monkeypatch.setattr(isolated_manager, "_pid_is_daemon", lambda pid: True)
        with patch("subprocess.Popen", side_effect=_fake_popen):
            result = isolated_manager.start()

        assert result.is_ok()
        args = captured["args"]
        assert manager_module.DAEMON_HOME_FLAG in args
        idx = args.index(manager_module.DAEMON_HOME_FLAG)
        assert args[idx + 1] == str(paths_mod.ROOT)
        assert args[1] == str(daemon_script)

    def test_scan_passes_home_filter(self, isolated_manager, monkeypatch):
        """收养扫描必须带归属过滤，避免抢别的实例（含沙盒 HOME）的 daemon"""
        import fr_cli.conf.paths as paths_mod

        seen = {}

        def _fake_scan(marker, home=None, exclude_pid=None):
            seen["marker"] = marker
            seen["home"] = home
            return []

        monkeypatch.setattr(manager_module, "scan_daemon_pids", _fake_scan)
        GatekeeperManager._scan_daemon_pids(isolated_manager)
        assert seen["home"] == str(paths_mod.ROOT)
        assert seen["marker"]

    def test_foreign_daemon_not_adopted(self, isolated_manager, monkeypatch):
        """别的实例（不同 home）的 daemon 不得被收养"""
        from fr_cli.core import procutil

        marker = "fr-cli-gatekeeper-foreign-test-8899"
        foreign_home = "/tmp/fr-gatekeeper-foreign/.fr_cli"
        monkeypatch.setattr(isolated_manager, "_daemon_marker", lambda: marker)
        monkeypatch.setattr(
            isolated_manager, "_scan_daemon_pids",
            GatekeeperManager._scan_daemon_pids.__get__(isolated_manager),
        )
        proc = subprocess.Popen(
            [sys.executable, "-c",
             f"import time; time.sleep(30)  # {marker} {procutil.DAEMON_HOME_FLAG} {foreign_home}"]
        )
        try:
            for _ in range(50):
                if marker in (procutil.pid_cmdline(proc.pid) or ""):
                    break
                time.sleep(0.1)
            assert isolated_manager._scan_daemon_pids() == []
            assert isolated_manager.is_running() is False
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()

    def test_own_daemon_adopted(self, isolated_manager, monkeypatch):
        """归属本实例的 daemon 正常收养（回归：修复不能把收养能力修没）"""
        from fr_cli.core import procutil

        marker = "fr-cli-gatekeeper-own-test-8900"
        own_home = str(isolated_manager._daemon_home())
        monkeypatch.setattr(isolated_manager, "_daemon_marker", lambda: marker)
        monkeypatch.setattr(
            isolated_manager, "_scan_daemon_pids",
            GatekeeperManager._scan_daemon_pids.__get__(isolated_manager),
        )
        proc = subprocess.Popen(
            [sys.executable, "-c",
             f"import time; time.sleep(30)  # {marker} {procutil.DAEMON_HOME_FLAG} {own_home}"]
        )
        try:
            for _ in range(50):
                if marker in (procutil.pid_cmdline(proc.pid) or ""):
                    break
                time.sleep(0.1)
            assert isolated_manager._scan_daemon_pids() == [proc.pid]
            assert isolated_manager.is_running() is True
            assert isolated_manager._read_pid() == proc.pid
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
