"""输入区视觉: 蓝色小箭头 + 状态分隔线 测试

用户需求:
1. 输入提示位置显示蓝色小箭头(输入态指示符);
2. 输入内容上方一条自适应屏宽的蓝色横线, 隔开 AI 之前的回答;
3. 按 Enter 提交后, 横线变浅灰, 表示当前不在输入状态。
"""

from fr_cli.ui.prompt.tui import INPUT_INDICATOR, _PROMPT_STYLE


class TestInputIndicator:
    """蓝色小箭头(输入态指示符)"""

    def test_indicator_is_blue_chevron(self):
        """指示符是 ❯ + class:indicator(3 字符宽, 与旧 ▍ 对齐一致)"""
        assert INPUT_INDICATOR == ("class:indicator", " ❯ ")

    def test_indicator_style_is_blue(self):
        """indicator 样式为亮蓝加粗(不是旧的 cyan)"""
        assert _PROMPT_STYLE["indicator"] == "ansibrightblue bold"


class TestInputSeparator:
    """输入区分隔线: 蓝(输入态)/ 浅灰(提交后)"""

    def test_active_line_is_blue(self, monkeypatch, capsys):
        """输入态: 亮蓝(94m)全宽线, 带 input 标签"""
        from fr_cli.ui import banner
        monkeypatch.setattr(banner._ui, "color_enabled", lambda: True)
        banner.print_input_separator(width=40, active=True)
        out = capsys.readouterr().out
        assert "\033[94m" in out
        assert "── input " in out
        assert "─" * 31 in out  # 40 - len("── input ")=9 → 31 段横线

    def test_inactive_line_is_gray(self, monkeypatch, capsys):
        """提交后: 浅灰(90m)全宽线"""
        from fr_cli.ui import banner
        monkeypatch.setattr(banner._ui, "color_enabled", lambda: True)
        banner.print_input_separator(width=40, active=False)
        out = capsys.readouterr().out
        assert "\033[90m" in out
        assert "\033[94m" not in out

    def test_full_width_fills_terminal(self, monkeypatch, capsys):
        """自适应屏宽: 行显示宽度 == 传入宽度"""
        from fr_cli.ui import banner
        monkeypatch.setattr(banner._ui, "color_enabled", lambda: True)
        banner.print_input_separator(width=50, active=True)
        out = capsys.readouterr().out
        line = out.rstrip("\n")
        # 剥 ANSI 后按字符宽度计算(─ 是宽字符 1 列)
        import re
        plain = re.sub(r"\033\[[0-9;]*m", "", line)
        assert banner.get_display_width(plain) == 50

    def test_no_color_mode_uses_labels(self, monkeypatch, capsys):
        """无颜色环境(管道/NO_COLOR): 用标签区分状态, 不泄漏 ANSI"""
        from fr_cli.ui import banner
        monkeypatch.setattr(banner._ui, "color_enabled", lambda: False)
        banner.print_input_separator(width=30, active=True)
        banner.print_input_separator(width=30, active=False)
        out = capsys.readouterr().out
        assert "\033[" not in out
        assert "── input " in out   # 输入态
        assert "── done " in out    # 输入态已结束
