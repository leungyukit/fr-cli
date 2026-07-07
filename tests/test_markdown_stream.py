"""Streaming Markdown 渲染测试"""
import unittest

from fr_cli.ui.markdown_stream import StreamingMarkdownRenderer


class TestRendererBasic(unittest.TestCase):
    def test_heading(self):
        r = StreamingMarkdownRenderer(use_color=False)
        out = r.feed("# Hello\n")
        self.assertIn("Hello", out)
        self.assertIn("#", out)

    def test_paragraph(self):
        r = StreamingMarkdownRenderer(use_color=False)
        out = r.feed("这是一段普通文本\n")
        self.assertIn("这是一段普通文本", out)

    def test_empty_line(self):
        r = StreamingMarkdownRenderer(use_color=False)
        out = r.feed("\n")
        self.assertEqual(out, "")

    def test_inline_code(self):
        r = StreamingMarkdownRenderer(use_color=False)
        out = r.feed("看 `print()` 函数\n")
        self.assertIn("print()", out)

    def test_inline_code_color(self):
        r = StreamingMarkdownRenderer(use_color=True)
        out = r.feed("看 `print()`\n")
        self.assertIn("\033[", out)

    def test_bold(self):
        r = StreamingMarkdownRenderer(use_color=False)
        out = r.feed("这是 **粗体** 文本\n")
        self.assertIn("粗体", out)

    def test_italic(self):
        r = StreamingMarkdownRenderer(use_color=False)
        out = r.feed("这是 *斜体* 文本\n")
        self.assertIn("斜体", out)


class TestRendererCodeBlock(unittest.TestCase):
    def test_code_block(self):
        r = StreamingMarkdownRenderer(use_color=False)
        out1 = r.feed("```python\n")
        out2 = r.feed("print('hi')\n")
        out3 = r.feed("```\n")
        # 开始标记
        self.assertIn("python", out1)
        # 代码内容
        self.assertIn("print('hi')", out2)
        # 结束
        self.assertEqual(r.state, "NORMAL")

    def test_code_block_color(self):
        r = StreamingMarkdownRenderer(use_color=True)
        out = r.feed("```\nprint(1)\n")
        self.assertIn("\033[", out)


class TestRendererLists(unittest.TestCase):
    def test_unordered(self):
        r = StreamingMarkdownRenderer(use_color=False)
        out = r.feed("- item 1\n- item 2\n")
        self.assertIn("item 1", out)
        self.assertIn("item 2", out)

    def test_ordered(self):
        r = StreamingMarkdownRenderer(use_color=False)
        out = r.feed("1. first\n2. second\n")
        self.assertIn("first", out)
        self.assertIn("1.", out)

    def test_nested(self):
        r = StreamingMarkdownRenderer(use_color=False)
        out = r.feed("- a\n  - b\n")
        self.assertIn("a", out)
        self.assertIn("b", out)


class TestRendererQuote(unittest.TestCase):
    def test_quote(self):
        r = StreamingMarkdownRenderer(use_color=False)
        out = r.feed("> 引用\n")
        self.assertIn("引用", out)
        self.assertIn("│", out)


class TestRendererHrule(unittest.TestCase):
    def test_hrule(self):
        r = StreamingMarkdownRenderer(use_color=False)
        out = r.feed("---\n")
        self.assertIn("─", out)


class TestRendererFlush(unittest.TestCase):
    def test_flush(self):
        r = StreamingMarkdownRenderer(use_color=False)
        r.feed("剩余内容没换行")
        rem = r.flush()
        self.assertIn("剩余内容没换行", rem)


class TestRendererStats(unittest.TestCase):
    def test_stats(self):
        r = StreamingMarkdownRenderer(use_color=False)
        r.feed("# title\n")
        r.feed("paragraph\n")
        s = r.stats()
        self.assertEqual(s["state"], "NORMAL")
        self.assertGreater(s["lines"], 0)


class TestRendererComplex(unittest.TestCase):
    def test_full_doc(self):
        r = StreamingMarkdownRenderer(use_color=False)
        text = """# 标题

这是一段描述

- 列表项 1
- 列表项 2

```python
print("hello")
```

## 子标题

| 列1 | 列2 |
|-----|-----|
| A   | B   |
"""
        out = ""
        for chunk in text.split("\n"):
            out += r.feed(chunk + "\n")
        out += r.flush()
        self.assertIn("标题", out)
        self.assertIn("列表项 1", out)
        self.assertIn('print("hello")', out)
        self.assertIn("子标题", out)


if __name__ == "__main__":
    unittest.main()
