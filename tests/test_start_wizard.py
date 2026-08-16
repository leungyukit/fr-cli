"""
/start 一键快速开始向导测试(痛点 5)
"""
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def force_color(monkeypatch):
    """默认开颜色,验证 ANSI 转义码"""
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FR_CLI_NO_COLOR", raising=False)
    import sys as _sys
    monkeypatch.setattr(_sys.stdout, "isatty", lambda: True)
    import importlib
    from fr_cli.ui import output
    importlib.reload(output)


@pytest.fixture
def state_with_model():
    """已配模型的 state"""
    state = MagicMock()
    state.lang = "zh"
    state.provider = "doubao"
    state.display_provider = "doubao"
    state.display_model = "doubao-seed-2-1-turbo-260628"
    state.cfg = {
        "provider": "doubao",
        "default_provider": "doubao",
        "providers": {"doubao": {"key": "ark-fake", "model": "doubao-seed-2-1-turbo-260628"}},
    }
    state.save_cfg = MagicMock()
    state.reinit_client = MagicMock()
    state.master_agent = MagicMock(is_enabled=MagicMock(return_value=False))
    return state


@pytest.fixture
def state_no_model():
    """未配模型的 state"""
    state = MagicMock()
    state.lang = "zh"
    state.provider = "doubao"
    state.display_provider = "doubao"
    state.display_model = "doubao-seed-2-1-turbo-260628"
    state.cfg = {"providers": {}}
    state.save_cfg = MagicMock()
    state.reinit_client = MagicMock()
    state.master_agent = MagicMock(is_enabled=MagicMock(return_value=False))
    return state


# ---------- 注册 ----------

class TestRegistration:
    """/start 命令注册到 router"""

    def test_start_registered_in_router(self):
        from fr_cli.repl.router import COMMAND_ROUTES
        assert "/start" in COMMAND_ROUTES

    def test_start_handler_callable(self):
        from fr_cli.repl.router import COMMAND_ROUTES
        assert callable(COMMAND_ROUTES["/start"])


# ---------- 命令处理 ----------

class TestStartCommand:
    """/start 命令的子命令 / 主流程"""

    def test_skip_marks_done(self, capsys, state_with_model):
        from fr_cli.repl.commands.system.start import _cmd_start
        _cmd_start(state_with_model, ["/start", "skip"])
        out = capsys.readouterr().out
        assert "✅" in out
        assert state_with_model.cfg.get("start_wizard_done") is True
        state_with_model.save_cfg.assert_called_once()

    def test_reset_clears_done(self, capsys, state_with_model):
        from fr_cli.repl.commands.system.start import _cmd_start
        state_with_model.cfg["start_wizard_done"] = True
        _cmd_start(state_with_model, ["/start", "reset"])
        assert state_with_model.cfg.get("start_wizard_done") is False

    def test_unknown_arg_shows_failure(self, capsys, state_with_model):
        from fr_cli.repl.commands.system.start import _cmd_start
        _cmd_start(state_with_model, ["/start", "weird"])
        out = capsys.readouterr().out
        assert "❌" in out
        assert "weird" in out

    def test_main_flow_5_steps(self, capsys, state_with_model):
        """主流程跑 5 步(模型已配 + MasterAgent 跳过)"""
        from fr_cli.repl.commands.system.start import _cmd_start
        # mock input 让 MasterAgent 步骤回答 n
        with patch("builtins.input", return_value="n"):
            _cmd_start(state_with_model, ["/start"])
        out = capsys.readouterr().out
        # 5 个 Step 标题
        assert "Step 1/5" in out
        assert "Step 2/5" in out
        assert "Step 3/5" in out
        assert "Step 4/5" in out
        assert "Step 5/5" in out
        # 写标志
        assert state_with_model.cfg.get("start_wizard_done") is True

    def test_main_flow_no_model_runs_wizard(self, capsys, state_no_model):
        """未配模型时,第 2 步会跑 model_wizard"""
        from fr_cli.repl.commands.system.start import _cmd_start
        with patch("builtins.input", return_value="n"), \
             patch("fr_cli.conf.model_wizard.run_model_wizard") as mock_wizard:
            # mock wizard 返回同样的 cfg(模拟配置完成)
            mock_wizard.return_value = {
                "provider": "doubao",
                "default_provider": "doubao",
                "providers": {"doubao": {"key": "ark-fake", "model": "doubao-seed-2-1-turbo-260628"}},
            }
            _cmd_start(state_no_model, ["/start"])
            assert mock_wizard.called

    def test_main_flow_uses_output_api(self, capsys, state_with_model):
        """主流程应使用统一 output API(✅ ❌ ⚠️ ℹ️)"""
        from fr_cli.repl.commands.system.start import _cmd_start
        with patch("builtins.input", return_value="n"):
            _cmd_start(state_with_model, ["/start"])
        out = capsys.readouterr().out
        # Step 1 用 header(═══)
        assert "═══" in out
        # Step 2 用 info(ℹ️)— 已配模型
        assert "ℹ️" in out
        # 至少 1 个 ANSI 颜色码
        assert "\x1b[" in out


