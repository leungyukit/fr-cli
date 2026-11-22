"""颜色判定单一源 + markdown_stream 跟随禁色 回归测试

固化的两个历史漏洞(均已修):
1. ui.py 的 _NO_COLOR 只认 NO_COLOR, 不认 FR_CLI_NO_COLOR, 与 output.py
   两套判定漂移 → FR_CLI_NO_COLOR=1 在 TTY 下关不掉 markdown 流式颜色。
2. markdown_stream 在 import 时把 ui 禁色态下的空常量"回填"成硬编码
   ANSI 码, 主动推翻全局禁色 → 非 TTY 场景泄漏 ?[96m 乱码。
"""
import io
import sys

import pytest

from fr_cli.ui import ui


def _set_tty(monkeypatch, value: bool):
    """伪造 stdin/stdout 的 isatty 返回值"""
    for stream in (sys.stdin, sys.stdout):
        monkeypatch.setattr(stream, "isatty", lambda v=value: v, raising=False)


@pytest.fixture(autouse=True)
def _restore_color_state():
    original = ui._NO_COLOR
    yield
    ui.set_no_color(original)


class TestColorEnabledSingleSource:
    """ui.color_enabled() 单一判定源"""

    def test_non_tty_disables(self, monkeypatch):
        _set_tty(monkeypatch, False)
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("FR_CLI_NO_COLOR", raising=False)
        monkeypatch.delenv("FORCE_COLOR", raising=False)
        monkeypatch.delenv("CLICOLOR_FORCE", raising=False)
        assert ui.color_enabled() is False

    def test_double_tty_enables(self, monkeypatch):
        _set_tty(monkeypatch, True)
        for var in ("NO_COLOR", "FR_CLI_NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE"):
            monkeypatch.delenv(var, raising=False)
        assert ui.color_enabled() is True

    def test_stdin_non_tty_disables_even_if_stdout_tty(self, monkeypatch):
        """双 TTY 才开色 —— 与 main.py 的提前判定策略一致"""
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
        for var in ("NO_COLOR", "FR_CLI_NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE"):
            monkeypatch.delenv(var, raising=False)
        assert ui.color_enabled() is False

    def test_fr_cli_no_color_env_respected_in_tty(self, monkeypatch):
        """修复点 1: FR_CLI_NO_COLOR 必须在 TTY 下也关掉 markdown 路径的颜色"""
        _set_tty(monkeypatch, True)
        monkeypatch.setenv("FR_CLI_NO_COLOR", "1")
        monkeypatch.delenv("NO_COLOR", raising=False)
        assert ui.color_enabled() is False

    def test_no_color_env_respected_in_tty(self, monkeypatch):
        _set_tty(monkeypatch, True)
        monkeypatch.setenv("NO_COLOR", "1")
        assert ui.color_enabled() is False

    def test_force_color_overrides_non_tty(self, monkeypatch):
        _set_tty(monkeypatch, False)
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("FR_CLI_NO_COLOR", raising=False)
        monkeypatch.setenv("FORCE_COLOR", "1")
        assert ui.color_enabled() is True

    def test_clicolor_force_overrides_non_tty(self, monkeypatch):
        _set_tty(monkeypatch, False)
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("FR_CLI_NO_COLOR", raising=False)
        monkeypatch.setenv("CLICOLOR_FORCE", "1")
        assert ui.color_enabled() is True

    def test_force_color_beats_no_color(self, monkeypatch):
        """优先级: 强制开 > 强制关"""
        _set_tty(monkeypatch, False)
        monkeypatch.setenv("FORCE_COLOR", "1")
        monkeypatch.setenv("NO_COLOR", "1")
        assert ui.color_enabled() is True


