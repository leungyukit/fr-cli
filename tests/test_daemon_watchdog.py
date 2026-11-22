"""
守护进程启动看门狗测试

看门狗把「初始化阶段永久挂起」变成「限时自毁 + 下次干净重启」，
直接切断「挂起的守护进程不写 pid 文件 → 每次启动 fr-cli 都再 spawn
一个 → 进程无限累积」的链条。

另外验证：被当库 import（如 pytest）时不会布防，
否则会给宿主进程装上定时自裁的炸弹。
"""
import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HERMES_MODULE = "fr_cli.agent.hermes_daemon_process"
GATEKEEPER_MODULE = "fr_cli.gatekeeper.daemon"


def _run_hung_daemon(tmp_path, module_name):
    """子进程里 import daemon 模块 → 布防看门狗 → 把初始化卡死"""
    env = dict(os.environ)
    env["HOME"] = str(tmp_path)
    env["FR_CLI_DAEMON_WATCHDOG_SECS"] = "1"
    code = (
        "import time\n"
        f"import {module_name} as m\n"
        "m._init_services = lambda cfg: time.sleep(60)\n"
        "m._arm_watchdog(1)\n"
        "m.run_daemon()\n"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=REPO_ROOT,
    )


class TestHermesDaemonWatchdog:
    def test_hung_startup_self_destructs(self, tmp_path):
        proc = _run_hung_daemon(tmp_path, HERMES_MODULE)
        assert proc.returncode == 3
        assert "看门狗" in proc.stderr


class TestGatekeeperDaemonWatchdog:
    def test_hung_startup_self_destructs(self, tmp_path):
        proc = _run_hung_daemon(tmp_path, GATEKEEPER_MODULE)
        assert proc.returncode == 3
        assert "看门狗" in proc.stderr


class TestWatchdogScriptModeOnly:
    @pytest.mark.parametrize("module_name", [HERMES_MODULE, GATEKEEPER_MODULE])
    def test_library_import_does_not_arm_fuse(self, tmp_path, module_name):
        """被当库 import 时不布防（1s 引信下存活 2.5s 即证明）"""
        env = dict(os.environ)
        env["HOME"] = str(tmp_path)
        env["FR_CLI_DAEMON_WATCHDOG_SECS"] = "1"
        code = (
            "import time\n"
            f"import {module_name} as m\n"
            "time.sleep(2.5)\n"
            "print('survived')\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=REPO_ROOT,
        )
        assert proc.returncode == 0
        assert "survived" in proc.stdout
