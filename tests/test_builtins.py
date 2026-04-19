"""
测试内置 Agent 分身（@local / @remote / @spider）
"""
import unittest
from unittest.mock import patch, MagicMock

from fr_cli.agent.builtins.remote import _load_hosts, _save_hosts, list_hosts, save_host, delete_host
from fr_cli.agent.builtins.spider import _sanitize_filename, _extract_links


class TestRemoteManager(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp_cfg = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        self.tmp_cfg.write('{}')
        self.tmp_cfg.close()
        self._orig_path = __import__('fr_cli.agent.builtins.remote', fromlist=['REMOTE_CFG_PATH']).REMOTE_CFG_PATH
        import fr_cli.agent.builtins.remote as remote_mod
        remote_mod.REMOTE_CFG_PATH = __import__('pathlib').Path(self.tmp_cfg.name)

    def tearDown(self):
        import fr_cli.agent.builtins.remote as remote_mod
        remote_mod.REMOTE_CFG_PATH = self._orig_path
        import os
        os.unlink(self.tmp_cfg.name)

    def test_save_and_load_host(self):
        hosts = list_hosts()
        self.assertEqual(hosts, {})

        save_host("test", "192.168.1.1", "22", "root", "password", "secret")
        hosts = list_hosts()
        self.assertIn("test", hosts)
        self.assertEqual(hosts["test"]["ip"], "192.168.1.1")
        self.assertEqual(hosts["test"]["port"], 22)

    def test_delete_host(self):
        save_host("test", "192.168.1.1", "22", "root", "password", "secret")
        self.assertTrue(delete_host("test"))
        self.assertFalse(delete_host("nonexist"))


class TestSpiderUtils(unittest.TestCase):
    def test_sanitize_filename(self):
        self.assertEqual(_sanitize_filename("https://example.com/path"), "example_com_path.html")
        self.assertEqual(_sanitize_filename("https://example.com/"), "example_com_index.html")

    def test_extract_links(self):
        html = '<a href="/page1">1</a><a href="https://example.com/page2">2</a><a href="http://other.com">3</a>'
        links = _extract_links(html, "https://example.com/")
        self.assertIn("https://example.com/page1", links)
        self.assertIn("https://example.com/page2", links)
        self.assertNotIn("http://other.com", links)


class TestRegistryIntegration(unittest.TestCase):
    def test_agent_tools_registered(self):
        from fr_cli.command.registry import get_registry
        reg = get_registry()
        tools = reg.get_tools()
        names = [t["name"] for t in tools]
        self.assertIn("agent_create", names)
        self.assertIn("agent_run", names)


if __name__ == "__main__":
    unittest.main()
