"""
4 阶安全确认测试
覆盖 fconfirm / sconfirm / 批量模式 / 非交互模式 / 永久放行撤销。

注:ask() 通过 input() 与用户交互,这里用 monkeypatch 模拟输入。
"""
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fr_cli.security.security import ask, clear_all_auto_confirm


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """确保测试环境干净"""
    monkeypatch.delenv("FR_CLI_BATCH_CONFIRM", raising=False)
    monkeypatch.delenv("FR_CLI_NON_INTERACTIVE", raising=False)


class TestBatchMode:

    def test_batch_confirm_always_allow(self):
        """FR_CLI_BATCH_CONFIRM=1:直接放行"""
        os.environ["FR_CLI_BATCH_CONFIRM"] = "1"
        ok, s, f = ask("sec_read", "/etc/test", "zh", {}, {}, {})
        assert ok is True

    def test_batch_confirm_works_for_exec(self):
        os.environ["FR_CLI_BATCH_CONFIRM"] = "1"
        ok, s, f = ask("sec_exec", "rm -rf /", "zh", {}, {}, {})
        assert ok is True


class TestNonInteractiveMode:

    def test_non_interactive_denies_by_default(self):
        """FR_CLI_NON_INTERACTIVE=1:默认拒绝"""
        os.environ["FR_CLI_NON_INTERACTIVE"] = "1"
        ok, s, f = ask("sec_read", "/etc/passwd", "zh", {}, {}, {})
        assert ok is False

    def test_non_interactive_denies_exec(self):
        os.environ["FR_CLI_NON_INTERACTIVE"] = "1"
        ok, s, f = ask("sec_exec", "dangerous command", "zh", {}, {}, {})
        assert ok is False


class TestForeverConfirm:

    def test_forever_confirm_dict_format(self):
        """fconfirm 字典按 sec_* 类别独立放行"""
        fconfirm = {"sec_read": True, "sec_write": False}
        # sec_read 直接放行
        ok, s, f = ask("sec_read", "/anywhere", "zh", fconfirm, {}, {})
        assert ok is True
        # sec_write 不会被连带放行
        assert f.get("sec_write") is False

    def test_forever_confirm_categorized(self):
        """永久放行只对指定 sec_* 类别生效"""
        fconfirm = {"sec_write": True}
        # sec_exec 不被永久放行,会询问
        with patch("builtins.input", return_value="n"):
            ok, _, _ = ask("sec_exec", "command", "zh", fconfirm, {}, {})
        # 用户输入 n → 拒绝
        assert ok is False

    def test_forever_confirm_persists_to_config(self, tmp_path, monkeypatch):
        """'f' 输入应持久化到 config['auto_confirm']"""
        # 用临时 config 文件
        config_file = tmp_path / "config.json"
        config_file.write_text("{}", encoding="utf-8")
        from fr_cli.conf import paths
        # 通过 monkeypatch paths 模块的 _root_holder 让所有路径都指向 tmp
        monkeypatch.setattr(paths._root_holder, "value", tmp_path)

        with patch("builtins.input", return_value="f"):
            ok, s, f = ask("sec_read", "/tmp/x", "zh", {}, {}, {"auto_confirm": {}})
        assert ok is True
        assert f.get("sec_read") is True
        # config 文件应被写入
        import json
        cfg = json.loads(config_file.read_text(encoding="utf-8"))
        assert cfg.get("auto_confirm", {}).get("sec_read") is True


class TestSessionConfirm:

    def test_session_confirm_dict_format(self):
        """sconfirm 字典按 sec_* 类别放行(本次会话)"""
        sconfirm = {"sec_exec": True}
        ok, s, f = ask("sec_exec", "ls", "zh", {}, sconfirm, {})
        assert ok is True

    def test_session_confirm_only_current_category(self):
        """session 放行只对当前 sec_* 类别"""
        sconfirm = {"sec_read": True}
        # sec_exec 没被 session 放行,需要询问
        with patch("builtins.input", return_value="n"):
            ok, _, _ = ask("sec_exec", "ls", "zh", {}, sconfirm, {})
        assert ok is False

    def test_session_confirm_true_means_all(self):
        """sconfirm=True 表示所有类别放行(旧版兼容)"""
        with patch("builtins.input", side_effect=AssertionError("should not prompt")):
            ok, s, f = ask("sec_exec", "ls", "zh", {}, True, {})
        assert ok is True


class TestUserInput:

    def test_user_yields_yes(self):
        with patch("builtins.input", return_value="y"):
            ok, _, _ = ask("sec_read", "/tmp/x", "zh", {}, {}, {})
        assert ok is True

    def test_user_yields_no(self):
        with patch("builtins.input", return_value="n"):
            ok, _, _ = ask("sec_read", "/tmp/x", "zh", {}, {}, {})
        assert ok is False

    def test_user_a_marks_session(self):
        """输入 'a' 应仅对当前 sec_* 类别标记 session 放行"""
        with patch("builtins.input", return_value="a"):
            ok, s, f = ask("sec_read", "/tmp/x", "zh", {}, {}, {})
        assert ok is True
        assert s.get("sec_read") is True
        # 其他 sec_* 不被影响
        assert s.get("sec_write") is None or s.get("sec_write") is False

    def test_empty_input_treated_as_no(self):
        with patch("builtins.input", return_value=""):
            ok, _, _ = ask("sec_read", "/tmp/x", "zh", {}, {}, {})
        assert ok is False


class TestClearAutoConfirm:

    def test_clear_removes_dict(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.json"
        config_file.write_text('{"auto_confirm": {"sec_read": true}}', encoding="utf-8")
        import fr_cli.conf.config as cfg_mod
        monkeypatch.setattr(cfg_mod, "CONFIG_FILE", config_file)

        config = {"auto_confirm": {"sec_read": True}}
        clear_all_auto_confirm(config)
        assert "auto_confirm" not in config

    def test_clear_removes_legacy_field(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.json"
        config_file.write_text('{"auto_confirm_forever": true}', encoding="utf-8")
        import fr_cli.conf.config as cfg_mod
        monkeypatch.setattr(cfg_mod, "CONFIG_FILE", config_file)

        config = {"auto_confirm_forever": True}
        clear_all_auto_confirm(config)
        assert "auto_confirm_forever" not in config

    def test_clear_no_op_when_empty(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.json"
        config_file.write_text("{}", encoding="utf-8")
        import fr_cli.conf.config as cfg_mod
        monkeypatch.setattr(cfg_mod, "CONFIG_FILE", config_file)

        config = {}
        clear_all_auto_confirm(config)  # 不应崩
        assert config == {}
