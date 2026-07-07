"""
/help 与模型命令帮助文本更新测试
"""
import pytest


class TestHelpAndModelDocs:
    """验证 /help 与 /model 帮助文本包含最新子命令"""

    @pytest.fixture
    def state(self, tmp_path, monkeypatch):
        from fr_cli.core.core import AppState
        from fr_cli.conf import paths
        # 把配置目录指向临时目录，避免污染真实配置
        monkeypatch.setattr(paths._root_holder, "value", tmp_path)
        cfg = {
            "provider": "zhipu",
            "key": "top-key",
            "model": "glm-4-flash",
            "providers": {"zhipu": {"key": "top-key", "model": "glm-4-flash"}},
            "lang": "zh",
            "limit": 4096,
            "allowed_dirs": [],
            "aliases": {},
            "auto_confirm_forever": True,
        }
        return AppState(cfg)

    def test_print_help_includes_model_config(self, state, capsys):
        """默认 /help 应列出 /model config"""
        from fr_cli.repl.commands._common import _print_help

        _print_help(state, "")
        captured = capsys.readouterr()
        assert "/model config" in captured.out
        assert "交互式配置向导" in captured.out

    def test_help_model_topic_exists(self, state, capsys):
        """/help model 应能输出模型相关详细帮助"""
        from fr_cli.repl.commands._common import _print_help

        _print_help(state, "model")
        captured = capsys.readouterr()
        assert "/model config" in captured.out
        assert "/providers" in captured.out

    def test_cmd_model_help_lists_config(self, state, capsys, monkeypatch):
        """/model 无参数时的提示文本应包含 /model config"""
        from fr_cli.repl.commands.config import _cmd_model

        # 避免进入交互式 input
        monkeypatch.setattr("builtins.input", lambda _: "")
        _cmd_model(state, ["/model"])
        captured = capsys.readouterr()
        assert "/model config" in captured.out
        assert "交互式模型配置向导" in captured.out

    def test_cmd_model_docstring_mentions_config(self):
        """_cmd_model 文档字符串应记录 /model config"""
        from fr_cli.repl.commands.config import _cmd_model

        assert "/model config" in _cmd_model.__doc__
