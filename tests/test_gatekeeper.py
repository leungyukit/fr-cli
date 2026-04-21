"""
Gatekeeper 守护进程系统测试
验证守护进程的启动、停止、状态查询及配置持久化。
"""
import sys
import os
import time
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from fr_cli.gatekeeper.manager import GatekeeperManager, DAEMON_CONFIG_FILE, PID_FILE


class TestGatekeeperManager(unittest.TestCase):
    """Gatekeeper 管理器单元测试"""

    def setUp(self):
        self.gk = GatekeeperManager()
        # 清理可能的残留状态
        self.gk._cleanup_files()

    def tearDown(self):
        # 如果守护进程还在运行则停止
        if self.gk.is_running():
            self.gk.stop()
        self.gk._cleanup_files()

    def test_status_when_not_running(self):
        """未启动时应返回未运行状态"""
        status = self.gk.status()
        self.assertIn("未运行", status)

    def test_is_running_when_not_running(self):
        """未启动时 is_running 应返回 False"""
        self.assertFalse(self.gk.is_running())

    def test_save_daemon_config(self):
        """配置保存与加载"""
        cfg = {
            "agent_server_port": 18080,
            "cron_jobs": [
                {"id": 1, "cmd": "/ls", "interval": 60}
            ],
            "lang": "zh"
        }
        ok, msg = self.gk.save_daemon_config(cfg)
        self.assertTrue(ok)
        self.assertTrue(DAEMON_CONFIG_FILE.exists())

        # 验证内容
        from fr_cli.gatekeeper.daemon import _load_daemon_config as _daemon_load
        loaded = _daemon_load()
        self.assertEqual(loaded.get("agent_server_port"), 18080)
        self.assertEqual(len(loaded.get("cron_jobs", [])), 1)

    def test_start_stop_cycle(self):
        """启动-停止完整周期"""
        # 先保存一个空配置，避免守护进程因配置问题退出
        ok, _ = self.gk.save_daemon_config({"agent_server_port": None, "cron_jobs": []})
        self.assertTrue(ok)

        # 启动
        ok, msg = self.gk.start()
        self.assertTrue(ok, msg)
        self.assertTrue(self.gk.is_running())
        self.assertIn("运行", self.gk.status())

        # 再次启动应失败
        ok, msg = self.gk.start()
        self.assertFalse(ok)
        self.assertIn("已在运行", msg)

        # 停止
        ok, msg = self.gk.stop()
        self.assertTrue(ok, msg)
        self.assertFalse(self.gk.is_running())

    def test_stop_when_not_running(self):
        """未运行时停止应返回失败"""
        ok, msg = self.gk.stop()
        self.assertFalse(ok)
        self.assertIn("未运行", msg)

    def test_cleanup_dead_pid(self):
        """残留的死 PID 文件应被自动清理"""
        # 写入一个不存在的 PID
        fake_pid = 99999
        PID_FILE.write_text(str(fake_pid), encoding="utf-8")
        self.assertFalse(self.gk.is_running())
        self.assertFalse(PID_FILE.exists())


class TestGatekeeperDaemon(unittest.TestCase):
    """守护进程本体测试"""

    def test_daemon_import(self):
        """守护进程模块应可正常导入"""
        from fr_cli.gatekeeper import daemon
        self.assertTrue(hasattr(daemon, "run_daemon"))

    def test_load_daemon_config_empty(self):
        """无配置时加载应返回空字典"""
        from fr_cli.gatekeeper.daemon import _load_daemon_config, DAEMON_CONFIG_FILE
        # 确保无残留配置
        if DAEMON_CONFIG_FILE.exists():
            DAEMON_CONFIG_FILE.unlink()
        cfg = _load_daemon_config()
        self.assertEqual(cfg, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
