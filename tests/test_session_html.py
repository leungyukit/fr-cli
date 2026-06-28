"""会话 HTML 时间线测试"""
import json
import os
import tempfile
import unittest

from fr_cli.weapon.session_html import (
    generate_timeline_html, export_session_to_html,
    _render_content, _extract_tool_calls, _render_inline_md,
)


SAMPLE_MESSAGES = [
    {"role": "system", "content": "你是助手"},
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好!有什么需要?\n\n```python\nprint('hi')\n```"},
    {"role": "user", "content": "搜索 Python 异步"},
    {"role": "assistant", "content": (
        "【调用：search_web({\"query\": \"Python asyncio\"})】\n"
        "好的,这是搜索结果..."
    )},
]


class TestRenderInline(unittest.TestCase):
    def test_escape(self):
        out = _render_inline_md("<script>")
        self.assertIn("&lt;", out)

    def test_inline_code(self):
        out = _render_inline_md("看 `print()`")
        self.assertIn("<code", out)

    def test_bold(self):
        out = _render_inline_md("**粗体**")
        self.assertIn("<strong>", out)

    def test_link(self):
        out = _render_inline_md("[链接](https://example.com)")
        self.assertIn('href="https://example.com"', out)


class TestExtractToolCalls(unittest.TestCase):
    def test_basic(self):
        text = "【调用：search_web({\"query\": \"x\"})】"
        calls = _extract_tool_calls(text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["tool"], "search_web")

    def test_multiple(self):
        text = "【调用：a({})】\n中间\n【调用：b({})】"
        calls = _extract_tool_calls(text)
        self.assertEqual(len(calls), 2)

    def test_no_calls(self):
        self.assertEqual(_extract_tool_calls("hello"), [])


class TestRenderContent(unittest.TestCase):
    def test_plain_text(self):
        out = _render_content("hello world")
        self.assertIn("hello world", out)

    def test_code_block(self):
        out = _render_content("```python\nprint(1)\n```")
        self.assertIn("<pre", out)
        self.assertIn("print(1)", out)
        self.assertIn("lang-python", out)

    def test_inline_format(self):
        out = _render_content("看 `code`")
        self.assertIn("inline-code", out)


class TestGenerateHTML(unittest.TestCase):
    def test_basic(self):
        html = generate_timeline_html(SAMPLE_MESSAGES, title="测试", session_filename="test.json")
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("测试", html)
        self.assertIn("user", html)
        self.assertIn("assistant", html)

    def test_tool_call_section(self):
        html = generate_timeline_html(SAMPLE_MESSAGES, title="x")
        # 应该包含工具调用面板
        self.assertIn("tool-call", html)
        self.assertIn("search_web", html)

    def test_code_block_rendered(self):
        html = generate_timeline_html(SAMPLE_MESSAGES, title="x")
        self.assertIn("code-block", html)
        # HTML 会转义引号 → &#x27;
        self.assertIn("print(&#x27;hi&#x27;)", html)


class TestExport(unittest.TestCase):
    def test_export_to_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = os.path.join(tmp, "session.json")
            with open(session, "w", encoding="utf-8") as f:
                json.dump({"messages": SAMPLE_MESSAGES}, f, ensure_ascii=False)

            output = os.path.join(tmp, "out.html")
            result = export_session_to_html(session, output_path=output, auto_open=False)
            self.assertTrue(result["ok"])
            self.assertTrue(os.path.exists(output))
            with open(output) as f:
                content = f.read()
            self.assertIn("<!DOCTYPE html>", content)

    def test_export_no_messages(self):
        result = export_session_to_html("/nonexistent.json")
        self.assertFalse(result["ok"])

    def test_export_default_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = os.path.join(tmp, "session.json")
            with open(session, "w", encoding="utf-8") as f:
                json.dump({"messages": SAMPLE_MESSAGES}, f, ensure_ascii=False)

            # 不指定 output_path,用默认 ~/.fr_cli/exports/
            # 这个会真实写盘(影响测试隔离),但 export_dir 会创建
            # 简单测一下 result 结构
            result = export_session_to_html(session, output_path=None, auto_open=False)
            self.assertTrue(result["ok"])
            # 清理
            try:
                os.remove(result["path"])
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()