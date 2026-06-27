"""Plan undo/redo 撤销栈测试"""
import os
import tempfile
import unittest
from unittest.mock import patch

from fr_cli.core.plan_undo import (
    push_version, undo, redo, clear_history,
    history_summary, format_history_summary,
    MAX_UNDO_DEPTH,
)


class TestPlanUndo(unittest.TestCase):
    def setUp(self):
        self.session_id = "test_session"
        self.tmp = tempfile.mkdtemp(prefix="test_undo_")
        self.patcher = patch("fr_cli.core.plan_undo.HISTORY_DIR",
                             __import__("pathlib").Path(self.tmp))
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _plan(self, version: int):
        return {"goal": f"plan v{version}", "steps": [], "version": version}

    def test_push_first(self):
        history = push_version(self.session_id, self._plan(1))
        self.assertEqual(history["current"]["version"], 1)
        self.assertEqual(len(history["undo_stack"]), 0)
        self.assertEqual(len(history["redo_stack"]), 0)

    def test_push_second(self):
        push_version(self.session_id, self._plan(1))
        history = push_version(self.session_id, self._plan(2))
        self.assertEqual(history["current"]["version"], 2)
        self.assertEqual(len(history["undo_stack"]), 1)
        self.assertEqual(history["undo_stack"][0]["version"], 1)

    def test_undo_one(self):
        push_version(self.session_id, self._plan(1))
        push_version(self.session_id, self._plan(2))
        result = undo(self.session_id)
        self.assertIsNotNone(result)
        self.assertEqual(result["version"], 1)

    def test_undo_multiple(self):
        for v in [1, 2, 3]:
            push_version(self.session_id, self._plan(v))
        result = undo(self.session_id, steps=2)
        self.assertEqual(result["version"], 1)

    def test_undo_empty(self):
        result = undo(self.session_id)
        self.assertIsNone(result)

    def test_undo_more_than_available(self):
        push_version(self.session_id, self._plan(1))
        push_version(self.session_id, self._plan(2))
        # 请求回退 5 步,但只有 1 步可回退
        result = undo(self.session_id, steps=5)
        # 应该是最早的版本(1)
        self.assertEqual(result["version"], 1)

    def test_redo(self):
        push_version(self.session_id, self._plan(1))
        push_version(self.session_id, self._plan(2))
        undo(self.session_id)
        result = redo(self.session_id)
        self.assertEqual(result["version"], 2)

    def test_redo_empty(self):
        result = redo(self.session_id)
        self.assertIsNone(result)

    def test_push_clears_redo(self):
        push_version(self.session_id, self._plan(1))
        push_version(self.session_id, self._plan(2))
        undo(self.session_id)
        # redo_stack 应该有 1 个
        summary = history_summary(self.session_id)
        self.assertEqual(summary["redo_count"], 1)
        # 现在 push 新版本,redo 应被清空
        push_version(self.session_id, self._plan(3))
        summary = history_summary(self.session_id)
        self.assertEqual(summary["redo_count"], 0)

    def test_max_depth(self):
        for v in range(MAX_UNDO_DEPTH + 5):
            push_version(self.session_id, self._plan(v))
        summary = history_summary(self.session_id)
        self.assertLessEqual(summary["undo_count"], MAX_UNDO_DEPTH)

    def test_clear_history(self):
        push_version(self.session_id, self._plan(1))
        push_version(self.session_id, self._plan(2))
        result = clear_history(self.session_id)
        self.assertTrue(result)
        summary = history_summary(self.session_id)
        self.assertEqual(summary["undo_count"], 0)
        self.assertFalse(summary["has_current"])

    def test_history_summary_zh(self):
        push_version(self.session_id, self._plan(1))
        push_version(self.session_id, self._plan(2))
        text = format_history_summary(self.session_id, "zh")
        self.assertIn("撤销", text)
        self.assertIn("1", text)

    def test_history_summary_en(self):
        push_version(self.session_id, self._plan(1))
        text = format_history_summary(self.session_id, "en")
        self.assertIn("undo", text.lower())


if __name__ == "__main__":
    unittest.main()