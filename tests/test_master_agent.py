"""
MasterAgent 测试 —— 自我进化型主控 Agent
"""
import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import MagicMock, patch

from fr_cli.agent.master import MasterAgent


class MockState:
    """最小化 Mock AppState"""
    def __init__(self):
        self.lang = "zh"
        self.model_name = "glm-4-flash"
        self.client = MagicMock()
        self.cfg = {}
        self.vfs = MagicMock()
        self.vfs.cwd = "/tmp"
        self.messages = []

    def save_cfg(self):
        pass


class TestMasterAgent(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.original_dir = Path.home() / ".fr_cli_master"
        # 重定向 MasterAgent 数据目录到临时目录
        from fr_cli import agent as agent_pkg
        from fr_cli.agent import master as master_mod
        self._orig_master_dir = master_mod.MASTER_DIR
        master_mod.SESSION_DIR = Path(self.tmpdir.name)
        master_mod.MASTER_DIR = Path(self.tmpdir.name)
        master_mod.PERSONA_FILE = master_mod.MASTER_DIR / "persona.md"
        master_mod.SKILLS_FILE = master_mod.MASTER_DIR / "skills.md"
        master_mod.EVOLUTION_FILE = master_mod.MASTER_DIR / "evolution.json"
        master_mod.MEMORY_FILE = master_mod.MASTER_DIR / "memory.json"
        master_mod.SESSION_FILE = master_mod.MASTER_DIR / "session.json"
        master_mod.STATUS_FILE = master_mod.MASTER_DIR / "status.json"

        self.state = MockState()
        self.agent = MasterAgent(self.state)

    def tearDown(self):
        self.tmpdir.cleanup()
        from fr_cli.agent import master as master_mod
        master_mod.MASTER_DIR = self._orig_master_dir
        master_mod.PERSONA_FILE = master_mod.MASTER_DIR / "persona.md"
        master_mod.SKILLS_FILE = master_mod.MASTER_DIR / "skills.md"
        master_mod.EVOLUTION_FILE = master_mod.MASTER_DIR / "evolution.json"
        master_mod.MEMORY_FILE = master_mod.MASTER_DIR / "memory.json"
        master_mod.SESSION_FILE = master_mod.MASTER_DIR / "session.json"
        master_mod.STATUS_FILE = master_mod.MASTER_DIR / "status.json"

    def test_toggle_default(self):
        """默认禁用，toggle 切换"""
        self.assertFalse(self.agent.is_enabled())
        self.agent.toggle(True)
        self.assertTrue(self.agent.is_enabled())
        self.agent.toggle(False)
        self.assertFalse(self.agent.is_enabled())

    def test_toggle_no_arg(self):
        """toggle() 无参数时自动翻转"""
        enabled = self.agent.toggle()
        self.assertTrue(enabled)
        enabled = self.agent.toggle()
        self.assertFalse(enabled)

    def test_status_empty(self):
        """新 Agent 状态应为空"""
        st = self.agent.status()
        self.assertFalse(st["enabled"])
        self.assertEqual(st["total_interactions"], 0)
        self.assertEqual(st["success"], 0)
        self.assertEqual(st["failure"], 0)

    def test_extract_tool_calls_single(self):
        """正确提取单个 tool 代码块"""
        text = '思考中...\n```tool\n{"tool": "list_files", "params": {}}\n```\n完成'
        calls = MasterAgent._extract_tool_calls(text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["tool"], "list_files")
        self.assertEqual(calls[0]["params"], {})

    def test_extract_tool_calls_multiple(self):
        """正确提取多个 tool 代码块"""
        text = ('```tool\n{"tool": "a", "params": {"x": 1}}\n```\n'
                '中间文本\n'
                '```tool\n{"tool": "b", "params": {"y": 2}}\n```')
        calls = MasterAgent._extract_tool_calls(text)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["tool"], "a")
        self.assertEqual(calls[1]["tool"], "b")

    def test_extract_tool_calls_invalid_json(self):
        """忽略无效的 JSON"""
        text = '```tool\n不是 JSON\n```'
        calls = MasterAgent._extract_tool_calls(text)
        self.assertEqual(len(calls), 0)

    def test_extract_tool_calls_no_block(self):
        """无代码块时返回空列表"""
        calls = MasterAgent._extract_tool_calls("普通文本")
        self.assertEqual(len(calls), 0)

    def test_record_interaction(self):
        """记录交互到内存"""
        self.agent._record_interaction("hello", "search_web", True, "ok")
        self.assertEqual(len(self.agent.memory["interactions"]), 1)
        self.assertEqual(self.agent.memory["interactions"][0]["tool"], "search_web")
        self.assertTrue(self.agent.memory["interactions"][0]["success"])

    def test_record_interaction_limits_to_100(self):
        """内存只保留最近 100 条"""
        for i in range(150):
            self.agent._record_interaction(f"msg{i}", "tool", True, "ok")
        self.assertEqual(len(self.agent.memory["interactions"]), 100)

    def test_get_recent_memory(self):
        """获取最近记忆摘要"""
        self.agent._record_interaction("q1", "t1", True, "r1")
        self.agent._record_interaction("q2", "t2", False, "r2")
        mem = self.agent._get_recent_memory()
        self.assertIn("t1", mem)
        self.assertIn("t2", mem)
        self.assertIn("✅", mem)
        self.assertIn("❌", mem)

    def test_get_recent_memory_empty(self):
        """无记忆时返回空字符串"""
        self.assertEqual(self.agent._get_recent_memory(), "")


if __name__ == "__main__":
    unittest.main()
