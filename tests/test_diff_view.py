"""Diff 可视化测试"""
import os
import unittest

from fr_cli.ui.diff_view import (
    _parse_unified_diff, render_diff_unified, render_diff_side_by_side,
    diff_stats, render_diff_stats, _pair_diff_lines,
)


SIMPLE_DIFF = """diff --git a/foo.py b/foo.py
index abc..def 100644
--- a/foo.py
+++ b/foo.py
@@ -10,5 +10,6 @@
 def hello():
-    return "hello"
+    return "hi"
+
+def new_func():
+    pass

@@ -20,3 +21,4 @@ def hello():
 ctx line
-deleted line
+added line
 unchanged
"""


class TestParseDiff(unittest.TestCase):
    def test_basic(self):
        hunks = _parse_unified_diff(SIMPLE_DIFF)
        self.assertEqual(len(hunks), 2)
        self.assertEqual(hunks[0]["old_start"], 10)
        self.assertEqual(hunks[0]["new_start"], 10)
        self.assertEqual(hunks[1]["old_start"], 20)
        self.assertEqual(hunks[1]["new_start"], 21)

    def test_empty(self):
        hunks = _parse_unified_diff("")
        self.assertEqual(hunks, [])

    def test_no_hunks(self):
        hunks = _parse_unified_diff("diff --git a/foo b/foo\n--- a/foo\n+++ b/foo\n")
        self.assertEqual(hunks, [])

    def test_line_counts(self):
        hunks = _parse_unified_diff(SIMPLE_DIFF)
        # 第一个 hunk
        adds = sum(1 for k, _ in hunks[0]["lines"] if k == "add")
        dels = sum(1 for k, _ in hunks[0]["lines"] if k == "del")
        self.assertEqual(adds, 4)  # return "hi" / 空 / def new_func() / pass
        self.assertEqual(dels, 1)


class TestRenderUnified(unittest.TestCase):
    def test_basic(self):
        out = render_diff_unified(SIMPLE_DIFF, use_color=False)
        self.assertIn("@@", out)
        self.assertIn('return "hello"', out)
        self.assertIn('return "hi"', out)

    def test_color_markers(self):
        out = render_diff_unified(SIMPLE_DIFF, use_color=True)
        # ANSI 颜色码
        self.assertIn("\033[", out)

    def test_empty(self):
        out = render_diff_unified("", use_color=False)
        self.assertIn("no diff", out)

    def test_no_color(self):
        out = render_diff_unified(SIMPLE_DIFF, use_color=False)
        self.assertNotIn("\033[", out)


class TestRenderSideBySide(unittest.TestCase):
    def test_basic(self):
        out = render_diff_side_by_side(SIMPLE_DIFF, use_color=False)
        self.assertIn("OLD", out)
        self.assertIn("NEW", out)
        self.assertIn("@@", out)

    def test_empty(self):
        out = render_diff_side_by_side("", use_color=False)
        self.assertIn("no diff", out)


class TestPairDiffLines(unittest.TestCase):
    def test_ctx(self):
        lines = [("ctx", "hello")]
        paired = _pair_diff_lines(lines)
        self.assertEqual(paired[0][0], "ctx")
        self.assertEqual(paired[0][1], "hello")
        self.assertEqual(paired[0][2], "hello")

    def test_mod_pairing(self):
        lines = [("del", "old"), ("add", "new")]
        paired = _pair_diff_lines(lines)
        self.assertEqual(len(paired), 1)
        self.assertEqual(paired[0][0], "mod")
        self.assertEqual(paired[0][1], "old")
        self.assertEqual(paired[0][2], "new")

    def test_add_grouping(self):
        lines = [("add", "a"), ("add", "b")]
        paired = _pair_diff_lines(lines)
        self.assertEqual(len(paired), 2)
        for p in paired:
            self.assertEqual(p[0], "add")


class TestStats(unittest.TestCase):
    def test_basic(self):
        stats = diff_stats(SIMPLE_DIFF)
        self.assertEqual(stats["files"], 1)
        self.assertEqual(stats["hunks"], 2)
        self.assertGreater(stats["added"], 0)
        self.assertGreater(stats["deleted"], 0)

    def test_empty(self):
        stats = diff_stats("")
        self.assertEqual(stats, {"added": 0, "deleted": 0, "hunks": 0, "files": 0})

    def test_format_zh(self):
        text = render_diff_stats(SIMPLE_DIFF, "zh")
        self.assertIn("Diff", text)
        self.assertIn("+", text)

    def test_format_en(self):
        text = render_diff_stats(SIMPLE_DIFF, "en")
        self.assertIn("Diff", text)


if __name__ == "__main__":
    unittest.main()