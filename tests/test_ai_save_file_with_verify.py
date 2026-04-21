"""
集成测试：AI 保存文件闭环验证

模拟用户输入"详细介绍什么是AI，并帮我保存到工作目录"，
AI 回复中包含 write_file 调用标记，程序自动执行后，
需二次验证文件是否真实存在且有内容。

验证通过 → 返回文件路径
验证失败 → 重新调用 write_file（重试一次）
"""
import sys
import os
import tempfile
import shutil
import unittest

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from fr_cli.weapon.fs import VFS
from fr_cli.command.executor import CommandExecutor


class TestAISaveFileWithVerification(unittest.TestCase):
    """AI 自动保存文件并验证的完整闭环测试"""

    def setUp(self):
        self.temp_dir = os.path.realpath(tempfile.mkdtemp())
        self.vfs = VFS([self.temp_dir])
        self.executor = CommandExecutor(
            vfs=self.vfs,
            mail_c=None,
            web_c=None,
            disk_c=None,
            plugins={},
            lang="zh",
            security=None,
            cfg={},
            client=None,
            model_name="glm-4-flash"
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _verify_file(self, path):
        """验证文件是否存在且非空，返回 (ok, abs_path, content_or_error)"""
        abs_path = os.path.join(self.temp_dir, path)
        if not os.path.exists(abs_path):
            return False, abs_path, "文件不存在"
        size = os.path.getsize(abs_path)
        if size == 0:
            return False, abs_path, "文件为空"
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
        return True, abs_path, content

    def _retry_write(self, path, content):
        """重试写入文件"""
        ok, msg = self.vfs.write(path, content, "zh")
        return ok

    def test_ai_save_file_success(self):
        """场景1：AI 正常保存文件，验证通过"""
        content_inside = (
            "# 什么是 AI\n\n"
            "人工智能（Artificial Intelligence，简称 AI）是指由人制造出来的系统所表现出来的智能。\n\n"
            "## 主要分支\n"
            "- 机器学习\n"
            "- 深度学习\n"
            "- 自然语言处理\n"
            "- 计算机视觉\n\n"
            "AI 正在改变我们的生活方式。"
        )
        ai_response = (
            '好的，我为您详细介绍 AI，并保存到工作目录。\n\n'
            '【调用：write_file({'
            '"path": "AI_Introduction.md", '
            '"content": ' + repr(content_inside) +
            '})】\n\n'
            '已为您保存到 AI_Introduction.md。'
        )

        # 第一步：解析并执行 AI 回复中的命令
        clean_txt, cmd_results = self.executor.process_ai_commands(ai_response)

        # 第二步：验证文件是否存在且有内容
        ok, abs_path, content = self._verify_file("AI_Introduction.md")

        # 第三步：断言验证通过
        self.assertTrue(ok, f"文件验证失败: {content}")
        self.assertIn("人工智能", content)
        self.assertGreater(len(content), 50)

        # 第四步：模拟向用户展示结果（返回路径）
        user_message = f"✅ 文件已保存: {abs_path}"
        self.assertIn(self.temp_dir, user_message)

    def test_ai_save_file_empty_and_retry(self):
        """场景2：AI 第一次保存空文件，验证失败后重试成功"""
        ai_response_first = (
            '好的，已保存。\n\n'
            '【调用：write_file({'
            '"path": "AI_Empty.md", '
            '"content": ""'
            '})】\n\n'
            '已为您保存到 AI_Empty.md。'
        )

        # 第一次执行
        clean_txt, cmd_results = self.executor.process_ai_commands(ai_response_first)

        # 验证：文件存在但为空
        ok, abs_path, info = self._verify_file("AI_Empty.md")
        self.assertFalse(ok, "第一次保存应为空文件，验证应失败")
        self.assertEqual(info, "文件为空")

        # 重试：模拟再次调用 write_file（补充内容）
        retry_content = (
            "# 什么是 AI\n\n"
            "人工智能（Artificial Intelligence）是计算机科学的一个分支，"
            "致力于创造能够模拟人类智能的系统。\n\n"
            "## 应用领域\n"
            "- 语音识别\n"
            "- 图像识别\n"
            "- 自动驾驶\n"
            "- 智能推荐\n"
        )
        retry_ok = self._retry_write("AI_Empty.md", retry_content)
        self.assertTrue(retry_ok, "重试写入应成功")

        # 再次验证
        ok2, abs_path2, content2 = self._verify_file("AI_Empty.md")
        self.assertTrue(ok2, f"重试后文件验证应通过: {content2}")
        self.assertIn("人工智能", content2)
        self.assertGreater(len(content2), 50)

    def test_ai_save_file_not_exist_and_retry(self):
        """场景3：AI 回复中路径非法导致未创建文件，验证失败后重试成功"""
        ai_response = (
            '已保存。\n\n'
            '【调用：write_file({'
            '"path": "../escaped.md", '
            '"content": "非法路径测试"'
            '})】\n\n'
            '文件已生成。'
        )

        clean_txt, cmd_results = self.executor.process_ai_commands(ai_response)

        # 验证：文件未创建（因为 ../ 被 VFS 拦截）
        ok, abs_path, info = self._verify_file("../escaped.md")
        self.assertFalse(ok, "非法路径应被拦截，文件不应存在")

        # 检查命令执行结果中包含失败信息
        self.assertTrue(
            any("❌" in r for r in cmd_results),
            "非法路径应产生错误结果"
        )

        # 重试：使用合法路径重新保存
        retry_ok = self._retry_write(
            "AI_Retry.md",
            "# 什么是 AI\n\nAI 是指人工智能。\n"
        )
        self.assertTrue(retry_ok)

        ok2, abs_path2, content2 = self._verify_file("AI_Retry.md")
        self.assertTrue(ok2, "重试后文件应存在")
        self.assertIn("人工智能", content2)

    def test_full_dialog_flow(self):
        """场景4：完整对话流——用户提问 → AI 保存 → 程序验证 → 返回路径"""
        user_input = "详细介绍什么是AI，并帮我保存到工作目录"

        content_inside = (
            "# 人工智能（AI）详解\n\n"
            "人工智能（Artificial Intelligence，AI）是指由人制造出来的系统所表现出来的智能。\n\n"
            "## 1. 定义\n"
            "AI 是计算机科学的一个广泛分支，涉及构建能够执行通常需要人类智能的任务的智能机器。\n\n"
            "## 2. 主要类型\n"
            "- 弱人工智能（Narrow AI）：专注于特定任务，如语音识别、图像分类。\n"
            "- 强人工智能（General AI）：具备与人类相当或超越人类的通用智能。\n\n"
            "## 3. 核心技术\n"
            "- 机器学习（Machine Learning）\n"
            "- 深度学习（Deep Learning）\n"
            "- 自然语言处理（NLP）\n"
            "- 计算机视觉（Computer Vision）\n\n"
            "## 4. 应用场景\n"
            "- 智能助手（如 Siri、Alexa）\n"
            "- 自动驾驶汽车\n"
            "- 医疗诊断\n"
            "- 金融风控\n\n"
            "## 5. 发展趋势\n"
            "随着大语言模型（LLM）的兴起，AI 正在向通用人工智能（AGI）迈进。"
        )

        ai_response = (
            '人工智能（AI）是计算机科学的重要分支，旨在创建能够执行通常需要人类智能的任务的系统。\n\n'
            '【调用：write_file({'
            '"path": "AI详解.md", '
            '"content": ' + repr(content_inside) +
            '})】\n\n'
            '已为您保存到工作目录的 AI详解.md 文件中。'
        )

        # 执行 AI 命令
        clean_txt, cmd_results = self.executor.process_ai_commands(ai_response)

        # 验证文件
        ok, abs_path, content = self._verify_file("AI详解.md")

        if ok:
            # 验证通过，模拟向用户展示路径
            final_msg = f"✅ 文件已成功保存: {abs_path}"
            self.assertIn("AI详解.md", final_msg)
            self.assertGreater(len(content), 100)
            self.assertIn("深度学习", content)
        else:
            # 验证失败，应触发重试（测试中直接断言失败）
            self.fail(f"文件验证未通过，应自动重试: {abs_path}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
