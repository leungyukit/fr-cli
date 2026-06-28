"""TTS 流式合成测试"""
import unittest
from unittest.mock import patch, MagicMock

from fr_cli.weapon.local_tts import speak_stream


class TestSpeakStream(unittest.TestCase):
    @patch("fr_cli.weapon.local_tts.speak")
    @patch("fr_cli.weapon.local_tts.detect_tts_engine")
    def test_no_engine(self, mock_detect, mock_speak):
        mock_detect.return_value = {"ok": False, "error": "no engine"}
        r = speak_stream("hello world")
        self.assertFalse(r["ok"])

    @patch("fr_cli.weapon.local_tts.speak")
    @patch("fr_cli.weapon.local_tts.detect_tts_engine")
    def test_empty_text(self, mock_detect, mock_speak):
        mock_detect.return_value = {"ok": True, "engine": "say", "platform": "Darwin"}
        r = speak_stream("")
        self.assertFalse(r["ok"])

    @patch("fr_cli.weapon.local_tts.speak")
    @patch("fr_cli.weapon.local_tts.detect_tts_engine")
    def test_short_text_one_chunk(self, mock_detect, mock_speak):
        mock_detect.return_value = {"ok": True, "engine": "say", "platform": "Darwin"}
        mock_speak.return_value = {"ok": True}
        r = speak_stream("hi", chunk_size=200)
        self.assertTrue(r["ok"])
        self.assertEqual(r["chunks"], 1)
        # 验证 speak 被调一次
        self.assertEqual(mock_speak.call_count, 1)

    @patch("fr_cli.weapon.local_tts.speak")
    @patch("fr_cli.weapon.local_tts.detect_tts_engine")
    def test_long_text_split_by_sentence(self, mock_detect, mock_speak):
        mock_detect.return_value = {"ok": True, "engine": "say", "platform": "Darwin"}
        mock_speak.return_value = {"ok": True}
        # 用很长的句子确保触发 chunk_size
        text = (
            "这是第一句话。这是一个非常非常长的句子用来测试分块功能。"
            "这是第三句话!这是第四句话?这是第五句话。"
            "继续添加更多文字以确保超过 chunk_size 限制。"
        )
        r = speak_stream(text, chunk_size=30)
        self.assertTrue(r["ok"])
        # 应该拆成多块
        self.assertGreater(r["chunks"], 1)
        self.assertEqual(mock_speak.call_count, r["chunks"])

    @patch("fr_cli.weapon.local_tts.speak")
    @patch("fr_cli.weapon.local_tts.detect_tts_engine")
    def test_long_text_split_by_size(self, mock_detect, mock_speak):
        mock_detect.return_value = {"ok": True, "engine": "say", "platform": "Darwin"}
        mock_speak.return_value = {"ok": True}
        # 没有句末标点,纯长字符串
        text = "a" * 500
        r = speak_stream(text, chunk_size=100)
        self.assertTrue(r["ok"])
        # 应该按 chunk_size 拆
        self.assertEqual(r["chunks"], 5)
        self.assertEqual(mock_speak.call_count, 5)

    @patch("fr_cli.weapon.local_tts.speak")
    @patch("fr_cli.weapon.local_tts.detect_tts_engine")
    def test_on_chunk_callback(self, mock_detect, mock_speak):
        mock_detect.return_value = {"ok": True, "engine": "say", "platform": "Darwin"}
        mock_speak.return_value = {"ok": True}
        callbacks = []
        def cb(chunk, idx):
            callbacks.append((chunk, idx))
        r = speak_stream("A. B. C.", on_chunk=cb, chunk_size=10)
        self.assertTrue(r["ok"])
        self.assertGreater(len(callbacks), 0)

    @patch("fr_cli.weapon.local_tts.speak")
    @patch("fr_cli.weapon.local_tts.detect_tts_engine")
    def test_partial_failure(self, mock_detect, mock_speak):
        mock_detect.return_value = {"ok": True, "engine": "say", "platform": "Darwin"}
        # 第一个块成功,第二个块失败
        mock_speak.side_effect = [
            {"ok": True},
            Exception("boom"),
        ]
        text = "A. B. C."
        r = speak_stream(text, chunk_size=5)
        # 应该有 errors
        self.assertIn("errors", r)
        self.assertGreater(len(r["errors"]), 0)


if __name__ == "__main__":
    unittest.main()