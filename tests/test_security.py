"""
四阶安全确认引擎测试
覆盖：Y/A/F/N 分支、批量确认、非交互模式、已放行状态、永久放行持久化。

v2.4.4 行为变更：
- fconfirm / sconfirm 改为 dict，按 sec_* 类别独立
- 旧版 bool 仍被 ask() 接受（向后兼容），但返回的 fconfirm / sconfirm 总是 dict
- 按 [F] 仅对当前 sec_* 类别永久放行（写入 cfg["auto_confirm"]，不再写 auto_confirm_forever）
"""
import pytest

from fr_cli.security.security import ask, clear_all_auto_confirm, _migrate_fconfirm


@pytest.fixture
def base_args(monkeypatch):
    # 确保 security 测试不受其他测试遗留的环境变量影响
    monkeypatch.delenv("FR_CLI_NON_INTERACTIVE", raising=False)
    monkeypatch.delenv("FR_CLI_BATCH_CONFIRM", raising=False)
    return {
        "k": "sec_read",
        "d": "README.md",
        "l": "zh",
        "fconfirm": {},   # v2.4.4: dict 而非 bool
        "sconfirm": {},   # v2.4.4: dict 而非 bool
        "config": {},
    }


class TestSecurityAsk:
    """测试 ask 函数各分支"""

    def test_y_once(self, base_args, monkeypatch):
        """[Y] 一次性放行：sconfirm / fconfirm 都不变（dict 中无 sec_read）"""
        monkeypatch.setattr("builtins.input", lambda _: "y")
        ok, s, f = ask(**base_args)
        assert ok is True
        assert s == {}
        assert f == {}

    def test_a_session(self, base_args, monkeypatch):
        """[A] 本次会话放行：sconfirm[sec_read] = True，fconfirm 不变"""
        monkeypatch.setattr("builtins.input", lambda _: "a")
        ok, s, f = ask(**base_args)
        assert ok is True
        assert s == {"sec_read": True}
        assert f == {}

    def test_f_forever(self, base_args, monkeypatch, tmp_path):
        """[F] 永世：仅对当前 sec_* 类别永久放行；写入 cfg["auto_confirm"] 而非 auto_confirm_forever"""
        config = {}
        base_args["config"] = config
        monkeypatch.setattr("builtins.input", lambda _: "f")
        # 避免写入真实配置文件
        saved = []
        monkeypatch.setattr("fr_cli.security.security.save_config", lambda c: saved.append(dict(c)))
        ok, s, f = ask(**base_args)
        assert ok is True
        assert s == {"sec_read": True}
        assert f == {"sec_read": True}
        # v2.4.4：写入 cfg["auto_confirm"]，而非 auto_confirm_forever
        assert "auto_confirm" in config
        assert config["auto_confirm"]["sec_read"] is True
        assert "auto_confirm_forever" not in config
        assert saved[-1]["auto_confirm"]["sec_read"] is True

    def test_f_does_not_bleed_into_other_categories(self, base_args, monkeypatch):
        """[F] 关键回归：按 F 放过 sec_read 不会顺带放过 sec_write"""
        base_args["k"] = "sec_read"
        monkeypatch.setattr("builtins.input", lambda _: "f")
        saved = []
        monkeypatch.setattr("fr_cli.security.security.save_config", lambda c: saved.append(dict(c)))
        ok, s, f = ask(**base_args)
        assert ok is True
        # fconfirm 仅含 sec_read
        assert f == {"sec_read": True}
        # 后续 sec_write 必须重新弹窗
        base_args["fconfirm"] = f
        base_args["k"] = "sec_write"
        base_args["d"] = "/etc/passwd"
        base_args["config"] = {}
        monkeypatch.setattr("builtins.input", lambda _: "n")  # 用户拒绝
        ok2, s2, f2 = ask(**base_args)
        assert ok2 is False
        # sec_read 仍保留在 fconfirm，但 sec_write 不被放过
        assert f2.get("sec_read") is True
        assert "sec_write" not in f2

    def test_n_deny(self, base_args, monkeypatch):
        """[N] 拒绝：sconfirm / fconfirm 都不变"""
        monkeypatch.setattr("builtins.input", lambda _: "n")
        ok, s, f = ask(**base_args)
        assert ok is False
        assert s == {}
        assert f == {}

    def test_empty_deny(self, base_args, monkeypatch):
        """回车等同于 N"""
        monkeypatch.setattr("builtins.input", lambda _: "")
        ok, s, f = ask(**base_args)
        assert ok is False
        assert s == {}
        assert f == {}

    def test_already_fconfirm_dict(self, base_args):
        """fconfirm 已是 dict 且包含当前 k → 直接放行"""
        base_args["fconfirm"] = {"sec_read": True}
        ok, s, f = ask(**base_args)
        assert ok is True
        # 状态不变
        assert s == {}
        assert f == {"sec_read": True}

    def test_already_fconfirm_bool_true_legacy(self, base_args):
        """兼容旧版：fconfirm = True 迁移为所有类别放行"""
        base_args["fconfirm"] = True
        ok, s, f = ask(**base_args)
        assert ok is True
        # 迁移后，f 应为包含所有已知 sec_* 类别的 dict
        assert isinstance(f, dict)
        assert f.get("sec_read") is True
        assert f.get("sec_write") is True
        assert f.get("sec_exec") is True

    def test_already_sconfirm_bool_true_legacy(self, base_args):
        """兼容旧版：sconfirm = True 视为全类别放行"""
        base_args["sconfirm"] = True
        ok, s, f = ask(**base_args)
        assert ok is True
        # sconfirm 被迁移为 dict
        assert isinstance(s, dict)
        assert s.get("sec_read") is True

    def test_sconfirm_dict_per_category(self, base_args, monkeypatch):
        """sconfirm = {"sec_read": True}：仅 sec_read 放行，sec_write 仍需弹窗"""
        base_args["sconfirm"] = {"sec_read": True}
        base_args["k"] = "sec_write"
        # sec_write 不在 sconfirm 中 → 弹窗 → 用户按 n → 拒绝
        monkeypatch.setattr("builtins.input", lambda _: "n")
        ok, s, f = ask(**base_args)
        assert ok is False
        # sconfirm 仍只含 sec_read（sec_write 拒绝不会污染）
        assert base_args["sconfirm"] == {"sec_read": True}

    def test_batch_confirm(self, base_args, monkeypatch):
        monkeypatch.setenv("FR_CLI_BATCH_CONFIRM", "1")
        ok, s, f = ask(**base_args)
        assert ok is True
        assert s == {}
        assert f == {}

    def test_non_interactive_deny(self, base_args, monkeypatch):
        monkeypatch.setenv("FR_CLI_NON_INTERACTIVE", "1")
        ok, s, f = ask(**base_args)
        assert ok is False
        assert s == {}
        assert f == {}


