"""Web 控制台 SSE 实时推送测试"""
import json
import threading
import time
import unittest
import urllib.error
import urllib.request

from fr_cli.web.console import (
    start_console, stop_console,
    push_event, get_recent_events,
)


class TestPushEvent(unittest.TestCase):
    def setUp(self):
        # 清空历史
        from fr_cli.web.console import _sse_history, _sse_lock
        with _sse_lock:
            _sse_history.clear()

    def test_basic(self):
        push_event("status", {"message": "hello"})
        events = get_recent_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "status")
        self.assertEqual(events[0]["data"]["message"], "hello")

    def test_history_max(self):
        from fr_cli.web.console import _sse_history_max
        for i in range(_sse_history_max + 20):
            push_event("test", {"i": i})
        events = get_recent_events(limit=100)
        self.assertLessEqual(len(events), _sse_history_max)

    def test_multiple_types(self):
        push_event("status", {"x": 1})
        push_event("task", {"y": 2})
        push_event("log", {"z": 3})
        events = get_recent_events()
        types = [e["type"] for e in events]
        self.assertIn("status", types)
        self.assertIn("task", types)
        self.assertIn("log", types)


class TestSSEEndpoint(unittest.TestCase):
    """集成测试:SSE HTTP 端点"""

    def setUp(self):
        from fr_cli.web.console import _sse_history, _sse_lock
        with _sse_lock:
            _sse_history.clear()
        stop_console()
        self.token = "test_sse_token"
        result = start_console(host="127.0.0.1", port=17781,
                               token=self.token, open_browser=False)
        if not result["ok"]:
            self.skipTest(f"无法启动控制台: {result.get('error')}")
        self.base_url = f"http://127.0.0.1:17781"

    def tearDown(self):
        stop_console()

    def _read_sse_events(self, path: str, max_lines: int = 5,
                         timeout: float = 3.0) -> list:
        """读取 SSE 流的前几行"""
        url = f"{self.base_url}{path}?token={self.token}"
        events = []
        try:
            resp = urllib.request.urlopen(url, timeout=timeout)
            # 读几行
            start = time.time()
            while time.time() - start < timeout and len(events) < max_lines:
                line = resp.readline()
                if not line:
                    break
                line = line.decode("utf-8").rstrip()
                if line.startswith("data: ") or line.startswith("event: "):
                    events.append(line)
            resp.close()
        except Exception as e:
            pass
        return events

    def test_sse_history_on_connect(self):
        """连上 SSE 应该先收到历史事件"""
        # 先 push 一些事件
        push_event("status", {"message": "history-test"})
        events = self._read_sse_events("/api/events", max_lines=10, timeout=2.0)
        # 应该有 history-test
        all_text = "\n".join(events)
        self.assertIn("history-test", all_text)

    def test_sse_live_event(self):
        """SSE 应该能收到 push 的实时事件"""
        # 起一个后台线程做 push
        def push_later():
            time.sleep(0.5)
            push_event("task", {"task_id": "live-test", "status": "running"})

        threading.Thread(target=push_later, daemon=True).start()

        events = self._read_sse_events("/api/events", max_lines=20, timeout=3.0)
        all_text = "\n".join(events)
        # 应该看到 live-test
        self.assertIn("live-test", all_text)

    def test_sse_unauthorized(self):
        """不带 token 应该 401"""
        url = f"{self.base_url}/api/events"
        try:
            urllib.request.urlopen(url, timeout=2)
            self.fail("应该 401")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 401)


class TestPostEvent(unittest.TestCase):
    """测试 POST /api/event 接收客户端事件"""

    def setUp(self):
        from fr_cli.web.console import _sse_history, _sse_lock
        with _sse_lock:
            _sse_history.clear()
        stop_console()
        self.token = "test_post_token"
        result = start_console(host="127.0.0.1", port=17782,
                               token=self.token, open_browser=False)
        if not result["ok"]:
            self.skipTest(f"无法启动控制台: {result.get('error')}")

    def tearDown(self):
        stop_console()

    def test_post_event(self):
        url = f"http://127.0.0.1:17782/api/event?token={self.token}"
        data = json.dumps({"type": "client", "data": {"msg": "from-test"}}).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST",
                                    headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=5)
        self.assertEqual(resp.status, 200)
        resp.close()

        # 事件应该被 push
        events = get_recent_events()
        types = [e["type"] for e in events]
        self.assertIn("client", types)


if __name__ == "__main__":
    unittest.main()