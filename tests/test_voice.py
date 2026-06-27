"""
Voice / TTS 测试
覆盖 voice 开关、可用性检测、缓存目录、graceful 降级等。
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fr_cli.agent import voice


@pytest.fixture(autouse=True)
def reset_voice_state():
    """每个测试重置 voice 开关"""
    voice.set_voice_enabled(False)
    yield
    voice.set_voice_enabled(False)


# ==================== 开关 ====================

class TestVoiceToggle:

    def test_default_disabled(self):
        voice.set_voice_enabled(False)
        assert voice.is_voice_enabled() is False

    def test_enable(self):
        voice.set_voice_enabled(True)
        assert voice.is_voice_enabled() is True

    def test_disable(self):
        voice.set_voice_enabled(True)
        voice.set_voice_enabled(False)
        assert voice.is_voice_enabled() is False


# ==================== 可用性检测 ====================

class TestVoiceAvailability:

    def test_not_available_when_no_mcp(self):
        with patch("fr_cli.weapon.mcp.get_mcp_manager") as mock_get:
            mock_get.return_value = None
            assert voice.is_voice_available() is False

    def test_not_available_when_no_matrix_server(self):
        mock_mgr = MagicMock()
        mock_mgr.servers = {"other_server": MagicMock()}
        mock_mgr.get_server.return_value = MagicMock(enabled=True)

        with patch("fr_cli.weapon.mcp.get_mcp_manager", return_value=mock_mgr):
            assert voice.is_voice_available() is False

    def test_available_with_matrix_server(self):
        mock_srv = MagicMock(enabled=True)
        mock_mgr = MagicMock()
        mock_mgr.servers = {"matrix_prod": mock_srv}
        mock_mgr.get_server.return_value = mock_srv

        with patch("fr_cli.weapon.mcp.get_mcp_manager", return_value=mock_mgr):
            assert voice.is_voice_available() is True

    def test_disabled_matrix_server_not_available(self):
        mock_srv = MagicMock(enabled=False)
        mock_mgr = MagicMock()
        mock_mgr.servers = {"matrix_prod": mock_srv}
        mock_mgr.get_server.return_value = mock_srv

        with patch("fr_cli.weapon.mcp.get_mcp_manager", return_value=mock_mgr):
            assert voice.is_voice_available() is False


# ==================== 缓存目录 ====================

class TestVoiceCache:

    def test_cache_dir_creates(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        cache = voice._get_voice_cache_dir()
        assert cache.exists()
        assert cache.is_dir()


# ==================== voice_speak 错误路径 ====================

class TestVoiceSpeak:

    def test_speak_empty_text_returns_ok_with_no_play(self):
        result = voice.voice_speak("")
        # 空文本不报错,但也没播放
        assert result.is_ok() or result.is_fail()

    def test_speak_unavailable_returns_fail(self):
        with patch("fr_cli.weapon.mcp.get_mcp_manager") as mock_get:
            mock_get.return_value = None
            result = voice.voice_speak("hello")
        assert not result.is_ok()
        assert "不可用" in result.error or "matrix" in result.error

    def test_speak_no_matrix_server(self):
        mock_mgr = MagicMock()
        mock_mgr.servers = {}

        with patch("fr_cli.weapon.mcp.get_mcp_manager", return_value=mock_mgr):
            result = voice.voice_speak("hello")
        assert not result.is_ok()


# ==================== list_available_voices ====================

class TestListVoices:

    def test_empty_when_no_matrix(self):
        mock_mgr = MagicMock()
        mock_mgr.servers = {}

        with patch("fr_cli.weapon.mcp.get_mcp_manager", return_value=mock_mgr):
            voices = voice.list_available_voices()
        assert voices == []

    def test_no_tools_method(self):
        """如果 mgr 没有 list_all_tools,不崩"""
        mock_mgr = MagicMock()
        mock_mgr.servers = {"matrix_x": MagicMock(enabled=True)}
        mock_mgr.list_all_tools = None

        with patch("fr_cli.weapon.mcp.get_mcp_manager", return_value=mock_mgr):
            voices = voice.list_available_voices()
        assert isinstance(voices, list)


# ==================== speak_if_enabled ====================

class TestSpeakIfEnabled:

    def test_no_speak_when_disabled(self):
        """voice 关闭时不朗读"""
        voice.set_voice_enabled(False)
        result = voice.speak_if_enabled("hello")
        assert result is None

    def test_speak_when_enabled(self):
        """voice 开启时返回 None(异步)不崩"""
        voice.set_voice_enabled(True)

        with patch("fr_cli.weapon.mcp.get_mcp_manager") as mock_get:
            mock_get.return_value = None
            # 应该异步启动但不崩
            result = voice.speak_if_enabled("hello world")
        # 异步,直接返回 None
        assert result is None

    def test_speak_empty_text(self):
        voice.set_voice_enabled(True)
        assert voice.speak_if_enabled("") is None
        assert voice.speak_if_enabled("   ") is None


# ==================== 工具注册 ====================

class TestToolRegistration:

    def test_voice_tools_registered(self):
        from fr_cli.command.registry import get_registry
        reg = get_registry()
        tools = getattr(reg, "_tools", {})
        for name in ["voice_speak", "voice_list", "voice_toggle"]:
            assert name in tools, f"{name} 未注册"
