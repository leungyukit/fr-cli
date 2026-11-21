"""韩立字符画测试

覆盖:
- 素材文件存在且可加载
- 终端高度保护(小终端不刷屏)
- NO_COLOR 降级到纯文本版
- /hanli 命令注册
- bootstrap show_art 参数贯通
"""
import io
import os
import unittest
from contextlib import redirect_stdout
from unittest import mock


class TestHanLiArt(unittest.TestCase):
    def setUp(self):
        from fr_cli.ui import hanli
        self.hanli = hanli

    def test_art_files_exist(self):
        """彩色与纯文本素材齐全"""
        from fr_cli.ui.hanli import _ASSETS_DIR
        for variant in ("bust", "full"):
            for ext in ("ansi", "txt"):
                path = _ASSETS_DIR / f"hanli_{variant}.{ext}"
                self.assertTrue(path.exists(), f"缺少素材: {path}")
                self.assertGreater(path.stat().st_size, 500)

    def test_art_dimensions(self):
        """行数与 ART_WIDTH 声明一致(纯文本版按 2:1 折算)"""
        from fr_cli.ui.hanli import ART_WIDTH, art_row_count, _load_art
        for variant, width in ART_WIDTH.items():
            plain_rows = art_row_count(variant)
            color_rows = len(_load_art(variant, color=True).rstrip("\n").split("\n"))
            # 半块字符垂直分辨率翻倍: 彩色行数 ≈ 2 × 纯文本行数
            self.assertAlmostEqual(color_rows, plain_rows * 2, delta=2,
                                   msg=f"{variant} 行列数不匹配")
            self.assertGreater(plain_rows, 20)

    def test_color_art_contains_halfblocks_and_truecolor(self):
        """彩色版使用半块字符 + 24 位真彩色"""
        from fr_cli.ui.hanli import _load_art
        art = _load_art("bust", color=True)
        self.assertIn("▀", art)
        self.assertIn("\033[38;2;", art)   # 真彩色前景
        self.assertIn("48;2;", art)   # 真彩色背景（fg/bg 合并在同一 SGR 序列中）

    def test_plain_art_has_no_ansi(self):
        """纯文本版无 ANSI 转义"""
        from fr_cli.ui.hanli import _load_art
        plain = _load_art("bust", color=False)
        self.assertNotIn("\033[", plain)

    def test_print_hanli_small_terminal_skips(self):
        """终端高度不足时跳过, 返回 False"""
        with mock.patch("shutil.get_terminal_size", return_value=os.terminal_size((80, 20))):
            buf = io.StringIO()
            with redirect_stdout(buf):
                ok = self.hanli.print_hanli("bust")
            self.assertFalse(ok)
            self.assertEqual(buf.getvalue(), "")

    def test_print_hanli_big_terminal_prints(self):
        """终端足够高时打印, 返回 True"""
        with mock.patch("shutil.get_terminal_size", return_value=os.terminal_size((120, 120))):
            buf = io.StringIO()
            with redirect_stdout(buf):
                ok = self.hanli.print_hanli("bust")
            self.assertTrue(ok)
            self.assertGreater(len(buf.getvalue()), 1000)

    def test_print_hanli_color_height_guard_uses_color_rows(self):
        """高度保护必须按彩色版行数算(彩色版 ≈ 2 × 纯文本版)

        回归: 曾按纯文本行数(40)判断, 彩色终端实际打印 80 行会溢出。
        终端高 85、min_free_rows=10: 纯文本口径 40+10=50 会放行(错),
        彩色口径 80+10=90 必须拦截。
        """
        with mock.patch("fr_cli.ui.hanli._no_color", return_value=False), \
             mock.patch("shutil.get_terminal_size", return_value=os.terminal_size((120, 85))):
            buf = io.StringIO()
            with redirect_stdout(buf):
                ok = self.hanli.print_hanli("bust", min_free_rows=10)
            self.assertFalse(ok, "85 行终端打印 80 行字符画会溢出, 应跳过")
            self.assertEqual(buf.getvalue(), "")

    def test_print_hanli_color_prints_when_tall_enough(self):
        """彩色版在高度真正够时打印, 且实际行数与彩色版一致"""
        with mock.patch("fr_cli.ui.hanli._no_color", return_value=False), \
             mock.patch("shutil.get_terminal_size", return_value=os.terminal_size((120, 100))):
            buf = io.StringIO()
            with redirect_stdout(buf):
                ok = self.hanli.print_hanli("bust", min_free_rows=10)
            self.assertTrue(ok)
            rows = len(buf.getvalue().rstrip("\n").split("\n")) - 1  # 去掉开头空行
            self.assertEqual(rows, self.hanli.art_row_count("bust", color=True))

    def test_print_hanli_no_color_uses_plain(self):
        """NO_COLOR 环境下输出无 ANSI 转义"""
        with mock.patch.dict(os.environ, {"NO_COLOR": "1"}), \
             mock.patch("shutil.get_terminal_size", return_value=os.terminal_size((120, 120))):
            buf = io.StringIO()
            with redirect_stdout(buf):
                ok = self.hanli.print_hanli("bust")
            self.assertTrue(ok)
            self.assertNotIn("\033[38;2;", buf.getvalue())

    def test_print_hanli_centered(self):
        """宽终端下居中(行首有填充空格)"""
        with mock.patch("shutil.get_terminal_size", return_value=os.terminal_size((160, 120))):
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.hanli.print_hanli("bust")
            first_content = next(l for l in buf.getvalue().split("\n") if l.strip())
            self.assertTrue(first_content.startswith(" "), "宽终端应居中对齐")

    def test_unknown_variant_falls_back(self):
        """未知 variant 回退到 bust"""
        with mock.patch("shutil.get_terminal_size", return_value=os.terminal_size((120, 120))):
            buf = io.StringIO()
            with redirect_stdout(buf):
                ok = self.hanli.print_hanli("nonexistent")
            self.assertTrue(ok)


class TestHanLiCommand(unittest.TestCase):
    def test_command_registered(self):
        from fr_cli.repl.router import COMMAND_ROUTES
        self.assertIn("/hanli", COMMAND_ROUTES)

    def test_cmd_hanli_runs(self):
        from fr_cli.repl.commands.base import _cmd_hanli
        with mock.patch("fr_cli.ui.hanli._no_color", return_value=False), \
             mock.patch("shutil.get_terminal_size", return_value=os.terminal_size((120, 120))):
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = _cmd_hanli(mock.MagicMock(), ["/hanli"])
        self.assertFalse(result)  # 命令不退出 REPL
        self.assertIn("▀", buf.getvalue())

    def test_cmd_hanli_full(self):
        from fr_cli.repl.commands.base import _cmd_hanli
        with mock.patch("fr_cli.ui.hanli._no_color", return_value=False), \
             mock.patch("shutil.get_terminal_size", return_value=os.terminal_size((160, 160))):
            buf = io.StringIO()
            with redirect_stdout(buf):
                _cmd_hanli(mock.MagicMock(), ["/hanli", "full"])
        out = buf.getvalue()
        self.assertIn("▀", out)

    def test_cmd_hanli_plain_in_non_tty(self):
        """非 TTY(测试环境)自动降级纯文本, 无 ANSI 转义"""
        from fr_cli.repl.commands.base import _cmd_hanli
        with mock.patch("shutil.get_terminal_size", return_value=os.terminal_size((120, 120))):
            buf = io.StringIO()
            with redirect_stdout(buf):
                _cmd_hanli(mock.MagicMock(), ["/hanli"])
        self.assertNotIn("\033[38;2;", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
