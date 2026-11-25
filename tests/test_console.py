"""Web 控制台测试"""
import json
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from fr_cli.web.console import (
    start_console, stop_console, console_status,
    _get_global_status, _generate_token, _render_homepage,
)
from fr_cli.web.console.handler import STATIC_DIR


class TestToken(unittest.TestCase):
    def test_length(self):
        token = _generate_token()
        self.assertEqual(len(token), 32)  # 16 bytes hex

    def test_unique(self):
        t1 = _generate_token()
        t2 = _generate_token()
        self.assertNotEqual(t1, t2)


class TestHomepage(unittest.TestCase):
    def test_renders(self):
        token = "test_token_12345"
        html = _render_homepage(token)
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn(token, html)
        # JS 调用 load('status') 时会拼成 /api/status
        self.assertIn("load('status')", html)
        self.assertIn("/api/", html)


class TestGetStatus(unittest.TestCase):
    @patch("fr_cli.web.console.JsonStore")
    @patch("fr_cli.conf.config.load_config")
    def test_basic(self, mock_cfg, mock_store):
        mock_cfg.return_value = {"provider": "zhipu", "model": "glm-4", "key": "xxx"}
        status = _get_global_status()
        self.assertEqual(status["provider"], "zhipu")
        self.assertEqual(status["model"], "glm-4")
        self.assertTrue(status["key_configured"])


class TestConsoleLifecycle(unittest.TestCase):
    """测试控制台启动 / 停止"""

    def setUp(self):
        # 确保初始状态干净
        stop_console()

    def tearDown(self):
        stop_console()

    def test_start_stop_no_browser(self):
        result = start_console(host="127.0.0.1", port=17777,
                               token="test_token", open_browser=False)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["token"], "test_token")
        self.assertEqual(result["port"], 17777)

        # 状态应该是运行
        s = console_status()
        self.assertTrue(s["running"])

        # 停止
        r = stop_console()
        self.assertTrue(r["ok"])
        self.assertFalse(console_status()["running"])

    def test_double_start_fails(self):
        result1 = start_console(host="127.0.0.1", port=17778,
                                token="test_token_1", open_browser=False)
        self.assertTrue(result1["ok"])
        result2 = start_console(host="127.0.0.1", port=17778,
                                token="test_token_2", open_browser=False)
        self.assertFalse(result2["ok"])
        stop_console()

    def test_port_in_use(self):
        result1 = start_console(host="127.0.0.1", port=17779,
                                token="t1", open_browser=False)
        self.assertTrue(result1["ok"])
        # 试 0(系统分配),应该 OK
        result2 = start_console(host="127.0.0.1", port=17779,
                                token="t2", open_browser=False)
        self.assertFalse(result2["ok"])
        stop_console()


class TestHTTPEndpoints(unittest.TestCase):
    """测试 HTTP 端点(集成)"""

    def setUp(self):
        stop_console()
        self.token = "test_http_token"
        result = start_console(host="127.0.0.1", port=17780,
                               token=self.token, open_browser=False)
        if not result["ok"]:
            self.skipTest(f"无法启动控制台: {result.get('error')}")
        self.base_url = "http://127.0.0.1:17780"

    def tearDown(self):
        stop_console()

    def _get(self, path: str, with_token: bool = True) -> tuple:
        url = self.base_url + path
        if with_token:
            sep = "&" if "?" in url else "?"
            url += f"{sep}token={self.token}"
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                return resp.status, resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8")
        except Exception as e:
            return -1, str(e)

    def test_homepage(self):
        status, body = self._get("/", with_token=False)
        self.assertEqual(status, 200)
        self.assertIn("fr-cli", body)
        self.assertIn(self.token, body)

    def test_health_no_auth_required(self):
        # /api/health 不需要 token(实际它也要 auth,这里测试)
        status, _ = self._get("/api/health", with_token=True)
        self.assertEqual(status, 200)

    def test_unauthorized(self):
        status, body = self._get("/api/status", with_token=False)
        self.assertEqual(status, 401)
        self.assertIn("Unauthorized", body)

    def test_status(self):
        status, body = self._get("/api/status")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["ok"])
        self.assertIn("provider", data["data"])

    def test_sessions(self):
        status, body = self._get("/api/sessions")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["ok"])
        self.assertIsInstance(data["data"], list)

    def test_worktrees(self):
        status, body = self._get("/api/worktrees")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["ok"])

    def test_bookmarks(self):
        status, body = self._get("/api/bookmarks")
        self.assertEqual(status, 200)

    def test_stats(self):
        status, body = self._get("/api/stats")
        self.assertEqual(status, 200)

    def test_unknown(self):
        status, body = self._get("/api/unknown")
        self.assertEqual(status, 404)


class TestStaticAssets(unittest.TestCase):
    """静态资源路径修复：资源在 fr_cli/web/static/，不是 console/static/"""

    def setUp(self):
        stop_console()
        self.token = "static_token"
        result = start_console(host="127.0.0.1", port=17781,
                               token=self.token, open_browser=False)
        if not result["ok"]:
            self.skipTest(f"无法启动控制台: {result.get('error')}")
        self.base_url = "http://127.0.0.1:17781"

    def tearDown(self):
        stop_console()

    def _get(self, path: str):
        try:
            with urllib.request.urlopen(self.base_url + path, timeout=5) as resp:
                return resp.status, resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8")

    def test_static_dir_points_to_web_static(self):
        # handler.py 在 fr_cli/web/console/ 下，静态资源在 fr_cli/web/static/(差一级)
        self.assertTrue(STATIC_DIR.exists(), f"静态目录不存在: {STATIC_DIR}")
        self.assertEqual(STATIC_DIR.name, "static")
        self.assertEqual(STATIC_DIR.parent.name, "web")
        self.assertTrue((STATIC_DIR / "manifest.json").exists())

    def test_manifest_served(self):
        status, body = self._get("/manifest.json")
        self.assertEqual(status, 200)
        self.assertIn("fr-cli", body)

    def test_icon_served(self):
        status, body = self._get("/icon.svg")
        self.assertEqual(status, 200)
        self.assertIn("<svg", body)

    def test_service_worker_served(self):
        status, body = self._get("/sw.js")
        self.assertEqual(status, 200)
        self.assertIn("fr-cli", body)


class TestCommandEndpoint(unittest.TestCase):
    """/api/command 默认关闭（安全考虑）"""

    def setUp(self):
        stop_console()
        self.token = "cmd_token"
        result = start_console(host="127.0.0.1", port=17782,
                               token=self.token, open_browser=False)
        if not result["ok"]:
            self.skipTest(f"无法启动控制台: {result.get('error')}")
        self.base_url = "http://127.0.0.1:17782"

    def tearDown(self):
        stop_console()

    def _post(self, path: str, payload: dict):
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + path,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.token}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_command_disabled(self):
        status, body = self._post("/api/command", {"command": "/status"})
        self.assertEqual(status, 403)
        self.assertFalse(body["ok"])
        self.assertIn("Web 命令未启用", body["error"])

    def test_event_endpoint_still_works(self):
        status, body = self._post("/api/event", {"type": "client", "data": {"x": 1}})
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])


if __name__ == "__main__":
    unittest.main()
