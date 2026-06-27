"""STT 语音输入测试"""
import os
import tempfile
import unittest

from fr_cli.weapon.voice_input import (
    is_supported_audio, validate_audio_file, SUPPORTED_FORMATS,
)


class TestAudioFormat(unittest.TestCase):
    def test_supported_formats_set(self):
        self.assertIsInstance(SUPPORTED_FORMATS, set)
        self.assertIn(".mp3", SUPPORTED_FORMATS)
        self.assertIn(".wav", SUPPORTED_FORMATS)

    def test_is_supported_audio(self):
        self.assertTrue(is_supported_audio("/x/y.mp3"))
        self.assertTrue(is_supported_audio("/x/y.WAV"))  # 大小写不敏感
        self.assertFalse(is_supported_audio("/x/y.txt"))
        self.assertFalse(is_supported_audio("/x/y"))


class TestValidateAudio(unittest.TestCase):
    def test_nonexistent(self):
        v = validate_audio_file("/nonexistent/foo.mp3")
        self.assertFalse(v["ok"])
        self.assertIn("不存在", v["error"])

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            path = f.name
        try:
            v = validate_audio_file(path)
            self.assertFalse(v["ok"])
        finally:
            os.unlink(path)

    def test_valid_mp3(self):
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(b"ID3" + b"\x00" * 1024)  # 假装 1KB mp3
            path = f.name
        try:
            v = validate_audio_file(path)
            self.assertTrue(v["ok"])
            self.assertEqual(v["format"], "mp3")
            self.assertGreater(v["size"], 0)
        finally:
            os.unlink(path)

    def test_too_large(self):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            # 写一个超大文件指针(不实际写磁盘)
            path = f.name
        try:
            # 模拟大文件
            with open(path, "wb") as f:
                f.seek(101 * 1024 * 1024)
                f.write(b"\x00")
            v = validate_audio_file(path)
            self.assertFalse(v["ok"])
            self.assertIn("过大", v["error"])
        finally:
            os.unlink(path)


class TestTranscribeFallback(unittest.TestCase):
    """测试没有 MCP / 没有本地 whisper 时的错误处理"""

    def test_transcribe_no_file(self):
        from fr_cli.weapon.voice_input import transcribe_audio
        r = transcribe_audio("/nonexistent.mp3")
        self.assertFalse(r["ok"])

    def test_transcribe_unsupported_format(self):
        from fr_cli.weapon.voice_input import transcribe_audio
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"hello")
            path = f.name
        try:
            r = transcribe_audio(path)
            self.assertFalse(r["ok"])
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()