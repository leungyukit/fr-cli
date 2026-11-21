"""
颜色输出控制回归测试
验证 NO_COLOR / 非 TTY 环境下禁用 ANSI 颜色,
交互式 TTY 保留颜色(prompt_toolkit 3.0.52 的 patch_stdout 已正确解析 ANSI)。
"""


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

    def test_main_color_kept_in_tty_repl(self, monkeypatch):
        """交互式 TTY REPL 应保留颜色

        prompt_toolkit 3.0.52 的 patch_stdout 已验证可正确解析 ANSI
        (非交互实测直通不损坏), 不再需要全局禁色;
        流式路径内部仍有 _ColorDisable 局部兜底。
        """
        from fr_cli.ui import ui
        original_no_color = ui._NO_COLOR
        try:
            import fr_cli.main as main

            monkeypatch.setattr("sys.stdin.isatty", lambda: True)
            monkeypatch.setattr("sys.stdout.isatty", lambda: True)
            monkeypatch.setattr("sys.argv", ["fr-cli"])
            monkeypatch.delenv("NO_COLOR", raising=False)
            monkeypatch.delenv("FORCE_COLOR", raising=False)
            monkeypatch.delenv("CLICOLOR_FORCE", raising=False)

            assert main._should_disable_colors_early() is False
        finally:
            ui.set_no_color(original_no_color)

    def test_main_color_disable_when_not_tty(self, monkeypatch):
        """非 TTY(管道/重定向)应提前禁用颜色"""
        import fr_cli.main as main

        monkeypatch.setattr("sys.stdin.isatty", lambda: False)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        monkeypatch.setattr("sys.argv", ["fr-cli"])
        monkeypatch.delenv("NO_COLOR", raising=False)

        assert main._should_disable_colors_early() is True

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