class TestMigrateFconfirm:
    """_migrate_fconfirm 迁移逻辑"""

    def test_bool_false_to_empty(self):
        assert _migrate_fconfirm(False) == {}

    def test_dict_passthrough(self):
        d = {"sec_read": True}
        assert _migrate_fconfirm(d) is d

    def test_bool_true_to_all_categories(self):
        result = _migrate_fconfirm(True)
        assert result.get("sec_read") is True
        assert result.get("sec_write") is True
        assert result.get("sec_exec") is True
        assert result.get("sec_mcp_call") is True
        assert result.get("sec_shell") is True


class TestClearAllAutoConfirm:
    """clear_all_auto_confirm /unconfirm 入口"""

    def test_clear_new_format(self):
        config = {"auto_confirm": {"sec_read": True, "sec_write": True}, "lang": "zh"}
        cleared = []
        import fr_cli.security.security as sec
        orig = sec.save_config
        sec.save_config = lambda c: cleared.append(dict(c))
        try:
            clear_all_auto_confirm(config)
        finally:
            sec.save_config = orig
        assert "auto_confirm" not in config
        assert config["lang"] == "zh"  # 其它字段保留

    def test_clear_legacy_format(self):
        config = {"auto_confirm_forever": True, "lang": "zh"}
        cleared = []
        import fr_cli.security.security as sec
        orig = sec.save_config
        sec.save_config = lambda c: cleared.append(dict(c))
        try:
            clear_all_auto_confirm(config)
        finally:
            sec.save_config = orig
        assert "auto_confirm_forever" not in config
        assert config["lang"] == "zh"
