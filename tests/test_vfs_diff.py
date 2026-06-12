"""
VFS 文件写入差异展示测试
"""
import os
import tempfile
from pathlib import Path

import pytest


class TestVFSDiffDisplay:
    """测试 VFS.write 的 diff / 预览展示行为"""

    def _make_vfs(self, tmpdir):
        from fr_cli.weapon.fs import VFS
        return VFS([str(tmpdir)])

    def test_new_file_shows_preview(self, capsys, tmp_path):
        from fr_cli.weapon.fs import VFS
        vfs = VFS([str(tmp_path)])
        ok, msg = vfs.write("new.py", "line1\nline2\nline3", "zh")
        captured = capsys.readouterr()
        assert ok is True
        assert "new.py" in msg
        assert "新建" in captured.out or "New file" in captured.out
        assert "+line1" in captured.out
        assert "+line2" in captured.out

    def test_overwrite_shows_unified_diff(self, capsys, tmp_path):
        from fr_cli.weapon.fs import VFS
        vfs = VFS([str(tmp_path)])
        target = tmp_path / "test.py"
        target.write_text("old_a\nold_b\nold_c\n", encoding="utf-8")

        ok, msg = vfs.write("test.py", "old_a\nnew_b\nold_c\n", "zh")
        captured = capsys.readouterr()
        assert ok is True
        output = captured.out
        assert "覆盖" in output or "Overwrite" in output
        assert "-old_b" in output
        assert "+new_b" in output
        assert "old_a" in output

    def test_append_shows_preview(self, capsys, tmp_path):
        from fr_cli.weapon.fs import VFS
        vfs = VFS([str(tmp_path)])
        target = tmp_path / "test.py"
        target.write_text("existing\n", encoding="utf-8")

        ok, msg = vfs.write("test.py", "appended\n", "zh", mode='a')
        captured = capsys.readouterr()
        assert ok is True
        output = captured.out
        assert "追加" in output or "Append" in output
        assert "+appended" in output

    def test_binary_file_skips_diff(self, capsys, tmp_path):
        from fr_cli.weapon.fs import VFS
        vfs = VFS([str(tmp_path)])
        target = tmp_path / "binary.bin"
        target.write_bytes(b"\x00\x01\x02\x03")

        ok, msg = vfs.write("binary.bin", "new text", "zh")
        captured = capsys.readouterr()
        assert ok is True
        output = captured.out
        assert "二进制" in output or "binary" in output.lower()

    def test_long_content_truncated(self, capsys, tmp_path):
        from fr_cli.weapon.fs import VFS
        vfs = VFS([str(tmp_path)])
        long_content = "\n".join(f"line{i}" for i in range(100))

        ok, msg = vfs.write("long.py", long_content, "zh")
        captured = capsys.readouterr()
        assert ok is True
        output = captured.out
        # 预览应被截断
        assert "仅预览" in output or "truncated" in output.lower()
