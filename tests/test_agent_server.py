"""
测试 Agent HTTP 服务功能
"""
import json
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fr_cli.agent.server import AgentHTTPServer, _AgentHTTPHandler
from fr_cli.agent.manager import create_agent_dir, delete_agent, _agent_dir


class MockState:
    """轻量 mock AppState"""
    def __init__(self):
        self.client = MagicMock()
        self.model_name = "glm-4-flash"
        self.lang = "zh"
        self.executor = MagicMock()


def _wait_for_server(server, timeout=2):
    for _ in range(int(timeout * 10)):
        if server.is_running():
            return True
        time.sleep(0.1)
    return False


class TestAgentHTTPServer(unittest.TestCase):

    def setUp(self):
        self.state = MockState()
        self.server = AgentHTTPServer(self.state, host="127.0.0.1", port=0)

    def tearDown(self):
        if self.server.is_running():
            self.server.stop()

    def test_start_stop(self):
        ok, msg = self.server.start()
        self.assertTrue(ok, msg)
        self.assertTrue(self.server.is_running())
        ok2, msg2 = self.server.stop()
        self.assertTrue(ok2, msg2)
        self.assertFalse(self.server.is_running())

    def test_double_start(self):
        self.server.start()
        ok, msg = self.server.start()
        self.assertFalse(ok)
        self.assertIn("已在运行", msg)
        self.server.stop()

    def test_status(self):
        self.assertIn("未运行", self.server.status())
        self.server.start()
        self.assertIn("运行中", self.server.status())
        self.server.stop()


class TestAgentHTTPHandler(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.state = MockState()
        cls.server = AgentHTTPServer(cls.state, host="127.0.0.1", port=0)
        cls.server.start()
        _wait_for_server(cls.server)
        cls.port = cls.server._server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def _request(self, method, path, data=None):
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        body = json.dumps(data) if data else None
        headers = {"Content-Type": "application/json"} if body else {}
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        status = resp.status
        resp_body = resp.read().decode("utf-8")
        conn.close()
        return status, json.loads(resp_body) if resp_body else {}

    def test_health(self):
        status, data = self._request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ok")

    def test_agents_list(self):
        status, data = self._request("GET", "/agents")
        self.assertEqual(status, 200)
        self.assertIn("agents", data)

    def test_agent_not_found(self):
        status, data = self._request("GET", "/agents/nonexistent_agent_12345")
        self.assertEqual(status, 404)
        self.assertIn("error", data)

    def test_cors_options(self):
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        conn.request("OPTIONS", "/agents")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 204)
        self.assertEqual(resp.getheader("Access-Control-Allow-Origin"), "*")
        conn.close()


class TestAgentHTTPRun(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.agent_name = "__test_http_agent__"
        d = create_agent_dir(cls.agent_name)
        (d / "agent.py").write_text("def run(ctx, **kwargs): return 'hello from ' + ctx['agent_name']", encoding="utf-8")
        cls.state = MockState()
        cls.server = AgentHTTPServer(cls.state, host="127.0.0.1", port=0)
        cls.server.start()
        _wait_for_server(cls.server)
        cls.port = cls.server._server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        delete_agent(cls.agent_name)

    def _request(self, method, path, data=None):
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.port)
        body = json.dumps(data) if data else None
        headers = {"Content-Type": "application/json"} if body else {}
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        status = resp.status
        resp_body = resp.read().decode("utf-8")
        conn.close()
        return status, json.loads(resp_body) if resp_body else {}

    def test_run_agent(self):
        status, data = self._request("POST", f"/agents/{self.agent_name}/run", {"input": "hi"})
        self.assertEqual(status, 200)
        self.assertIn("hello from", data["result"])
        self.assertIsNone(data["error"])

    def test_get_agent_info(self):
        status, data = self._request("GET", f"/agents/{self.agent_name}")
        self.assertEqual(status, 200)
        self.assertEqual(data["name"], self.agent_name)
        self.assertFalse(data["has_workflow"])


if __name__ == "__main__":
    unittest.main()
