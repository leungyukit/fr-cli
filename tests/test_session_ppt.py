"""会话导出 PPT 测试"""
import json
import os
import tempfile
import unittest

from fr_cli.weapon.session_to_ppt import (
    load_session_messages, extract_conversation_pairs,
    clean_markdown_for_ppt, build_outline,
    export_to_markdown, export_to_pptx,
)


def _make_session_file(tmp: str, name: str = "test.json"):
    """创建一个测试会话文件"""
    path = os.path.join(tmp, name)
    data = {
        "filename": name,
        "messages": [
            {"role": "system", "content": "你是助手"},
            {"role": "user", "content": "你好,介绍一下 fr-cli"},
            {"role": "assistant", "content": "fr-cli 是一个 AI 终端工具。\n\n## 特性\n- 简洁\n- 强大"},
            {"role": "user", "content": "支持哪些模型?"},
            {"role": "assistant", "content": "支持 25+ 模型,包括 zhipu、deepseek、kimi 等。"},
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return path


class TestLoadSession(unittest.TestCase):
    def test_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _make_session_file(tmp)
            msgs = load_session_messages(path)
            self.assertEqual(len(msgs), 5)

    def test_load_missing(self):
        msgs = load_session_messages("/nonexistent")
        self.assertEqual(msgs, [])


class TestExtractPairs(unittest.TestCase):
    def test_basic(self):
        msgs = [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "1"},
            {"role": "user", "content": "b"},
            {"role": "assistant", "content": "2"},
        ]
        pairs = extract_conversation_pairs(msgs)
        self.assertEqual(len(pairs), 2)
        self.assertEqual(pairs[0][0]["content"], "a")
        self.assertEqual(pairs[0][1]["content"], "1")

    def test_user_only(self):
        msgs = [
            {"role": "user", "content": "lonely"},
        ]
        pairs = extract_conversation_pairs(msgs)
        self.assertEqual(len(pairs), 1)
        self.assertIsNone(pairs[0][1])

    def test_skip_system(self):
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "a"},
        ]
        pairs = extract_conversation_pairs(msgs)
        self.assertEqual(len(pairs), 1)


class TestCleanMarkdown(unittest.TestCase):
    def test_code_block_removed(self):
        text = "before\n```python\nprint(1)\n```\nafter"
        cleaned = clean_markdown_for_ppt(text)
        self.assertIn("before", cleaned)
        self.assertIn("after", cleaned)
        self.assertNotIn("print(1)", cleaned)

    def test_inline_code(self):
        cleaned = clean_markdown_for_ppt("看 `print()` 函数")
        self.assertIn("print()", cleaned)
        self.assertNotIn("`", cleaned)

    def test_link(self):
        cleaned = clean_markdown_for_ppt("[链接](https://example.com)")
        self.assertIn("链接", cleaned)
        self.assertNotIn("https", cleaned)

    def test_heading_marks(self):
        cleaned = clean_markdown_for_ppt("# 标题\n## 子标题")
        self.assertNotIn("#", cleaned)

    def test_length_limit(self):
        long_text = "x" * 5000
        cleaned = clean_markdown_for_ppt(long_text, max_length=100)
        self.assertLessEqual(len(cleaned), 105)  # 100 + "..."


class TestBuildOutline(unittest.TestCase):
    def setUp(self):
        self.msgs = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好!有什么需要帮助?"},
            {"role": "user", "content": "推荐一本书"},
            {"role": "assistant", "content": "《深入理解计算机系统》"},
        ]

    def test_outline_structure(self):
        outline = build_outline(self.msgs, title="测试")
        # 封面 + 2 轮 × 2 张 + 总结 = 6 张
        self.assertEqual(outline[0]["type"], "cover")
        self.assertEqual(outline[-1]["type"], "summary")

        # user/ai 交替
        content_types = [o["type"] for o in outline if o["type"] in ("user", "ai")]
        self.assertEqual(content_types.count("user"), 2)
        self.assertEqual(content_types.count("ai"), 2)

    def test_max_slides(self):
        outline = build_outline(self.msgs, max_slides=1)
        # 限制后只剩 1 轮
        content_types = [o["type"] for o in outline if o["type"] in ("user", "ai")]
        self.assertLessEqual(len(content_types), 2)


class TestExportMarkdown(unittest.TestCase):
    def test_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            outline = [
                {"type": "cover", "title": "测试", "subtitle": "2026-06-28"},
                {"type": "user", "title": "需求 #1", "content": "问题"},
                {"type": "ai", "title": "回答 #1", "content": "答案"},
                {"type": "summary", "title": "总结", "content": "搞定"},
            ]
            out_path = os.path.join(tmp, "out.md")
            result = export_to_markdown(outline, out_path)
            self.assertTrue(result["ok"])
            self.assertTrue(os.path.exists(out_path))
            with open(out_path) as f:
                content = f.read()
            self.assertIn("测试", content)
            self.assertIn("问题", content)
            self.assertIn("答案", content)
            self.assertIn("👤", content)
            self.assertIn("🤖", content)


class TestExportPptx(unittest.TestCase):
    def test_no_pptx(self):
        # mock pptx 不存在
        import sys
        original = sys.modules.get("pptx", None)
        sys.modules["pptx"] = None
        try:
            result = export_to_pptx([{"type": "cover", "title": "x", "subtitle": "y"}], "/tmp/x.pptx")
            self.assertFalse(result["ok"])
            self.assertIn("python-pptx", result["error"])
        finally:
            if original is not None:
                sys.modules["pptx"] = original

    def test_with_pptx(self):
        # 跳过 if pptx not installed
        try:
            from pptx import Presentation
        except ImportError:
            self.skipTest("python-pptx not installed")

        with tempfile.TemporaryDirectory() as tmp:
            outline = [
                {"type": "cover", "title": "t", "subtitle": "s"},
                {"type": "user", "title": "Q1", "content": "问题"},
                {"type": "ai", "title": "A1", "content": "回答"},
                {"type": "summary", "title": "结", "content": "完成"},
            ]
            out = os.path.join(tmp, "out.pptx")
            result = export_to_pptx(outline, out)
            self.assertTrue(result["ok"])
            self.assertTrue(os.path.exists(out))
            self.assertGreater(result["slides"], 0)


class TestExportSessionToPpt(unittest.TestCase):
    def test_auto_format_with_real_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _make_session_file(tmp)
            from fr_cli.weapon.session_to_ppt import export_session_to_ppt
            result = export_session_to_ppt(path, format="markdown")
            self.assertTrue(result["ok"])
            self.assertEqual(result["format"], "markdown")
            self.assertTrue(os.path.exists(result["path"]))

    def test_no_session(self):
        from fr_cli.weapon.session_to_ppt import export_session_to_ppt
        result = export_session_to_ppt("/nonexistent.json")
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
