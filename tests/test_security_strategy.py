"""
可注入安全确认策略（fr_cli.security.strategy）测试

覆盖：四种策略的行为契约、fail-closed 语义、SecurityManager 集成。
"""

from fr_cli.security.strategy import (
    AutoAllowStrategy,
    AutoDenyStrategy,
    CallbackStrategy,
    ConfirmDecision,
    TerminalStrategy,
    build_default_strategy,
)


class TestConfirmDecision:
    def test_allow_and_deny(self):
        assert ConfirmDecision.allow().allowed is True
        assert ConfirmDecision.deny("x").allowed is False
        assert ConfirmDecision.deny("x").reason == "x"

    def test_bool_conversion(self):
        assert bool(ConfirmDecision.allow()) is True
        assert bool(ConfirmDecision.deny()) is False


class TestAutoDenyStrategy:
    def test_denies_by_default(self):
        """非交互场景必须 fail-closed"""
        s = AutoDenyStrategy()
        decision = s.check("sec_write", "/etc/passwd")
        assert decision.allowed is False
        assert "默认拒绝" in decision.reason


class TestAutoAllowStrategy:
    def test_allows(self):
        s = AutoAllowStrategy()
        assert s.check("sec_write", "/x").allowed is True


class TestCallbackStrategy:
    def test_bool_result(self):
        s = CallbackStrategy(lambda *a: True)
        assert s.check("sec_write", "/x").allowed is True

    def test_false_result(self):
        s = CallbackStrategy(lambda *a: False)
        assert s.check("sec_write", "/x").allowed is False

    def test_string_result(self):
        s = CallbackStrategy(lambda *a: "y")
        assert s.check("sec_write", "/x").scope == "once"

    def test_session_scope(self):
        s = CallbackStrategy(lambda *a: "a")
        decision = s.check("sec_write", "/x")
        assert decision.scope == "session"
        assert s.sconfirm.get("sec_write") is True

    def test_forever_scope_persists_to_config(self):
        cfg = {}
        s = CallbackStrategy(lambda *a: "f", config=cfg)
        decision = s.check("sec_write", "/x")
        assert decision.scope == "forever"
        assert cfg["auto_confirm"]["sec_write"] is True

    def test_resolver_exception_fails_closed(self):
        """确认通道故障绝不能放行高危操作"""
        def boom(*args):
            raise RuntimeError("channel down")

        s = CallbackStrategy(boom)
        decision = s.check("sec_shell", "rm -rf /")
        assert decision.allowed is False
        assert "异常" in decision.reason

    def test_unknown_result_denies(self):
        s = CallbackStrategy(lambda *a: object())
        assert s.check("sec_write", "/x").allowed is False


class TestBuildDefaultStrategy:
    def test_terminal_by_default(self, monkeypatch):
        monkeypatch.delenv("FR_CLI_NON_INTERACTIVE", raising=False)
        assert isinstance(build_default_strategy(), TerminalStrategy)

    def test_auto_deny_when_non_interactive(self, monkeypatch):
        monkeypatch.setenv("FR_CLI_NON_INTERACTIVE", "1")
        assert isinstance(build_default_strategy(), AutoDenyStrategy)


class TestSecurityManagerIntegration:
    def _mgr(self, cfg=None, monkeypatch=None):
        from fr_cli.command.security import SecurityManager
        return SecurityManager("zh", cfg if cfg is not None else {})

    def test_default_strategy_is_terminal(self):
        mgr = self._mgr()
        assert isinstance(mgr.strategy, TerminalStrategy)

    def test_set_strategy(self):
        mgr = self._mgr()
        strat = AutoDenyStrategy(config=mgr.cfg)
        mgr.set_strategy(strat)
        assert mgr.strategy is strat
        assert mgr.check("sec_write", "/x") is False

    def test_callback_strategy_integration(self):
        """bot 场景：确认结果由外部回调决定"""
        from fr_cli.command.security import SecurityManager
        mgr = SecurityManager("zh", {})
        mgr.set_strategy(CallbackStrategy(lambda *a: "y", config=mgr.cfg))
        assert mgr.check("sec_exec", "/ls") is True

    def test_check_accepts_tool_name_and_args(self):
        mgr = self._mgr()
        seen = {}

        def resolver(key, target, tool_name, args):
            seen["tool"] = tool_name
            seen["args"] = args
            return True

        mgr.set_strategy(CallbackStrategy(resolver, config=mgr.cfg))
        mgr.check("sec_write", "/a", tool_name="write_file", args={"path": "/a"})
        assert seen["tool"] == "write_file"
        assert seen["args"] == {"path": "/a"}

    def test_unconfirm_all_clears_strategy_state(self):
        mgr = self._mgr()
        mgr.set_strategy(CallbackStrategy(lambda *a: "f", config=mgr.cfg))
        mgr.check("sec_write", "/x")
        assert mgr.fconfirm.get("sec_write") is True
        mgr.unconfirm_all()
        assert mgr.fconfirm == {}
        assert mgr.strategy.fconfirm == {}
