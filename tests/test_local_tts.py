"""本地 TTS 测试"""
import platform
import unittest
from unittest.mock import patch, MagicMock

from fr_cli.weapon.local_tts import (
    detect_tts_engine, _parse_say_voices, list_voices,
    format_voices,
)


class TestParseSayVoices(unittest.TestCase):
    def test_parse(self):
        text = """Samantha               en_US    # Sample voice
Tingting               zh_CN    # Chinese female
"""
        voices = _parse_say_voices(text)
        self.assertEqual(len(voices), 2)
        self.assertEqual(voices[0]["name"], "Samantha")
        self.assertEqual(voices[0]["lang"], "en_US")

    def test_parse_with_comments(self):
        text = "# Comment line\n\nSamantha en_US\n"
        voices = _parse_say_voices(text)
        self.assertEqual(len(voices), 1)

    def test_parse_empty(self):
        voices = _parse_say_voices("")
        self.assertEqual(voices, [])


class TestDetectEngine(unittest.TestCase):
    @patch("shutil.which")
    @patch("platform.system")
    def test_macos_with_say(self, mock_sys, mock_which):
        mock_sys.return_value = "Darwin"
        mock_which.return_value = "/usr/bin/say"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stderr="Samantha en_US\nTingting zh_CN\n"
            )
            r = detect_tts_engine()
            self.assertTrue(r["ok"])
            self.assertEqual(r["engine"], "say")
            self.assertEqual(r["platform"], "Darwin")

    @patch("shutil.which")
    @patch("platform.system")
    def test_macos_no_say(self, mock_sys, mock_which):
        mock_sys.return_value = "Darwin"
        mock_which.return_value = None
        r = detect_tts_engine()
        self.assertFalse(r["ok"])

    @patch("shutil.which")
    @patch("platform.system")
    def test_linux_espeak(self, mock_sys, mock_which):
        mock_sys.return_value = "Linux"
        # espeak 在 PATH 里
        mock_which.side_effect = lambda cmd: "/usr/bin/espeak" if cmd == "espeak" else None
        r = detect_tts_engine()
        self.assertTrue(r["ok"])
        self.assertEqual(r["engine"], "espeak")

    @patch("shutil.which")
    @patch("platform.system")
    def test_linux_no_engine(self, mock_sys, mock_which):
        mock_sys.return_value = "Linux"
        mock_which.return_value = None
        r = detect_tts_engine()
        self.assertFalse(r["ok"])
        self.assertIn("espeak", r["error"])

    @patch("platform.system")
    def test_windows_with_pywin32(self, mock_sys):
        mock_sys.return_value = "Windows"
        with patch.dict("sys.modules", {"win32com": MagicMock(), "win32com.client": MagicMock()}):
            r = detect_tts_engine()
            self.assertTrue(r["ok"])
            self.assertEqual(r["engine"], "sapi")


class TestSpeak(unittest.TestCase):
    @patch("fr_cli.weapon.local_tts.detect_tts_engine")
    @patch("platform.system", return_value="Darwin")
    @patch("subprocess.run")
    def test_macos_basic(self, mock_run, mock_sys, mock_detect):
        mock_detect.return_value = {"ok": True, "engine": "say", "platform": "Darwin"}
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        from fr_cli.weapon.local_tts import speak
        r = speak("hello")
        self.assertTrue(r["ok"])
        args = mock_run.call_args[0][0]
        self.assertEqual(args[0], "say")
        self.assertIn("hello", args)

    @patch("fr_cli.weapon.local_tts.detect_tts_engine")
    @patch("platform.system", return_value="Darwin")
    @patch("subprocess.run")
    def test_macos_with_voice(self, mock_run, mock_sys, mock_detect):
        mock_detect.return_value = {"ok": True, "engine": "say", "platform": "Darwin"}
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        from fr_cli.weapon.local_tts import speak
        r = speak("hi", voice="Tingting")
        self.assertTrue(r["ok"])
        args = mock_run.call_args[0][0]
        self.assertIn("-v", args)
        self.assertIn("Tingting", args)

    @patch("fr_cli.weapon.local_tts.detect_tts_engine")
    @patch("platform.system", return_value="Darwin")
    @patch("subprocess.run")
    def test_macos_to_file(self, mock_run, mock_sys, mock_detect):
        mock_detect.return_value = {"ok": True, "engine": "say", "platform": "Darwin"}
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        from fr_cli.weapon.local_tts import speak
        r = speak("hi", output_file="/tmp/out.aiff")
        self.assertTrue(r["ok"])
        args = mock_run.call_args[0][0]
        self.assertIn("-o", args)
        self.assertIn("/tmp/out.aiff", args)

    @patch("fr_cli.weapon.local_tts.detect_tts_engine")
    @patch("platform.system", return_value="Darwin")
    @patch("subprocess.run")
    def test_macos_fail(self, mock_run, mock_sys, mock_detect):
        mock_detect.return_value = {"ok": True, "engine": "say", "platform": "Darwin"}
        mock_run.return_value = MagicMock(returncode=1, stderr="voice not found")
        from fr_cli.weapon.local_tts import speak
        r = speak("hi", voice="nonexistent")
        self.assertFalse(r["ok"])

    @patch("fr_cli.weapon.local_tts.detect_tts_engine")
    @patch("platform.system", return_value="Linux")
    @patch("shutil.which", side_effect=lambda c: "/usr/bin/espeak" if c == "espeak" else None)
    @patch("subprocess.run")
    def test_linux_espeak(self, mock_run, mock_which, mock_sys, mock_detect):
        mock_detect.return_value = {"ok": True, "engine": "espeak", "platform": "Linux"}
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        from fr_cli.weapon.local_tts import speak
        r = speak("hello")
        self.assertTrue(r["ok"])
        args = mock_run.call_args[0][0]
        self.assertEqual(args[0], "espeak")

    @patch("fr_cli.weapon.local_tts.detect_tts_engine")
    def test_no_engine(self, mock_detect):
        mock_detect.return_value = {"ok": False, "error": "no engine"}
        from fr_cli.weapon.local_tts import speak
        r = speak("hi")
        self.assertFalse(r["ok"])


class TestListVoices(unittest.TestCase):
    @patch("fr_cli.weapon.local_tts.detect_tts_engine")
    def test_macos(self, mock_detect):
        mock_detect.return_value = {
            "ok": True, "engine": "say", "platform": "Darwin",
            "voices": [{"name": "Samantha", "lang": "en_US"}]
        }
        voices = list_voices()
        self.assertEqual(len(voices), 1)
        self.assertEqual(voices[0]["name"], "Samantha")

    @patch("fr_cli.weapon.local_tts.detect_tts_engine")
    def test_linux(self, mock_detect):
        mock_detect.return_value = {"ok": True, "engine": "espeak", "platform": "Linux"}
        voices = list_voices()
        self.assertEqual(voices[0]["name"], "default")

    @patch("fr_cli.weapon.local_tts.detect_tts_engine")
    def test_no_engine(self, mock_detect):
        mock_detect.return_value = {"ok": False}
        voices = list_voices()
        self.assertEqual(voices, [])


class TestFormatVoices(unittest.TestCase):
    def test_empty(self):
        self.assertIn("没有", format_voices([]))

    def test_with_voices(self):
        voices = [{"name": "Samantha", "lang": "en_US"}, {"name": "Tingting", "lang": "zh_CN"}]
        out = format_voices(voices, lang="zh")
        self.assertIn("Samantha", out)
        self.assertIn("Tingting", out)


if __name__ == "__main__":
    unittest.main()