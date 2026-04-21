"""
结构化工具调用全面验证
模拟 AI 输出各种【调用：tool_name({...})】格式，验证 invoke_tool 直接调用 weapon 方法的正确性。
"""
import sys
import os
import json
import tempfile
import shutil
import unittest
from unittest.mock import MagicMock, patch

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from fr_cli.weapon.fs import VFS
from fr_cli.command.executor import CommandExecutor


class TestStructuredToolInvocation(unittest.TestCase):
    """验证新的结构化工具调用架构"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.vfs = VFS([self.temp_dir])
        self.mail_c = MagicMock()
        self.web_c = MagicMock()
        self.disk_c = MagicMock()
        self.cfg = {"session_name": "", "model": "glm-4-flash", "lang": "zh"}
        self.client = MagicMock()

        from types import SimpleNamespace
        mock_state = SimpleNamespace(
            vfs=self.vfs,
            mail_c=self.mail_c,
            web_c=self.web_c,
            disk_c=self.disk_c,
            plugins={"test_plugin": "/tmp/test.py"},
            lang="zh",
            security=None,
            cfg=self.cfg,
            client=self.client,
            model_name="glm-4-flash"
        )
        self.executor = CommandExecutor(mock_state)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _simulate_ai(self, ai_response, msgs=None):
        """模拟 AI 回复并执行其中的调用标记"""
        return self.executor.process_ai_commands(ai_response, msgs)

    # ========== 文件操作 ==========
    def test_write_file(self):
        """AI 请求写入文件：【调用：write_file({"path": "a.md", "content": "# Hello"})】"""
        ai = '好的，我来保存。\n【调用：write_file({"path": "a.md", "content": "# Hello\\n\\nWorld"})】\n已保存。'
        clean, results = self._simulate_ai(ai)
        self.assertIn("已保存", clean)
        self.assertTrue(any("✅" in r and "write_file" in r for r in results))

        with open(os.path.join(self.temp_dir, "a.md")) as f:
            content = f.read()
        self.assertEqual(content, "# Hello\n\nWorld")

    def test_read_file(self):
        """AI 请求读取文件：【调用：read_file({"path": "b.md"})】"""
        with open(os.path.join(self.temp_dir, "b.md"), "w") as f:
            f.write("测试内容")

        ai = '文件内容如下：\n【调用：read_file({"path": "b.md"})】\n完毕。'
        clean, results = self._simulate_ai(ai)
        self.assertTrue(any("测试内容" in r for r in results))

    def test_list_files(self):
        """AI 请求列出文件：【调用：list_files({})】"""
        open(os.path.join(self.temp_dir, "x.txt"), "w").close()
        ai = '当前目录文件：\n【调用：list_files({})】\n如上。'
        clean, results = self._simulate_ai(ai)
        self.assertTrue(any("x.txt" in r for r in results))

    def test_delete_file(self):
        """AI 请求删除文件：【调用：delete_file({"path": "del.md"})】"""
        open(os.path.join(self.temp_dir, "del.md"), "w").close()
        ai = '删除文件。\n【调用：delete_file({"path": "del.md"})】\n完成。'
        clean, results = self._simulate_ai(ai)
        self.assertFalse(os.path.exists(os.path.join(self.temp_dir, "del.md")))

    def test_append_file(self):
        """AI 请求追加文件：【调用：append_file({"path": "app.md", "content": "追加"})】"""
        with open(os.path.join(self.temp_dir, "app.md"), "w") as f:
            f.write("原内容")
        ai = '追加内容。\n【调用：append_file({"path": "app.md", "content": "\\n追加"})】\n完成。'
        clean, results = self._simulate_ai(ai)
        with open(os.path.join(self.temp_dir, "app.md")) as f:
            self.assertEqual(f.read(), "原内容\n追加")

    def test_change_dir(self):
        """AI 请求切换目录：【调用：change_dir({"path": "."})】"""
        ai = '切换目录。\n【调用：change_dir({"path": "."})】\n完成。'
        clean, results = self._simulate_ai(ai)
        self.assertTrue(any("✅" in r for r in results))

    # ========== 网络搜索 ==========
    def test_search_web(self):
        """AI 请求搜索：【调用：search_web({"query": "Python"})】"""
        self.web_c.search.return_value = (
            [{"title": "Python 官网", "url": "https://python.org", "snippet": "Python 官网"}],
            None
        )
        ai = '搜索一下。\n【调用：search_web({"query": "Python"})】\n结果如上。'
        clean, results = self._simulate_ai(ai)
        self.assertTrue(any("Python 官网" in r for r in results))

    def test_fetch_web(self):
        """AI 请求抓取网页：【调用：fetch_web({"url": "https://example.com"})】"""
        self.web_c.fetch.return_value = ("网页正文内容", None)
        ai = '抓取网页。\n【调用：fetch_web({"url": "https://example.com"})】\n完成。'
        clean, results = self._simulate_ai(ai)
        self.assertTrue(any("网页正文" in r for r in results))

    # ========== 邮件 ==========
    def test_mail_inbox(self):
        """AI 请求查看收件箱：【调用：mail_inbox({})】"""
        self.mail_c.inbox.return_value = (
            [{"id": "1", "sub": "测试邮件", "from": "a@b.com"}],
            None
        )
        ai = '查看收件箱。\n【调用：mail_inbox({})】\n完毕。'
        clean, results = self._simulate_ai(ai)
        self.assertTrue(any("测试邮件" in r for r in results))

    def test_mail_send(self):
        """AI 请求发送邮件：【调用：mail_send({"to": "a@b.com", "subject": "主题", "body": "正文"})】"""
        self.mail_c.send.return_value = (True, None)
        ai = '发送邮件。\n【调用：mail_send({"to": "a@b.com", "subject": "主题", "body": "正文"})】\n完成。'
        clean, results = self._simulate_ai(ai)
        self.assertTrue(any("✅" in r for r in results))

    # ========== 云盘 ==========
    def test_disk_ls(self):
        """AI 请求列出云盘：【调用：disk_ls({})】"""
        self.disk_c.ls.return_value = (["file1.txt", "file2.txt"], None)
        ai = '查看云盘。\n【调用：disk_ls({})】\n完毕。'
        clean, results = self._simulate_ai(ai)
        self.assertTrue(any("file1.txt" in r for r in results))

    def test_disk_up(self):
        """AI 请求上传文件：【调用：disk_up({"local": "a.txt", "remote": "/a.txt"})】"""
        self.disk_c.up.return_value = (True, "上传成功")
        ai = '上传文件。\n【调用：disk_up({"local": "a.txt", "remote": "/a.txt"})】\n完成。'
        clean, results = self._simulate_ai(ai)
        self.assertTrue(any("上传成功" in r for r in results))

    # ========== 定时任务 ==========
    def test_cron_add(self):
        """AI 请求添加定时任务：【调用：cron_add({"command": "/ls", "interval": 3600})】"""
        ai = '添加定时任务。\n【调用：cron_add({"command": "/ls", "interval": 3600})】\n完成。'
        clean, results = self._simulate_ai(ai)
        self.assertTrue(any("✅" in r for r in results))

    def test_cron_list(self):
        """AI 请求列出定时任务：【调用：cron_list({})】"""
        ai = '列出定时任务。\n【调用：cron_list({})】\n完毕。'
        clean, results = self._simulate_ai(ai)
        self.assertTrue(any("定时" in r or "暂无" in r or "✅" in r for r in results))

    # ========== 会话管理 ==========
    def test_save_session(self):
        """AI 请求保存会话：【调用：save_session({"name": "test_sess"})】"""
        msgs = [{"role": "user", "content": "hi"}]
        ai = '保存会话。\n【调用：save_session({"name": "test_sess"})】\n完成。'
        clean, results = self._simulate_ai(ai, msgs)
        self.assertTrue(any("✅" in r for r in results))

    def test_list_sessions(self):
        """AI 请求列出会话：【调用：list_sessions({})】"""
        ai = '列出会话。\n【调用：list_sessions({})】\n完毕。'
        clean, results = self._simulate_ai(ai)
        # 可能有会话也可能没有，但至少执行了
        self.assertEqual(len(results), 1)

    # ========== 配置管理 ==========
    def test_set_model(self):
        """AI 请求切换模型：【调用：set_model({"name": "glm-4-plus"})】"""
        ai = '切换模型。\n【调用：set_model({"name": "glm-4-plus"})】\n完成。'
        clean, results = self._simulate_ai(ai)
        self.assertEqual(self.cfg["model"], "glm-4-plus")
        self.assertTrue(any("glm-4-plus" in r for r in results))

    def test_set_lang(self):
        """AI 请求切换语言：【调用：set_lang({"code": "en"})】"""
        ai = '切换语言。\n【调用：set_lang({"code": "en"})】\n完成。'
        clean, results = self._simulate_ai(ai)
        self.assertEqual(self.cfg["lang"], "en")

    # ========== 插件命令（保持兼容） ==========
    def test_plugin_command(self):
        """AI 调用插件：【命令：/test_plugin hello】"""
        with patch("fr_cli.command.executor.exec_plugin") as mock_exec:
            ai = '运行插件。\n【命令：/test_plugin hello】\n完成。'
            clean, results = self._simulate_ai(ai)
            mock_exec.assert_called_once()
            self.assertTrue(any("test_plugin" in r for r in results))

    # ========== 兼容旧格式 ==========
    def test_file_operations_compat(self):
        """AI 使用旧 file_operations/write 格式"""
        ai = '保存文件。\nfile_operations\n/write compat.md "兼容测试"\n完成。'
        clean, results = self._simulate_ai(ai)
        self.assertTrue(any("compat.md" in r for r in results))

    # ========== 清理回复测试 ==========
    def test_clean_response_removes_all_markers(self):
        """验证清理后回复中不残留任何调用标记"""
        ai = '我将执行两个操作。\n【调用：write_file({"path": "1.md", "content": "1"})】\n【调用：write_file({"path": "2.md", "content": "2"})】\n完成。'
        clean, results = self._simulate_ai(ai)
        self.assertNotIn("【调用", clean)
        self.assertNotIn("【命令", clean)
        self.assertNotIn("file_operations", clean)

    # ========== 错误处理 ==========
    def test_unknown_tool(self):
        """AI 调用了不存在的工具"""
        ai = '【调用：unknown_tool({"x": 1})】'
        clean, results = self._simulate_ai(ai)
        self.assertTrue(any("Unknown tool" in r for r in results))

    def test_missing_param(self):
        """AI 调用时缺少必需参数"""
        ai = '【调用：write_file({"path": "x.md"})】'  # 缺少 content
        clean, results = self._simulate_ai(ai)
        self.assertTrue(any("Missing required parameter" in r for r in results))

    def test_invalid_json(self):
        """AI 输出的 JSON 参数格式错误"""
        ai = '【调用：write_file({path: "x.md"})】'  # 键未加引号
        clean, results = self._simulate_ai(ai)
        # ast.literal_eval 可能成功解析，或者返回错误
        self.assertEqual(len(results), 1)


if __name__ == "__main__":
    unittest.main()
