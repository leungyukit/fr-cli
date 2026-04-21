"""
集成测试：模拟大模型判定并自主调用工具的完整闭环
覆盖 "用户输入 → 工具注入判定 → AI 生成命令 → 自动执行 → 结果回传" 全流程
无需真实 API Key，使用 mock 验证代码路径与数据流
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


class TestAIToolCallingIntegration(unittest.TestCase):
    """集成测试：AI 自主判定并调用工具的完整闭环"""

    def setUp(self):
        self.temp_dir = os.path.realpath(tempfile.mkdtemp())
        from fr_cli.weapon.fs import VFS
        from fr_cli.command.security import SecurityManager
        from fr_cli.command.executor import CommandExecutor
        from fr_cli.weapon.loader import load_weapon_md, should_inject_tools, get_available_tools

        from types import SimpleNamespace
        self.vfs = VFS([self.temp_dir])
        self.security = SecurityManager("zh", {})
        mock_state = SimpleNamespace(
            vfs=self.vfs, mail_c=None, web_c=None, disk_c=None,
            plugins={}, lang="zh", security=self.security, cfg={},
            client=None, model_name="glm-4-flash"
        )
        self.executor = CommandExecutor(mock_state)
        self.weapon_tools, self.weapon_triggers = load_weapon_md()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ---------- 1. 工具注入判定测试 ----------
    def test_inject_tools_for_file_request(self):
        """用户请求文件操作时应注入工具信息"""
        from fr_cli.weapon.loader import should_inject_tools
        self.assertTrue(should_inject_tools("帮我查看当前目录", self.weapon_triggers))
        self.assertTrue(should_inject_tools("读取文件内容", self.weapon_triggers))
        self.assertTrue(should_inject_tools("save to file", self.weapon_triggers))

    def test_inject_tools_for_search_request(self):
        """用户请求搜索时应注入工具信息"""
        from fr_cli.weapon.loader import should_inject_tools
        self.assertTrue(should_inject_tools("搜索最新人工智能新闻", self.weapon_triggers))
        self.assertTrue(should_inject_tools("查一下今天天气", self.weapon_triggers))

    def test_no_inject_for_greeting(self):
        """问候语不应注入工具信息"""
        from fr_cli.weapon.loader import should_inject_tools
        self.assertFalse(should_inject_tools("你好", self.weapon_triggers))
        self.assertFalse(should_inject_tools("1+1等于几", self.weapon_triggers))
        self.assertFalse(should_inject_tools("Python怎么写快速排序", self.weapon_triggers))

    def test_no_inject_for_direct_command(self):
        """用户直接输入 / 命令时不注入工具信息"""
        from fr_cli.weapon.loader import should_inject_tools
        self.assertFalse(should_inject_tools("/ls", self.weapon_triggers))
        self.assertFalse(should_inject_tools("/web hello", self.weapon_triggers))

    # ---------- 2. 系统提示词工具列表测试 ----------
    def test_tools_injected_in_system_prompt(self):
        """验证注入系统提示词后的工具列表结构完整"""
        from fr_cli.weapon.loader import get_available_tools
        tools = get_available_tools(self.weapon_tools, {})
        self.assertGreater(len(tools), 0)

        # 模拟主循环构造 tools_info 的逻辑
        tools_info = "\n\n当前可用的工具列表：\n"
        for i, tool in enumerate(tools, 1):
            tools_info += f"{i}. {tool['name']}: {tool['description']}\n   可用命令: {', '.join(tool['commands'])}\n"

        self.assertIn("file_operations", tools_info)
        self.assertIn("web_search", tools_info)
        self.assertIn("list_files", tools_info)
        self.assertIn("search_web", tools_info)
        self.assertIn("email_management", tools_info)

    def test_tools_with_plugins(self):
        """验证插件被正确追加到工具列表"""
        from fr_cli.weapon.loader import get_available_tools
        plugins = {"demo_plugin": "/path/demo.py"}
        tools = get_available_tools(self.weapon_tools, plugins)
        names = [t["name"] for t in tools]
        self.assertIn("plugin_demo_plugin", names)

    # ---------- 3. AI 自动命令执行闭环测试 ----------
    def test_ai_auto_ls_and_result_feedback(self):
        """场景1：AI 自动执行 /ls 并将结果回传到消息历史"""
        Path(self.temp_dir, "test_file.txt").write_text("content")

        ai_response = "好的，我来查看当前目录。\n【命令：/ls】"
        clean_txt, cmd_results = self.executor.process_ai_commands(ai_response)

        # 验证 clean 文本去除了命令标记
        self.assertNotIn("【命令", clean_txt)
        self.assertIn("好的，我来查看当前目录。", clean_txt)

        # 验证命令执行结果包含文件名
        self.assertEqual(len(cmd_results), 1)
        self.assertIn("test_file.txt", cmd_results[0])

        # 模拟主循环更新消息历史的逻辑
        messages = [
            {"role": "system", "content": "sys prompt"},
            {"role": "user", "content": "查看目录"},
            {"role": "assistant", "content": ai_response}
        ]
        messages[-1]["content"] = clean_txt if clean_txt.strip() else "[已执行命令]"
        messages.append({
            "role": "system",
            "content": f"命令执行结果:\n" + "\n".join(cmd_results)
        })

        # 验证消息历史可被用于下一轮 AI 调用
        self.assertEqual(messages[-2]["content"], "好的，我来查看当前目录。")
        self.assertIn("命令执行结果", messages[-1]["content"])
        self.assertIn("test_file.txt", messages[-1]["content"])

    def test_ai_auto_write_file(self):
        """场景2：AI 自动执行 /write 创建文件"""
        ai_response = "【命令：/write hello.txt world】"
        clean_txt, cmd_results = self.executor.process_ai_commands(ai_response)

        self.assertEqual(len(cmd_results), 1)
        self.assertIn("✅", cmd_results[0])

        # 验证文件确实被创建在 VFS 沙盒内
        target = Path(self.temp_dir, "hello.txt")
        self.assertTrue(target.exists())
        self.assertEqual(target.read_text(), "world")

    def test_ai_auto_cd_and_ls(self):
        """场景3：AI 先切换目录再列出文件"""
        subdir = Path(self.temp_dir, "subdir")
        subdir.mkdir()
        Path(subdir, "inner.txt").write_text("inner")

        ai_response = "【命令：/cd subdir】【命令：/ls】"
        clean_txt, cmd_results = self.executor.process_ai_commands(ai_response)

        self.assertEqual(len(cmd_results), 2)
        self.assertIn("✅", cmd_results[0])  # cd 成功
        self.assertIn("inner.txt", cmd_results[1])  # ls 包含文件

    def test_ai_multiple_commands_sequence(self):
        """场景4：AI 在一条回复中顺序执行多个命令"""
        ai_response = "先创建文件，再查看内容。\n【命令：/write multi.txt ok】\n【命令：/cat multi.txt】"
        clean_txt, cmd_results = self.executor.process_ai_commands(ai_response)

        self.assertEqual(len(cmd_results), 2)
        self.assertIn("✅", cmd_results[0])
        self.assertIn("✅", cmd_results[1])
        self.assertIn("ok", cmd_results[1])  # cat 结果包含内容

        # 验证文件被创建
        self.assertTrue(Path(self.temp_dir, "multi.txt").exists())

    def test_ai_command_failure_handled(self):
        """场景5：AI 调用非法命令时的错误处理"""
        ai_response = "【命令：/cd /nonexistent_path_12345】"
        clean_txt, cmd_results = self.executor.process_ai_commands(ai_response)

        self.assertEqual(len(cmd_results), 1)
        self.assertIn("❌", cmd_results[0])
        self.assertIn("命令执行失败", cmd_results[0])

    def test_ai_unknown_command(self):
        """场景6：AI 生成了不存在的命令"""
        ai_response = "【命令：/magic_spell】"
        clean_txt, cmd_results = self.executor.process_ai_commands(ai_response)

        self.assertEqual(len(cmd_results), 1)
        self.assertIn("❌", cmd_results[0])
        self.assertIn("Unknown command", cmd_results[0])

    def test_ai_no_command_for_direct_answer(self):
        """场景7：AI 直接回答，不调用任何工具"""
        ai_response = "你好！有什么我可以帮你的吗？"
        clean_txt, cmd_results = self.executor.process_ai_commands(ai_response)

        self.assertEqual(cmd_results, [])
        self.assertEqual(clean_txt, ai_response)

    # ---------- 4. 功能推荐集成测试 ----------
    def test_recommend_after_file_operation(self):
        """文件操作后推荐相关功能"""
        from fr_cli.core.recommender import recommend_features
        recs = recommend_features("我刚刚读取了文件")
        cmds = [r["cmd"] for r in recs]
        self.assertIn("/ls", cmds)
        self.assertIn("/cat <file>", cmds)

    def test_recommend_after_search(self):
        """搜索后推荐相关功能"""
        from fr_cli.core.recommender import recommend_features
        recs = recommend_features("搜索信息")
        cmds = [r["cmd"] for r in recs]
        self.assertIn("/web <query>", cmds)

    # ---------- 5. 完整消息流测试 ----------
    def test_full_message_flow_with_tool_use(self):
        """验证使用工具后的完整消息流可被正确保存和加载"""
        from fr_cli.memory.history import save_sess, load_sess

        # 模拟一次完整的带工具调用的对话
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "查看目录"},
            {"role": "assistant", "content": "好的，我来查看。\n【命令：/ls】"},
        ]

        # 执行命令并更新历史
        clean_txt, cmd_results = self.executor.process_ai_commands(messages[-1]["content"])
        messages[-1]["content"] = clean_txt
        messages.append({
            "role": "system",
            "content": f"命令执行结果:\n" + "\n".join(cmd_results)
        })
        messages.append({"role": "assistant", "content": "当前目录是空的。"})

        # 保存并加载
        self.assertTrue(save_sess("tool_test", messages))
        ok, loaded, name = load_sess(0, "new_sys")
        self.assertTrue(ok)
        self.assertEqual(name, "tool_test")
        self.assertEqual(len(loaded), 5)  # system + user + assistant + system + assistant


class TestLiveDemoScript(unittest.TestCase):
    """
    验证真实 API 演示脚本存在且结构正确
    （真实 API 调用需要用户自行提供 Key 运行 tests/run_live_demo.py）
    """

    def test_demo_script_exists(self):
        demo_path = Path(__file__).parent / "run_live_demo.py"
        self.assertTrue(demo_path.exists(), "真实 API 演示脚本 run_live_demo.py 应存在")


if __name__ == "__main__":
    unittest.main(verbosity=2)
