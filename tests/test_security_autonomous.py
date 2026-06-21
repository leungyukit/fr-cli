"""
自治模式安全策略测试
覆盖：manual / sandbox_auto / full_auto 三种模式，以及环境变量覆盖。
"""
import os

import pytest

from fr_cli.command.security import SecurityManager
from fr_cli.security.policy import (
    SANDBOX_SECURITY_KEYS,
    SYSTEM_SECURITY_KEYS,
    normalize_autonomous_mode,
)


@pytest.fixture
def fresh_sm(monkeypatch):
    """返回一个 fresh SecurityManager，并清理环境变量影响"""
    monkeypatch.delenv("FR_CLI_AUTONOMOUS_MODE", raising=False)
    monkeypatch.delenv("FR_CLI_NON_INTERACTIVE", raising=False)
    monkeypatch.delenv("FR_CLI_BATCH_CONFIRM", raising=False)
    cfg = {"auto_confirm": {}}
    return SecurityManager("zh", cfg)


class TestNormalizeAutonomousMode:
    def test_manual(self):
        assert normalize_autonomous_mode("manual") == "manual"
        assert normalize_autonomous_mode("OFF") == "manual"
        assert normalize_autonomous_mode("") == "manual"

    def test_sandbox_auto(self):
        assert normalize_autonomous_mode("sandbox_auto") == "sandbox_auto"
        assert normalize_autonomous_mode("SANDBOX_AUTO") == "sandbox_auto"

    def test_full_auto(self):
        assert normalize_autonomous_mode("full_auto") == "full_auto"

    def test_invalid_fallback(self):
        assert normalize_autonomous_mode("dangerous") == "manual"


class TestPolicyConstants:
    def test_no_overlap(self):
        assert SANDBOX_SECURITY_KEYS.isdisjoint(SYSTEM_SECURITY_KEYS)

    def test_core_keys_present(self):
        assert "sec_read" in SANDBOX_SECURITY_KEYS
        assert "sec_write" in SANDBOX_SECURITY_KEYS
        assert "sec_fetch_web" in SANDBOX_SECURITY_KEYS
        assert "sec_shell" in SYSTEM_SECURITY_KEYS
        assert "sec_exec" in SYSTEM_SECURITY_KEYS
        assert "sec_send_mail" in SYSTEM_SECURITY_KEYS


class TestSecurityManagerManual:
    def test_default_mode_is_manual(self, fresh_sm):
        assert fresh_sm.autonomous_mode == "manual"

    def test_manual_asks_for_sandbox(self, fresh_sm, monkeypatch):
        """manual 模式下即使是 sec_read 也要弹窗"""
        monkeypatch.setattr("builtins.input", lambda _: "y")
        assert fresh_sm.check("sec_read", "README.md") is True

    def test_manual_asks_for_system(self, fresh_sm, monkeypatch):
        monkeypatch.setattr("builtins.input", lambda _: "n")
        assert fresh_sm.check("sec_shell", "whoami") is False


class TestSecurityManagerSandboxAuto:
    def test_sandbox_keys_auto_allowed(self, fresh_sm):
        fresh_sm.set_autonomous_mode("sandbox_auto")
        for key in SANDBOX_SECURITY_KEYS:
            assert fresh_sm.check(key, f"test-{key}") is True

    def test_system_keys_still_require_confirm(self, fresh_sm, monkeypatch):
        fresh_sm.set_autonomous_mode("sandbox_auto")
        monkeypatch.setattr("builtins.input", lambda _: "n")
        for key in SYSTEM_SECURITY_KEYS:
            assert fresh_sm.check(key, f"test-{key}") is False

    def test_system_keys_default_deny_in_non_interactive(self, fresh_sm, monkeypatch):
        fresh_sm.set_autonomous_mode("sandbox_auto")
        monkeypatch.setenv("FR_CLI_NON_INTERACTIVE", "1")
        for key in SYSTEM_SECURITY_KEYS:
            assert fresh_sm.check(key, f"test-{key}") is False

    def test_env_var_overrides_config(self, fresh_sm, monkeypatch):
        """FR_CLI_AUTONOMOUS_MODE 环境变量可覆盖配置中的模式"""
        fresh_sm.set_autonomous_mode("manual")
        monkeypatch.setenv("FR_CLI_AUTONOMOUS_MODE", "sandbox_auto")
        assert fresh_sm.check("sec_read", "README.md") is True


class TestSecurityManagerFullAuto:
    def test_all_keys_allowed(self, fresh_sm):
        fresh_sm.set_autonomous_mode("full_auto")
        for key in SANDBOX_SECURITY_KEYS | SYSTEM_SECURITY_KEYS:
            assert fresh_sm.check(key, f"test-{key}") is True


class TestSetAutonomousMode:
    def test_persisted_to_config(self, fresh_sm, monkeypatch):
        saved = []
        monkeypatch.setattr("fr_cli.conf.config.save_config", lambda c: saved.append(dict(c)) or True)
        assert fresh_sm.set_autonomous_mode("sandbox_auto") is True
        assert fresh_sm.cfg["autonomous_mode"] == "sandbox_auto"
        assert saved[-1]["autonomous_mode"] == "sandbox_auto"

    def test_off_maps_to_manual(self, fresh_sm, monkeypatch):
        monkeypatch.setattr("fr_cli.conf.config.save_config", lambda c: True)
        fresh_sm.set_autonomous_mode("off")
        assert fresh_sm.autonomous_mode == "manual"
        assert fresh_sm.cfg["autonomous_mode"] == "manual"


class TestLegacyCompatibility:
    def test_batch_confirm_env_still_works(self, fresh_sm, monkeypatch):
        """FR_CLI_BATCH_CONFIRM=1 仍覆盖一切（向后兼容）"""
        fresh_sm.set_autonomous_mode("manual")
        monkeypatch.setenv("FR_CLI_BATCH_CONFIRM", "1")
        assert fresh_sm.check("sec_shell", "rm -rf /") is True

    def test_non_interactive_still_default_deny(self, fresh_sm, monkeypatch):
        """FR_CLI_NON_INTERACTIVE=1 仍默认拒绝，不被 sandbox_auto 覆盖"""
        fresh_sm.set_autonomous_mode("sandbox_auto")
        monkeypatch.setenv("FR_CLI_NON_INTERACTIVE", "1")
        assert fresh_sm.check("sec_read", "README.md") is True
        assert fresh_sm.check("sec_shell", "whoami") is False
