"""
Agent 客户端测试 —— 本地/远程 Agent 调用与发现
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class MockState:
    def __init__(self):
        self.client = MagicMock()
        self.model_name = "glm-4-flash"
        self.lang = "zh"
        self.executor = MagicMock()


class TestAgentRemote(unittest.TestCase):
    """测试远程 Agent 配置管理"""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        from fr_cli.agent import remote as remote_mod
        self._orig_file = remote_mod.REMOTE_AGENTS_FILE
        remote_mod.REMOTE_AGENTS_FILE = Path(self.tmpdir.name) / "remote_agents.json"

    def tearDown(self):
        self.tmpdir.cleanup()
        from fr_cli.agent import remote as remote_mod
        remote_mod.REMOTE_AGENTS_FILE = self._orig_file

    def test_add_and_list_remote_agent(self):
        from fr_cli.agent.remote import add_remote_agent, list_remote_agents
        add_remote_agent("data_analyst", "192.168.1.100", 8080, "tok123", "数据分析助手")
        agents = list_remote_agents()
        self.assertIn("data_analyst", agents)
        self.assertEqual(agents["data_analyst"]["host"], "192.168.1.100")
        self.assertEqual(agents["data_analyst"]["port"], 8080)
        self.assertEqual(agents["data_analyst"]["token"], "tok123")

    def test_remove_remote_agent(self):
        from fr_cli.agent.remote import add_remote_agent, remove_remote_agent, list_remote_agents
        add_remote_agent("test_agent", "127.0.0.1", 9090, "abc")
        self.assertTrue(remove_remote_agent("test_agent"))
        self.assertEqual(list_remote_agents(), {})
        self.assertFalse(remove_remote_agent("not_exist"))

    def test_get_remote_agent(self):
        from fr_cli.agent.remote import add_remote_agent, get_remote_agent
        add_remote_agent("web_crawler", "10.0.0.5", 17890, "secret", "爬虫助手")
        cfg = get_remote_agent("web_crawler")
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg["port"], 17890)
        self.assertIsNone(get_remote_agent("not_exist"))


class TestAgentClient(unittest.TestCase):
    """测试 Agent API 客户端"""

    def test_discover_all_agents(self):
        from fr_cli.agent.client import discover_all_agents
        agents = discover_all_agents()
        # 返回列表格式检查
        self.assertIsInstance(agents, list)
        for a in agents:
            self.assertIn("name", a)
            self.assertIn("type", a)
            self.assertIn(a["type"], ("local", "remote"))

    def test_call_local_agent_not_found(self):
        from fr_cli.agent.client import call_agent
        state = MockState()
        result, err = call_agent("nonexistent_agent_xyz", state, user_input="hello")
        self.assertIsNone(result)
        self.assertIn("未找到", err)

    @patch("fr_cli.agent.client.urllib.request.urlopen")
    def test_call_remote_agent_success(self, mock_urlopen):
        from fr_cli.agent.client import call_remote_agent
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"result": "远程分析完成", "error": None}).encode()
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        cfg = {"host": "192.168.1.50", "port": 8080, "token": "tok456"}
        result, err = call_remote_agent("data_bot", "分析销售数据", cfg)
        self.assertEqual(result, "远程分析完成")
        self.assertIsNone(err)

        # 验证请求构造
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.full_url, "http://192.168.1.50:8080/agents/data_bot/run")
        self.assertEqual(req.headers.get("Authorization"), "Bearer tok456")

    @patch("fr_cli.agent.client.urllib.request.urlopen")
    def test_call_remote_agent_http_error(self, mock_urlopen):
        from fr_cli.agent.client import call_remote_agent
        from urllib.error import HTTPError
        mock_urlopen.side_effect = HTTPError(
            "http://test/agents/x/run", 401, "Unauthorized", {}, None
        )
        cfg = {"host": "test", "port": 80, "token": "bad"}
        result, err = call_remote_agent("x", "hi", cfg)
        self.assertIsNone(result)
        self.assertIn("401", err)


if __name__ == "__main__":
    unittest.main()
