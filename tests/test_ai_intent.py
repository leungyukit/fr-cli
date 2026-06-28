"""AI 意图可视化测试"""
import unittest

from fr_cli.core.ai_intent import (
    parse_intent_block, parse_reason_marker,
    format_intent_preview, enhance_ai_response_with_intent,
    extract_ai_intent_hints,
)


class TestParseIntentBlock(unittest.TestCase):
    def test_basic(self):
        text = """
[AI_INTENT]
tool: search_web
params: {"query": "Python 异步"}
reason: 用户问异步教程
[/AI_INTENT]
【调用：search_web({"query": "Python 异步"})】
"""
        intent = parse_intent_block(text)
        self.assertIsNotNone(intent)
        self.assertEqual(intent["tool"], "search_web")
        self.assertEqual(intent["params"]["query"], "Python 异步")
        self.assertEqual(intent["reason"], "用户问异步教程")

    def test_no_block(self):
        self.assertIsNone(parse_intent_block("no intent here"))

    def test_malformed_json(self):
        text = """
[AI_INTENT]
tool: a
params: not json
reason: r
[/AI_INTENT]
"""
        intent = parse_intent_block(text)
        self.assertIsNotNone(intent)
        self.assertEqual(intent["tool"], "a")
        # params 解析失败会保留 raw
        self.assertIn("params", intent)


class TestParseReasonMarker(unittest.TestCase):
    def test_basic(self):
        text = "【理由：用户问 Python 教程】\n【调用：search_web({})】"
        reason = parse_reason_marker(text)
        self.assertEqual(reason, "用户问 Python 教程")

    def test_no_marker(self):
        self.assertIsNone(parse_reason_marker("no reason"))


class TestFormatPreview(unittest.TestCase):
    def test_basic(self):
        intent = {
            "tool": "search_web",
            "params": {"query": "x"},
            "reason": "用户需要",
        }
        out = format_intent_preview(intent, use_color=False)
        self.assertIn("search_web", out)
        self.assertIn("用户需要", out)

    def test_partial(self):
        intent = {"tool": "a"}
        out = format_intent_preview(intent, use_color=False)
        self.assertIn("a", out)
        self.assertNotIn("参数", out)
        self.assertNotIn("理由", out)


class TestEnhance(unittest.TestCase):
    def test_extract_block(self):
        text = """
[AI_INTENT]
tool: a
params: {}
reason: r
[/AI_INTENT]
执行内容
"""
        cleaned, preview = enhance_ai_response_with_intent(text, use_color=False)
        self.assertNotIn("AI_INTENT", cleaned)
        self.assertIn("执行内容", cleaned)
        self.assertIsNotNone(preview)
        self.assertIn("a", preview)

    def test_extract_reason(self):
        text = "【理由：为了 x】\n实际调用"
        cleaned, preview = enhance_ai_response_with_intent(text, use_color=False)
        self.assertNotIn("理由", cleaned)
        self.assertIn("实际调用", cleaned)
        self.assertIsNotNone(preview)
        self.assertIn("为了 x", preview)

    def test_no_intent(self):
        text = "普通回复,没有意图"
        cleaned, preview = enhance_ai_response_with_intent(text, use_color=False)
        self.assertEqual(cleaned, text)
        self.assertIsNone(preview)


class TestHints(unittest.TestCase):
    def test_hints(self):
        hints = extract_ai_intent_hints()
        self.assertIn("【理由", hints)
        self.assertIn("AI_INTENT", hints)


if __name__ == "__main__":
    unittest.main()