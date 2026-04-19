"""
测试本地应用启动器
"""
import unittest
from unittest.mock import patch, MagicMock

from fr_cli.weapon.launcher import (
    _resolve_app, open_file, launch_app, list_apps, SYSTEM
)



class TestResolveApp(unittest.TestCase):
    def test_chrome_alias(self):
        if SYSTEM == "Darwin":
            self.assertEqual(_resolve_app("chrome"), "Google Chrome")
        elif SYSTEM == "Windows":
            self.assertEqual(_resolve_app("chrome"), "chrome")
        else:
            self.assertEqual(_resolve_app("chrome"), "google-chrome")

    def test_unknown_app(self):
        self.assertEqual(_resolve_app("unknown_app_xyz"), "unknown_app_xyz")

    def test_case_insensitive(self):
        if SYSTEM == "Darwin":
            self.assertEqual(_resolve_app("CHROME"), "Google Chrome")


class TestOpenFile(unittest.TestCase):
    @patch("fr_cli.weapon.launcher.subprocess.Popen")
    def test_open_path(self, mock_popen):
        ok, msg = open_file("/tmp/test.txt", "zh")
        self.assertTrue(ok)
        self.assertIn("已打开", msg)
        mock_popen.assert_called_once()

    @patch("fr_cli.weapon.launcher.subprocess.Popen")
    def test_open_url(self, mock_popen):
        ok, msg = open_file("https://example.com", "en")
        self.assertTrue(ok)
        self.assertIn("Opened", msg)

    def test_open_empty(self):
        ok, msg = open_file("", "zh")
        self.assertFalse(ok)
        self.assertIn("路径为空", msg)


class TestLaunchApp(unittest.TestCase):
    @patch("fr_cli.weapon.launcher.subprocess.Popen")
    def test_launch_browser(self, mock_popen):
        ok, msg = launch_app("chrome", "https://example.com", "zh")
        self.assertTrue(ok)
        self.assertIn("已启动", msg)
        mock_popen.assert_called_once()

    @patch("fr_cli.weapon.launcher.subprocess.Popen")
    def test_launch_without_target(self, mock_popen):
        ok, msg = launch_app("微信", None, "zh")
        self.assertTrue(ok)
        self.assertIn("已启动", msg)

    def test_launch_empty(self):
        ok, msg = launch_app("", None, "zh")
        self.assertFalse(ok)
        self.assertIn("应用名称为空", msg)


class TestListApps(unittest.TestCase):
    def test_list_apps(self):
        res, err = list_apps("zh")
        self.assertIsNone(err)
        self.assertIn("本机可用应用映射", res)


class TestLauncherIntegration(unittest.TestCase):
    """集成测试：验证 launcher 模块可被注册表正确导入和调用"""

    def test_registry_has_tools(self):
        from fr_cli.command.registry import get_registry
        reg = get_registry()
        tools = reg.get_tools()
        names = [t["name"] for t in tools]
        self.assertIn("open_file", names)
        self.assertIn("launch_app", names)
        self.assertIn("list_apps", names)

    def test_registry_aliases(self):
        from fr_cli.command.registry import get_registry
        reg = get_registry()
        self.assertEqual(reg._aliases.get("open"), "open_file")
        self.assertEqual(reg._aliases.get("launch"), "launch_app")
        self.assertEqual(reg._aliases.get("apps"), "list_apps")


if __name__ == "__main__":
    unittest.main()
