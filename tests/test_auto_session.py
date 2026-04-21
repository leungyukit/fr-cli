"""
自动会话存档测试 —— 按日期编号 session
"""
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from fr_cli.memory import session as session_mod


class TestAutoSession(unittest.TestCase):

    def setUp(self):
        """每个测试用例使用临时目录隔离"""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.original_dir = session_mod.SESSION_DIR
        session_mod.SESSION_DIR = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()
        session_mod.SESSION_DIR = self.original_dir

    def test_ensure_dir_creates_directory(self):
        target = Path(self.tmpdir.name) / "nested"
        session_mod.SESSION_DIR = target
        session_mod._ensure_dir()
        self.assertTrue(target.exists())

    def test_get_next_session_filename_first(self):
        fname = session_mod._get_next_session_filename()
        today = datetime.now().strftime("%Y-%m-%d")
        self.assertEqual(fname, f"{today}_01.json")

    def test_get_next_session_filename_increment(self):
        today = datetime.now().strftime("%Y-%m-%d")
        # 预先创建两个文件
        (session_mod.SESSION_DIR / f"{today}_01.json").write_text("{}")
        (session_mod.SESSION_DIR / f"{today}_02.json").write_text("{}")
        fname = session_mod._get_next_session_filename()
        self.assertEqual(fname, f"{today}_03.json")

    def test_create_and_update_session(self):
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hello"},
        ]
        path = session_mod.create_session(msgs)
        self.assertIsNotNone(path)
        self.assertTrue(Path(path).exists())

        # 读取验证
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["messages"], msgs)
        self.assertIn("created_at", data)

        # 更新
        msgs.append({"role": "assistant", "content": "hi"})
        ok = session_mod.update_session(path, msgs)
        self.assertTrue(ok)

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data["messages"]), 3)
        self.assertEqual(data["messages"][-1]["content"], "hi")

    def test_list_sessions(self):
        today = datetime.now().strftime("%Y-%m-%d")
        msgs = [{"role": "user", "content": "x"}]
        p1 = session_mod.create_session(msgs)
        p2 = session_mod.create_session(msgs)

        sessions = session_mod.list_sessions()
        self.assertEqual(len(sessions), 2)
        # 按时间倒序，后创建的在前
        self.assertEqual(sessions[0]["filename"], f"{today}_02.json")
        self.assertEqual(sessions[1]["filename"], f"{today}_01.json")

    def test_load_session(self):
        msgs = [
            {"role": "system", "content": "old_sys"},
            {"role": "user", "content": "hello"},
        ]
        session_mod.create_session(msgs)

        ok, loaded_msgs, fname = session_mod.load_session(1, current_system_prompt="new_sys")
        self.assertTrue(ok)
        self.assertEqual(loaded_msgs[0]["content"], "new_sys")
        self.assertEqual(loaded_msgs[1]["content"], "hello")

    def test_load_session_invalid_index(self):
        ok, _, _ = session_mod.load_session(99)
        self.assertFalse(ok)

    def test_delete_session(self):
        msgs = [{"role": "user", "content": "x"}]
        session_mod.create_session(msgs)

        ok = session_mod.delete_session(1)
        self.assertTrue(ok)
        self.assertEqual(len(session_mod.list_sessions()), 0)

    def test_delete_session_invalid_index(self):
        ok = session_mod.delete_session(99)
        self.assertFalse(ok)

    def test_update_session_none_path(self):
        ok = session_mod.update_session(None, [])
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