class TestMarkdownStreamFollowsGlobalState:
    """修复点 2: markdown_stream 颜色常量实时跟随 ui, 禁色态拼不出任何序列"""

    def test_disabled_state_emits_no_escape(self):
        from fr_cli.ui.markdown_stream import StreamingMarkdownRenderer
        ui.set_no_color(True)
        # 即使调用方显式传 use_color=True, 禁色态下常量是空串, 拼不出序列
        r = StreamingMarkdownRenderer(use_color=True)
        out = r.feed("- 项目符号\n")
        assert "\033[" not in out
        assert "•" in out

    def test_enabled_state_emits_escape(self):
        from fr_cli.ui.markdown_stream import StreamingMarkdownRenderer
        ui.set_no_color(False)
        r = StreamingMarkdownRenderer(use_color=True)
        out = r.feed("- 项目符号\n")
        assert "\033[96m" in out  # 亮青
        assert "\033[1m" in out   # 加粗
        assert "\033[0m" in out   # 复位
        assert "•" in out

    def test_toggle_mid_stream(self):
        """运行中切换全局开关, 渲染器实时跟随(旧版 import 快照做不到)"""
        from fr_cli.ui.markdown_stream import StreamingMarkdownRenderer
        ui.set_no_color(False)
        r = StreamingMarkdownRenderer(use_color=True)
        assert "\033[" in r.feed("- a\n")
        ui.set_no_color(True)
        assert "\033[" not in r.feed("- b\n")

    def test_constants_are_dynamic_proxy(self):
        """模块级 __getattr__ 代理: 访问即取 ui 当前值, 不是 import 时快照"""
        from fr_cli.ui import markdown_stream
        ui.set_no_color(True)
        assert markdown_stream.CYAN == ""
        assert markdown_stream.RESET == ""
        ui.set_no_color(False)
        assert markdown_stream.CYAN == "\033[96m"

    def test_unknown_attribute_still_raises(self):
        from fr_cli.ui import markdown_stream
        with pytest.raises(AttributeError):
            _ = markdown_stream.NOT_A_COLOR


class TestStreamRendererColorDecision:
    """stream.py 的组合判定(可测函数)"""

    def test_off_when_non_tty(self, monkeypatch):
        from fr_cli.core.stream import _markdown_use_color
        _set_tty(monkeypatch, False)
        for var in ("NO_COLOR", "FR_CLI_NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE"):
            monkeypatch.delenv(var, raising=False)
        ui.set_no_color(False)  # 全局没被显式关, 但环境非 TTY
        assert _markdown_use_color() is False

    def test_off_when_explicitly_disabled(self, monkeypatch):
        from fr_cli.core.stream import _markdown_use_color
        _set_tty(monkeypatch, True)
        for var in ("NO_COLOR", "FR_CLI_NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE"):
            monkeypatch.delenv(var, raising=False)
        ui.set_no_color(True)
        assert _markdown_use_color() is False

    def test_on_when_tty_and_enabled(self, monkeypatch):
        from fr_cli.core.stream import _markdown_use_color
        _set_tty(monkeypatch, True)
        for var in ("NO_COLOR", "FR_CLI_NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE"):
            monkeypatch.delenv(var, raising=False)
        ui.set_no_color(False)
        assert _markdown_use_color() is True

    def test_off_when_fr_cli_no_color_in_tty(self, monkeypatch):
        """修复点 1 的端到端: FR_CLI_NO_COLOR=1 + TTY → 流式路径也关色"""
        from fr_cli.core.stream import _markdown_use_color
        _set_tty(monkeypatch, True)
        monkeypatch.setenv("FR_CLI_NO_COLOR", "1")
        monkeypatch.delenv("NO_COLOR", raising=False)
        ui.set_no_color(False)
        assert _markdown_use_color() is False


class TestOutputColorEnabledDelegation:
    """output.py 的判定委托给 ui, 两套逻辑不再漂移"""

    def test_matches_ui_decision(self, monkeypatch):
        from fr_cli.ui import output
        _set_tty(monkeypatch, True)
        monkeypatch.setenv("FR_CLI_NO_COLOR", "1")
        monkeypatch.delenv("NO_COLOR", raising=False)
        assert output._color_enabled() is False
        assert output._color_enabled() == ui.color_enabled()
