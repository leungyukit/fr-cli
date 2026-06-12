"""
插件执行回归测试
验证 exec_plugin 生成的子进程代码语法正确，能正确处理含空格、
引号、反斜杠的路径以及空参数、含特殊字符的参数。
"""

import pytest
import tempfile
from pathlib import Path


class TestPluginExecution:
    """测试插件子进程执行代码生成"""

    def test_exec_plugin_with_empty_args(self, capsys, monkeypatch, tmp_path):
        """空参数时不应抛出 JSON 解码错误"""
        from fr_cli.addon.plugin import exec_plugin

        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()
        plugin_file = plugin_dir / "test_empty.py"
        plugin_file.write_text(
            'def run(args=""):\n    return f"got={args!r}"\n',
            encoding="utf-8",
        )

        # 让 PLUGIN_DIR 指向临时目录
        import fr_cli.addon.plugin as plugin_mod
        monkeypatch.setattr(plugin_mod, "PLUGIN_DIR", plugin_dir)

        exec_plugin("test_empty", str(plugin_file), "", "zh")
        captured = capsys.readouterr()
        assert "got=" in captured.out
        assert "Error" not in captured.out
        assert "SyntaxError" not in captured.err

    def test_exec_plugin_path_with_special_chars(self, capsys, monkeypatch, tmp_path):
        """插件目录含空格、引号、反斜杠时仍能正确生成 sys.path.insert"""
        from fr_cli.addon.plugin import exec_plugin

        plugin_dir = tmp_path / 'plugins with "quotes" and \\backslash'
        plugin_dir.mkdir()
        plugin_file = plugin_dir / "test_special.py"
        plugin_file.write_text(
            'def run(args=""):\n    return f"args={args!r}"\n',
            encoding="utf-8",
        )

        import fr_cli.addon.plugin as plugin_mod
        monkeypatch.setattr(plugin_mod, "PLUGIN_DIR", plugin_dir)

        exec_plugin("test_special", str(plugin_file), 'hello "world"', "zh")
        captured = capsys.readouterr()
        assert 'args=' in captured.out
        assert 'hello "world"' in captured.out
        assert "SyntaxError" not in captured.err

    def test_exec_plugin_unicode_name(self, capsys, monkeypatch, tmp_path):
        """中文插件名应能被正确导入并执行"""
        from fr_cli.addon.plugin import exec_plugin

        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()
        plugin_file = plugin_dir / "姓名.py"
        plugin_file.write_text(
            'def run(args=""):\n    return "Plugin 姓名 executed"\n',
            encoding="utf-8",
        )

        import fr_cli.addon.plugin as plugin_mod
        monkeypatch.setattr(plugin_mod, "PLUGIN_DIR", plugin_dir)

        exec_plugin("姓名", str(plugin_file), "", "zh")
        captured = capsys.readouterr()
        assert "Plugin 姓名 executed" in captured.out
        assert "SyntaxError" not in captured.err
