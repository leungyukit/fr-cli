"""
procutil 测试：pid 存活 / 身份校验 / 守护进程扫描与收养。

覆盖守护进程累积修复的两块基石：
- pid_matches_daemon：pid 存活且命令行含标记（防 pid 回收误报）
- scan_daemon_pids：按标记找现存进程（收养用）

跨实例误收养修复：
- spawn 时命令行带 --fr-cli-daemon-home 归属标记
- 收养/身份校验时比对归属，别的实例（含沙盒 HOME）与旧版无标记
  daemon 都不认
"""
import os
import subprocess
import sys
import time

import pytest

from fr_cli.core import procutil

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="依赖 POSIX ps"
)


class TestPidAlive:
    def test_self_pid_alive(self):
        assert procutil.pid_alive(os.getpid()) is True

    def test_bogus_pid_not_alive(self):
        assert procutil.pid_alive(999999) is False

    def test_invalid_pid_not_alive(self):
        assert procutil.pid_alive(None) is False
        assert procutil.pid_alive("abc") is False
        assert procutil.pid_alive(-1) is False
        assert procutil.pid_alive(0) is False


@pytest.fixture
def sleeper():
    """起一个真进程，命令行带唯一标记（模拟守护进程）"""
    marker = "fr-cli-procutil-test-31337"
    proc = subprocess.Popen(
        [sys.executable, "-c", f"import time; time.sleep(30)  # {marker}"]
    )
    # 等 ps 能看到它
    for _ in range(50):
        if marker in (procutil.pid_cmdline(proc.pid) or ""):
            break
        time.sleep(0.1)
    yield proc, marker
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()


class TestPidCmdline:
    def test_reads_own_cmdline(self, sleeper):
        proc, marker = sleeper
        assert marker in (procutil.pid_cmdline(proc.pid) or "")

    def test_dead_pid_returns_none(self):
        assert procutil.pid_cmdline(999999) is None


class TestPidMatchesDaemon:
    def test_matches_when_cmdline_has_marker(self, sleeper):
        proc, marker = sleeper
        assert procutil.pid_matches_daemon(proc.pid, marker) is True

    def test_no_match_when_marker_absent(self, sleeper):
        proc, marker = sleeper
        assert procutil.pid_matches_daemon(proc.pid, "no-such-marker-xyz") is False

    def test_dead_pid_never_matches(self, sleeper):
        proc, marker = sleeper
        proc.terminate()
        proc.wait(timeout=5)
        assert procutil.pid_matches_daemon(proc.pid, marker) is False

    def test_self_pid_never_matches(self):
        assert procutil.pid_matches_daemon(os.getpid(), "python") is False

    def test_invalid_pid_never_matches(self):
        assert procutil.pid_matches_daemon(None, "x") is False
        assert procutil.pid_matches_daemon("abc", "x") is False


class TestScanDaemonPids:
    def test_scan_finds_marked_process(self, sleeper):
        proc, marker = sleeper
        assert proc.pid in procutil.scan_daemon_pids(marker)

    def test_scan_empty_for_absent_marker(self):
        assert procutil.scan_daemon_pids("definitely-not-a-real-marker-987654") == []

    def test_scan_excludes_self(self, sleeper):
        _proc, marker = sleeper
        assert os.getpid() not in procutil.scan_daemon_pids(marker)

    def test_scan_empty_marker(self):
        assert procutil.scan_daemon_pids("") == []

    def test_scan_stops_finding_after_exit(self, sleeper):
        proc, marker = sleeper
        assert proc.pid in procutil.scan_daemon_pids(marker)
        proc.terminate()
        proc.wait(timeout=5)
        assert proc.pid not in procutil.scan_daemon_pids(marker)


class TestDaemonHomeOfCmdline:
    """归属标记提取"""

    def test_extracts_flag_value(self):
        cmd = "/usr/bin/python /repo/fr_cli/agent/hermes_daemon_process.py --fr-cli-daemon-home /Users/x/.fr_cli"
        assert procutil.daemon_home_of_cmdline(cmd) == "/Users/x/.fr_cli"

    def test_extracts_equals_form(self):
        cmd = "python daemon.py --fr-cli-daemon-home=/tmp/h/.fr_cli"
        assert procutil.daemon_home_of_cmdline(cmd) == "/tmp/h/.fr_cli"

    def test_none_without_flag(self):
        assert procutil.daemon_home_of_cmdline("python /repo/daemon.py") is None

    def test_none_for_empty(self):
        assert procutil.daemon_home_of_cmdline("") is None
        assert procutil.daemon_home_of_cmdline(None) is None

    def test_flag_without_value(self):
        assert procutil.daemon_home_of_cmdline("python daemon.py --fr-cli-daemon-home") is None


