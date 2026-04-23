"""
意图判定测试
验证大模型意图分类器：将用户提问 + 功能列表发给大模型，
判定是直接回答(DIRECT)还是需要调用工具(TOOL)。
"""
import sys
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


class TestIntentClassification(unittest.TestCase):
    """意图判定单元测试"""

    def setUp(self):
        self.temp_dir = os.path.realpath(tempfile.mkdtemp())
        from fr_cli.weapon.fs import VFS
        from fr_cli.command.security import SecurityManager
        from fr_cli.command.executor import CommandExecutor
        from fr_cli.weapon.loader import load_weapon_md, get_available_tools

        from types import SimpleNamespace
        self.vfs = VFS([self.temp_dir])
        self.security = SecurityManager("zh", {})
        mock_state = SimpleNamespace(
            vfs=self.vfs, mail_c=None, web_c=None, disk_c=None,
            plugins={}, lang="zh", security=self.security, cfg={},
            client=None, model_name="glm-4-flash"
        )
        self.executor = CommandExecutor(mock_state)
        self.weapon_tools, _ = load_weapon_md()
        self.tools = get_available_tools(self.weapon_tools, {})

        # 构造一个最小化的 AppState mock
        self.state = MagicMock()
        self.state.lang = "zh"
        self.state.model_name = "glm-4-flash"
        self.state.vfs = self.vfs
        self.state.weapon_tools = self.weapon_tools
        self.state.plugins = {}
        self.state.weapon_triggers = {}
        self.state.context_summary = ""
        self.state.messages = []
        self.state.sn = "test"
        self.state.security = self.security
        self.state.executor = self.executor
        self.state.limit = 4096
        self.state.client = MagicMock()
        self.state.client.api_key = "fake_key_for_test"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ---------- 1. _classify_intent 解析测试 ----------
    @patch("fr_cli.core.intent.stream_cnt")
    def test_classify_intent_direct(self, mock_stream):
        """大模型返回 DIRECT 时，意图判定为 DIRECT"""
        from fr_cli.core.intent import classify_intent
        mock_stream.return_value = ("DIRECT", {}, 0.1)

        result = classify_intent(self.state, "你好，今天天气怎么样", self.tools, "zh")
        self.assertEqual(result, "DIRECT")

        # 验证 stream_cnt 被调用且 silent=True
        mock_stream.assert_called_once()
        _, kwargs = mock_stream.call_args
        self.assertTrue(kwargs.get("silent"))
        self.assertEqual(kwargs.get("max_tokens"), 10)

    @patch("fr_cli.core.intent.stream_cnt")
    def test_classify_intent_tool(self, mock_stream):
        """大模型返回 TOOL 时，意图判定为 TOOL"""
        from fr_cli.core.intent import classify_intent
        mock_stream.return_value = ("TOOL", {}, 0.1)

        result = classify_intent(self.state, "帮我写一个 Python 脚本并保存", self.tools, "zh")
        self.assertEqual(result, "TOOL")

    @patch("fr_cli.core.intent.stream_cnt")
    def test_classify_intent_case_insensitive(self, mock_stream):
        """大小写不敏感：tool / Tool / tOoL 都应识别为 TOOL"""
        from fr_cli.core.intent import classify_intent
        for raw in ["tool", "Tool", "tOoL", "  TOOL  "]:
            mock_stream.return_value = (raw, {}, 0.1)
            result = classify_intent(self.state, "搜索一下", self.tools, "zh")
            self.assertEqual(result, "TOOL", f"'{raw}' 应被识别为 TOOL")

    @patch("fr_cli.core.intent.stream_cnt")
    def test_classify_intent_prompt_contains_tools(self, mock_stream):
        """判定 prompt 中应包含工具列表信息"""
        from fr_cli.core.intent import classify_intent
        mock_stream.return_value = ("DIRECT", {}, 0.1)

        classify_intent(self.state, "测试", self.tools, "zh")

        # 提取传给 stream_cnt 的 messages
        args, _ = mock_stream.call_args
        messages = args[2]  # 第三个 positional arg 是 messages
        prompt_text = messages[0]["content"]

        # prompt 中应包含工具列表和判定规则
        self.assertIn("可用工具列表", prompt_text)
        self.assertIn("DIRECT", prompt_text)
        self.assertIn("TOOL", prompt_text)
        self.assertIn("测试", prompt_text)

    # ---------- 1.5 快速关键词预检测试 ----------
    def test_should_force_tool_with_save_keyword(self):
        """包含'保存'关键词时应强制判定为 TOOL"""
        from fr_cli.core.intent import should_force_tool
        self.assertTrue(should_force_tool("详细介绍什么是RAG, 并将介绍内容保存到工作区"))
        self.assertTrue(should_force_tool("帮我写一个Python脚本并保存"))
        self.assertTrue(should_force_tool("写入文件 test.txt"))

    def test_should_force_tool_with_search_keyword(self):
        """包含'搜索'关键词时应强制判定为 TOOL"""
        from fr_cli.core.intent import should_force_tool
        self.assertTrue(should_force_tool("搜索一下最新的人工智能新闻"))
        self.assertTrue(should_force_tool("查一下今天天气"))

    def test_should_force_tool_english_keywords(self):
        """英文关键词也应触发强制 TOOL 判定"""
        from fr_cli.core.intent import should_force_tool
        self.assertTrue(should_force_tool("Introduce RAG and save it to workspace"))
        self.assertTrue(should_force_tool("Search for Python tutorials"))
        self.assertTrue(should_force_tool("Send an email to John"))
        self.assertTrue(should_force_tool("List files in current directory"))
        self.assertTrue(should_force_tool("Generate an image of a cat"))
        self.assertTrue(should_force_tool("Upload the file to cloud"))
        self.assertTrue(should_force_tool("Write the result to a file"))

    def test_should_force_tool_no_keyword(self):
        """不包含工具关键词时不强制判定"""
        from fr_cli.core.intent import should_force_tool
        self.assertFalse(should_force_tool("你好"))
        self.assertFalse(should_force_tool("1+1等于几"))
        self.assertFalse(should_force_tool("Python怎么写快速排序"))
        self.assertFalse(should_force_tool("What is the weather today?"))
        self.assertFalse(should_force_tool("Explain quantum computing"))

    def test_force_tool_bypasses_llm_classification(self):
        """关键词命中时跳过大模型判定，直接注入工具"""
        from fr_cli.core.chat import handle_ai_chat

        with patch("fr_cli.core.chat.stream_cnt") as mock_stream:
            mock_stream.side_effect = [
                ("好的，我来查看。\n【命令：/ls】", {}, 0.5),
                ("当前目录为空。", {}, 0.5)
            ]

            handle_ai_chat(self.state, "查看当前目录")

            # stream_cnt 只被调用了 2 次（没有意图判定那一步），因为"查看目录"命中关键词
            self.assertEqual(len(mock_stream.call_args_list), 2)

    def test_force_tool_english_bypasses_llm(self):
        """英文关键词命中时也跳过大模型判定"""
        from fr_cli.core.chat import handle_ai_chat

        with patch("fr_cli.core.chat.stream_cnt") as mock_stream:
            # 回复不含命令标记，避免触发安全确认
            mock_stream.side_effect = [
                ("OK, I will introduce RAG and save it for you.", {}, 0.5),
            ]

            handle_ai_chat(self.state, "Introduce RAG and save to workspace")

            # 没有意图判定调用，直接走 TOOL 分支
            self.assertEqual(len(mock_stream.call_args_list), 1)

            # 验证系统提示词中包含工具列表
            args, _ = mock_stream.call_args
            messages = args[2]
            system_content = messages[0]["content"]
            self.assertIn("当前可用的工具列表", system_content)

    @patch("fr_cli.core.intent.stream_cnt")
    def test_classify_intent_english_prompt(self, mock_stream):
        """英文界面下应使用英文 prompt 进行意图判定"""
        from fr_cli.core.intent import classify_intent
        mock_stream.return_value = ("DIRECT", {}, 0.1)

        self.state.lang = "en"
        classify_intent(self.state, "What is RAG?", self.tools, "en")

        args, _ = mock_stream.call_args
        messages = args[2]
        prompt_text = messages[0]["content"]

        self.assertIn("intent classifier", prompt_text)
        self.assertIn("DIRECT", prompt_text)
        self.assertIn("TOOL", prompt_text)
        self.assertIn("Available tools", prompt_text)

    # ---------- 2. _handle_ai_chat 工具注入流程测试 ----------
    @patch("fr_cli.core.intent.stream_cnt")
    @patch("fr_cli.core.chat.stream_cnt")
    def test_handle_chat_direct_no_tools_injected(self, mock_chat_stream, mock_intent_stream):
        """DIRECT 意图：系统提示词中不应包含工具列表"""
        from fr_cli.core.chat import handle_ai_chat

        mock_intent_stream.return_value = ("DIRECT", {}, 0.1)  # 意图判定
        mock_chat_stream.return_value = ("你好！我是 AI 助手。", {}, 0.5)  # 正常回复

        handle_ai_chat(self.state, "你好")

        # intent.stream_cnt 被调用 1 次（意图判定）
        self.assertEqual(len(mock_intent_stream.call_args_list), 1)
        # chat.stream_cnt 被调用 1 次（正常回复）
        self.assertEqual(len(mock_chat_stream.call_args_list), 1)

        # 检查正常回复的系统提示词不应包含工具列表
        _, kwargs = mock_chat_stream.call_args_list[0]
        messages = kwargs.get("messages", mock_chat_stream.call_args_list[0][0][2])
        system_content = messages[0]["content"]
        self.assertNotIn("当前可用的工具列表", system_content)

    @patch("fr_cli.core.intent.stream_cnt")
    @patch("fr_cli.core.chat.stream_cnt")
    def test_handle_chat_tool_with_tools_injected(self, mock_chat_stream, mock_intent_stream):
        """TOOL 意图：系统提示词中应包含工具列表"""
        from fr_cli.core.chat import handle_ai_chat

        mock_intent_stream.return_value = ("TOOL", {}, 0.1)  # 意图判定
        mock_chat_stream.side_effect = [
            ("好的，我来查看。\n【命令：/ls】", {}, 0.5),      # 正常回复（含命令）
            ("当前目录为空。", {}, 0.5)                     # 命令执行后最终回复
        ]

        handle_ai_chat(self.state, "查看当前目录")

        # intent.stream_cnt 被调用 1 次（意图判定）
        self.assertEqual(len(mock_intent_stream.call_args_list), 1)
        # chat.stream_cnt 被调用 2 次（正常回复 + 最终回复）
        self.assertEqual(len(mock_chat_stream.call_args_list), 2)

        # 第一次 chat 调用的系统提示词应包含工具列表
        _, kwargs = mock_chat_stream.call_args_list[0]
        messages = kwargs.get("messages", mock_chat_stream.call_args_list[0][0][2])
        system_content = messages[0]["content"]
        self.assertIn("当前可用的工具列表", system_content)

    @patch("fr_cli.core.chat.stream_cnt")
    def test_handle_chat_direct_saves_messages(self, mock_stream):
        """DIRECT 意图：对话历史应被正确保存"""
        from fr_cli.core.chat import handle_ai_chat

        mock_stream.side_effect = [
            ("DIRECT", {}, 0.1),
            ("直接回答内容", {}, 0.5)
        ]

        handle_ai_chat(self.state, "1+1等于几")

        # 验证 state.messages 被更新
        self.assertGreaterEqual(len(self.state.messages), 2)
        self.assertEqual(self.state.messages[-1]["role"], "assistant")


if __name__ == "__main__":
    unittest.main(verbosity=2)
