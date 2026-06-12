"""
颜色输出控制回归测试
验证 prompt_toolkit REPL 环境下会提前禁用 ANSI 颜色，
避免用户看到 ?[92m 这类转义字符。
"""

import sys
import os
import importlib

import pytest


class TestNoColorControl:
    """测试 ANSI 颜色全局开关"""

    def test_set_no_color_disables_constants(self):
        """set_no_color(True) 应将所有颜色常量置空"""
        from fr_cli.ui import ui

        original = ui._NO_COLOR
        try:
            ui.set_no_color(True)
            assert ui._NO_COLOR is True
            assert ui.RED == ""
            assert ui.GREEN == ""
            assert ui.CYAN == ""
            assert ui.DIM == ""
            assert ui.RESET == ""
            assert ui.CODE_BG == ""
            assert ui.CODE_FG == ""
        finally:
            ui.set_no_color(original)

    def test_set_no_color_restores_constants(self):
        """set_no_color(False) 应恢复原始 ANSI 码"""
        from fr_cli.ui import ui

        ui.set_no_color(True)
        try:
            ui.set_no_color(False)
            assert ui.RED == "\033[91m"
            assert ui.GREEN == "\033[92m"
            assert ui.RESET == "\033[0m"
        finally:
            ui.reset_color()

    def test_main_color_early_disable_in_repl(self, monkeypatch):
        """REPL + prompt_toolkit 环境下应提前设置 NO_COLOR"""
        from fr_cli.ui import ui
        original_no_color = ui._NO_COLOR
        try:
            import fr_cli.main as main

            # 模拟 REPL 环境：有 TTY 且 prompt_toolkit 可导入
            monkeypatch.setattr("sys.stdin.isatty", lambda: True)
            monkeypatch.setattr("sys.stdout.isatty", lambda: True)
            monkeypatch.setattr("sys.argv", ["fr-cli"])
            monkeypatch.delenv("NO_COLOR", raising=False)
            monkeypatch.delenv("FORCE_COLOR", raising=False)
            monkeypatch.delenv("CLICOLOR_FORCE", raising=False)

            # prompt_toolkit 一般已安装，若未安装则跳过
            try:
                import prompt_toolkit  # noqa: F401
            except ImportError:
                pytest.skip("prompt_toolkit not installed")

            assert main._should_disable_colors_early() is True
        finally:
            ui.set_no_color(original_no_color)

    def test_main_color_keep_in_batch(self, monkeypatch):
        """批处理模式不应提前禁用颜色"""
        from fr_cli.ui import ui
        original_no_color = ui._NO_COLOR
        try:
            import fr_cli.main as main

            monkeypatch.setattr("sys.stdin.isatty", lambda: True)
            monkeypatch.setattr("sys.stdout.isatty", lambda: True)
            monkeypatch.setattr("sys.argv", ["fr-cli", "-c", "/model current"])
            monkeypatch.delenv("NO_COLOR", raising=False)
            monkeypatch.delenv("FORCE_COLOR", raising=False)
            monkeypatch.delenv("CLICOLOR_FORCE", raising=False)

            assert main._should_disable_colors_early() is False
        finally:
            ui.set_no_color(original_no_color)

    def test_force_color_override(self, monkeypatch):
        """FORCE_COLOR 环境变量应覆盖自动禁用"""
        from fr_cli.ui import ui
        original_no_color = ui._NO_COLOR
        try:
            import fr_cli.main as main

            monkeypatch.setattr("sys.stdin.isatty", lambda: True)
            monkeypatch.setattr("sys.stdout.isatty", lambda: True)
            monkeypatch.setattr("sys.argv", ["fr-cli"])
            monkeypatch.setenv("FORCE_COLOR", "1")
            monkeypatch.delenv("NO_COLOR", raising=False)
            monkeypatch.delenv("CLICOLOR_FORCE", raising=False)

            assert main._should_disable_colors_early() is False
        finally:
            ui.set_no_color(original_no_color)

    def test_no_color_env_respected(self, monkeypatch):
        """NO_COLOR 环境变量应被尊重"""
        from fr_cli.ui import ui
        original_no_color = ui._NO_COLOR
        try:
            import fr_cli.main as main

            monkeypatch.setattr("sys.stdin.isatty", lambda: True)
            monkeypatch.setattr("sys.stdout.isatty", lambda: True)
            monkeypatch.setattr("sys.argv", ["fr-cli"])
            monkeypatch.setenv("NO_COLOR", "1")
            monkeypatch.delenv("FORCE_COLOR", raising=False)
            monkeypatch.delenv("CLICOLOR_FORCE", raising=False)

            assert main._should_disable_colors_early() is True
        finally:
            ui.set_no_color(original_no_color)

    def test_image_display_fallback_to_ascii_when_no_color(self, monkeypatch):
        """NO_COLOR 时图片显示应回退到 ascii，避免 iTerm2/Kitty 转义序列泄漏"""
        from fr_cli.ui import ui
        from fr_cli.agent.image_and_parallel import TerminalImageDisplay

        original_no_color = ui._NO_COLOR
        try:
            ui.set_no_color(True)
            # 即使终端标识为 iTerm2/Kitty，也应返回 ascii
            monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
            monkeypatch.setenv("KITTY_WINDOW_ID", "1")
            monkeypatch.setenv("TERM", "xterm-256color")
            assert TerminalImageDisplay._detect_method() == "ascii"
        finally:
            ui.set_no_color(original_no_color)