@pytest.fixture
def owned_sleepers():
    """三个真进程：实例 A 的 daemon、实例 B 的 daemon、旧版无标记 daemon"""
    marker = "fr-cli-procutil-owner-test-4711"
    home_a = "/tmp/fr-owner-a/.fr_cli"
    home_b = "/tmp/fr-owner-b/.fr_cli"
    procs = [
        subprocess.Popen(
            [sys.executable, "-c",
             f"import time; time.sleep(30)  # {marker} {procutil.DAEMON_HOME_FLAG} {home_a}"]
        ),
        subprocess.Popen(
            [sys.executable, "-c",
             f"import time; time.sleep(30)  # {marker} {procutil.DAEMON_HOME_FLAG} {home_b}"]
        ),
        # 旧版 daemon：spawn 时没有归属标记
        subprocess.Popen(
            [sys.executable, "-c", f"import time; time.sleep(30)  # {marker}"]
        ),
    ]
    for _ in range(50):
        if all(marker in (procutil.pid_cmdline(p.pid) or "") for p in procs):
            break
        time.sleep(0.1)
    yield (marker, home_a, home_b), procs
    for p in procs:
        p.terminate()
        try:
            p.wait(timeout=5)
        except Exception:
            p.kill()


class TestDaemonHomeOwnership:
    """跨实例误收养修复：收养/身份校验按归属过滤"""

    def test_scan_only_own_home(self, owned_sleepers):
        """A 实例的扫描只看到自己的 daemon，不抢 B 实例的"""
        (marker, home_a, home_b), procs = owned_sleepers
        found_a = procutil.scan_daemon_pids(marker, home=home_a)
        found_b = procutil.scan_daemon_pids(marker, home=home_b)
        assert procs[0].pid in found_a
        assert procs[1].pid not in found_a
        assert procs[1].pid in found_b
        assert procs[0].pid not in found_b

    def test_scan_without_home_finds_all(self, owned_sleepers):
        """不传 home 时退回纯标记扫描（旧语义，供诊断用）"""
        (marker, _a, _b), procs = owned_sleepers
        found = procutil.scan_daemon_pids(marker)
        for p in procs:
            assert p.pid in found

    def test_legacy_daemon_not_adopted_by_any_home(self, owned_sleepers):
        """旧版无归属标记的 daemon 不被任何实例收养（归属不可知 → 不抢）"""
        (marker, home_a, home_b), procs = owned_sleepers
        assert procs[2].pid not in procutil.scan_daemon_pids(marker, home=home_a)
        assert procs[2].pid not in procutil.scan_daemon_pids(marker, home=home_b)

    def test_pid_matches_respects_home(self, owned_sleepers):
        (marker, home_a, home_b), procs = owned_sleepers
        assert procutil.pid_matches_daemon(procs[0].pid, marker, home=home_a) is True
        assert procutil.pid_matches_daemon(procs[0].pid, marker, home=home_b) is False
        # 无 home 参数时只校验脚本标记（pid 文件路径用，见 manager._pid_is_daemon）
        assert procutil.pid_matches_daemon(procs[0].pid, marker) is True

    def test_pid_matches_rejects_legacy_when_home_given(self, owned_sleepers):
        (marker, home_a, _b), procs = owned_sleepers
        assert procutil.pid_matches_daemon(procs[2].pid, marker, home=home_a) is False

    def test_scan_excludes_self_with_home(self, owned_sleepers):
        (marker, home_a, _b), _procs = owned_sleepers
        assert os.getpid() not in procutil.scan_daemon_pids(marker, home=home_a)

    def test_scan_empty_marker_with_home(self):
        assert procutil.scan_daemon_pids("", home="/tmp/x/.fr_cli") == []
