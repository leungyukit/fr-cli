"""会话自动恢复测试"""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fr_cli.memory.resume import (
    find_latest_auto_session, is_resumable, format_resume_prompt,
    load_last_n_turns, ask_resume_choice, DEFAULT_LOAD_TURNS,
    RESUME_WINDOW_SECONDS,
)


class TestFindLatest(unittest.TestCase):
    def setUp(self):
        from fr_cli.conf.paths import SESSIONS_AUTO_DIR
        self.real_dir = SESSIONS_AUTO_DIR
        self.tmp = tempfile.mkdtemp(prefix="test_resume_")
        self.patcher = patch("fr_cli.memory.resume.SESSIONS_AUTO_DIR", Path(self.tmp))
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_dir(self):
        # 没有 .json
        result = find_latest_auto_session()
        self.assertIsNone(result)

    def test_empty_dir(self):
        result = find_latest_auto_session()
        self.assertIsNone(result)

    def test_finds_latest(self):
        from fr_cli.core.store import JsonStore
        # 写 2 个会话
        path1 = os.path.join(self.tmp, "2026-01-01_01.json")
        JsonStore(path1, default=dict).write({
            "messages": [{"role": "user", "content": "old"}],
        })
        time.sleep(0.1)
        path2 = os.path.join(self.tmp, "2026-06-28_01.json")
        JsonStore(path2, default=dict).write({
            "messages": [
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "你好!"},
            ],
        })
        result = find_latest_auto_session()
        self.assertIsNotNone(result)
        self.assertEqual(result["filename"], "2026-06-28_01.json")
        self.assertEqual(result["msg_count"], 2)


class TestResumable(unittest.TestCase):
    def test_fresh_session(self):
        s = {"updated_at": time.time() - 60}
        self.assertTrue(is_resumable(s))

    def test_old_session(self):
        s = {"updated_at": time.time() - (RESUME_WINDOW_SECONDS + 100)}
        self.assertFalse(is_resumable(s))

    def test_future_session(self):
        s = {"updated_at": time.time() + 100}
        self.assertFalse(is_resumable(s))

    def test_none(self):
        self.assertFalse(is_resumable(None))


class TestFormatPrompt(unittest.TestCase):
    def test_zh(self):
        s = {"filename": "2026-06-28_01.json", "updated_at": time.time() - 600, "msg_count": 10}
        out = format_resume_prompt(s, lang="zh")
        self.assertIn("检测到上次会话", out)
        self.assertIn("2026-06-28_01.json", out)

    def test_en(self):
        s = {"filename": "x.json", "updated_at": time.time() - 60, "msg_count": 5}
        out = format_resume_prompt(s, lang="en")
        self.assertIn("Previous session", out)


class TestLoadLastN(unittest.TestCase):
    def test_load_basic(self):
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "1"},
            {"role": "assistant", "content": "1r"},
            {"role": "user", "content": "2"},
            {"role": "assistant", "content": "2r"},
        ]
        result = load_last_n_turns(msgs, n_turns=2)
        self.assertEqual(len(result), 4)
        self.assertEqual(result[0]["content"], "1")
        self.assertEqual(result[-1]["content"], "2r")

    def test_load_excludes_system(self):
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        result = load_last_n_turns(msgs, n_turns=5)
        self.assertEqual(len(result), 2)
        # 不应包含 system
        for m in result:
            self.assertNotEqual(m["role"], "system")

    def test_load_more_than_available(self):
        msgs = [
            {"role": "user", "content": "1"},
            {"role": "assistant", "content": "1r"},
        ]
        result = load_last_n_turns(msgs, n_turns=10)
        self.assertEqual(len(result), 2)


class TestAskChoice(unittest.TestCase):
    def test_y(self):
        self.assertEqual(ask_resume_choice(prompt_input=lambda _: "y"), "y")

    def test_n(self):
        self.assertEqual(ask_resume_choice(prompt_input=lambda _: "n"), "n")

    def test_enter(self):
        self.assertEqual(ask_resume_choice(prompt_input=lambda _: ""), "y")

    def test_s(self):
        self.assertEqual(ask_resume_choice(prompt_input=lambda _: "s"), "s")

    def test_eof(self):
        def raise_eof(_):
            raise EOFError
        self.assertIsNone(ask_resume_choice(prompt_input=raise_eof))

    def test_keyboard_interrupt(self):
        def raise_kb(_):
            raise KeyboardInterrupt
        self.assertIsNone(ask_resume_choice(prompt_input=raise_kb))


if __name__ == "__main__":
    unittest.main()