# ---------- 检测函数 ----------

class TestModelDetection:
    """_has_model_configured 检测函数"""

    def test_with_provider_and_key(self):
        from fr_cli.repl.commands.system.start import _has_model_configured
        state = MagicMock()
        state.cfg = {
            "provider": "doubao",
            "providers": {"doubao": {"key": "k"}},
        }
        assert _has_model_configured(state) is True

    def test_only_provider_no_key(self):
        from fr_cli.repl.commands.system.start import _has_model_configured
        state = MagicMock()
        state.cfg = {
            "provider": "doubao",
            "providers": {"doubao": {"key": ""}},
        }
        assert _has_model_configured(state) is False

    def test_legacy_top_level_key(self):
        from fr_cli.repl.commands.system.start import _has_model_configured
        state = MagicMock()
        state.cfg = {
            "provider": "zhipu",
            "key": "legacy",
            "providers": {},
        }
        assert _has_model_configured(state) is True

    def test_no_config(self):
        from fr_cli.repl.commands.system.start import _has_model_configured
        state = MagicMock()
        state.cfg = {}
        assert _has_model_configured(state) is False


# ---------- banner 集成 ----------

class TestBannerIntegration:
    """首次启动 banner 应提示 /start"""

    def test_banner_first_time_mentions_start(self, capsys):
        from fr_cli.repl.bootstrap import print_simple_banner
        from unittest.mock import MagicMock
        state = MagicMock()
        state.cfg = {"start_wizard_done": False, "allowed_dirs": ["/tmp"]}
        state.display_provider = "doubao"
        state.display_model = "doubao-seed-2-1-turbo-260628"
        state.provider = "doubao"
        state.session_id = "test"
        state.vfs = MagicMock(cwd="/tmp")
        print_simple_banner(state, "2.8.5")
        out = capsys.readouterr().out
        assert "/start" in out
        # 首次不应提示 /help(被 /start 替代了)
        # 但 Send /help 出现在 subtitle 之外,不影响

    def test_banner_after_done_no_start_hint(self, capsys):
        from fr_cli.repl.bootstrap import print_simple_banner
        state = MagicMock()
        state.cfg = {"start_wizard_done": True, "allowed_dirs": ["/tmp"]}
        state.display_provider = "doubao"
        state.display_model = "doubao-seed-2-1-turbo-260628"
        state.provider = "doubao"
        state.session_id = "test"
        state.vfs = MagicMock(cwd="/tmp")
        print_simple_banner(state, "2.8.5")
        out = capsys.readouterr().out
        # 不应再提示 /start
        assert "跑 5 步快速开始向导" not in out


# ---------- config 默认值 ----------

class TestConfigDefault:
    """start_wizard_done 默认值"""

    def test_default_config_has_start_wizard_done_false(self):
        from fr_cli.conf.config import _default_config
        assert _default_config().get("start_wizard_done") is False
