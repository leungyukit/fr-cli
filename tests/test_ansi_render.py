"""ANSI 序列还原 / 剥离 / 渲染 测试

核心场景: `?[96m?[1m•?[0m`(ESC 被查看器吃掉只剩 `?`)如何
① 还原成真序列让终端解释出亮青+加粗+项目符号
② 或在非 TTY 场景剥成干净纯文本
"""
import io
import sys

import pytest

from fr_cli.ui import ansi


class TestHasAnsi:
    def test_detects_damaged(self):
        assert ansi.has_ansi("?[96m?[1m•?[0m") is True

    def test_detects_real(self):
        assert ansi.has_ansi("\033[96mhi\033[0m") is True

    def test_plain_text_no(self):
        assert ansi.has_ansi("普通文本, 没有序列") is False

    def test_plain_question_mark_no(self):
        """真问号不被误判为序列"""
        assert ansi.has_ansi("选 A?[1] 还是 B") is False
        assert ansi.has_ansi("what? [see docs]") is False

    def test_unknown_sgr_code_no(self):
        """未知 SGR 码的 ?[..m 不当作序列"""
        assert ansi.has_ansi("值?[999m 结束") is False


class TestNormalizeAnsi:
    def test_restores_damaged_bullet(self):
        """用户报的样本: 亮青 + 加粗 + 项目符号 + 复位"""
        out = ansi.normalize_ansi("?[96m?[1m•?[0m")
        assert out == "\033[96m\033[1m•\033[0m"

    def test_real_sequence_untouched(self):
        text = "\033[96mhi\033[0m"
        assert ansi.normalize_ansi(text) == text

    def test_mixed(self):
        out = ansi.normalize_ansi("前 \033[2m暗?[1m粗 后")
        assert out == "前 \033[2m暗\033[1m粗 后"

    def test_256_color_and_truecolor(self):
        assert ansi.normalize_ansi("?[38;5;196m") == "\033[38;5;196m"
        assert ansi.normalize_ansi("?[48;2;255;0;0m") == "\033[48;2;255;0;0m"

    def test_unknown_code_kept_literal(self):
        assert ansi.normalize_ansi("值?[999m") == "值?[999m"
        assert ansi.normalize_ansi("选 A?[1]") == "选 A?[1]"

    def test_non_m_terminator_not_touched(self):
        """?[2J(清屏)等非 m 结尾不吃 —— 只处理 SGR, 避免误伤"""
        assert ansi.normalize_ansi("?[2J") == "?[2J"


class TestStripAnsi:
    def test_strips_both_forms(self):
        out = ansi.strip_ansi("?[96m?[1m•?[0m 真\033[32m绿\033[0m")
        assert out == "• 真绿"
        assert "\033[" not in out
        assert "?[" not in out

    def test_bullet_char_preserved(self):
        assert ansi.strip_ansi("?[1m•?[0m") == "•"

    def test_plain_text_untouched(self):
        text = "选 A?[1] 保留问号"
        assert ansi.strip_ansi(text) == text


class TestRenderAnsi:
    def test_writes_normalized_to_target(self):
        buf = io.StringIO()
        ansi.render_ansi("?[96m•?[0m", file=buf)
        assert buf.getvalue() == "\033[96m•\033[0m"

    def test_default_target_is_stdout(self, capsys):
        ansi.render_ansi("?[1mhi?[0m")
        assert capsys.readouterr().out == "\033[1mhi\033[0m"


class TestCliMain:
    def test_strips_when_not_tty(self, monkeypatch, capsys):
        monkeypatch.setattr(sys.stdout, "isatty", lambda: False, raising=False)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
        monkeypatch.setattr(sys, "stdin", io.StringIO("?[96m?[1m•?[0m 列表项\n"))
        assert ansi.main([]) == 0
        out = capsys.readouterr().out
        assert out == "• 列表项\n"

    def test_renders_when_tty(self, monkeypatch, capsys):
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
        monkeypatch.setattr(sys, "stdin", io.StringIO("?[96m?[1m•?[0m"))
        assert ansi.main([]) == 0
        assert capsys.readouterr().out == "\033[96m\033[1m•\033[0m"

    def test_reads_files(self, monkeypatch, capsys, tmp_path):
        p = tmp_path / "screen.txt"
        p.write_text("?[2m暗?[0m 正常\n", encoding="utf-8")
        monkeypatch.setattr(sys.stdout, "isatty", lambda: False, raising=False)
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
        assert ansi.main([str(p)]) == 0
        assert capsys.readouterr().out == "暗 正常\n"
