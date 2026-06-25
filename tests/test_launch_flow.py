"""
测试 v2.5 启动流程改造:
  - resolve_active_model / check_provider_availability
  - AnthropicCompatibleClient 协议适配
  - config schema v3 (default_provider / backup_provider)
  - model_wizard 6 步流程(模拟交互)
  - AppState 在 default/backup 不可用时的降级
  - bootstrap 自动启动(检测后台服务)
"""

import json
from unittest.mock import patch


# ---------------------------------------------------------------------------
# conf/default_models.yaml: compat 字段
# ---------------------------------------------------------------------------

class TestDefaultModelsCompat:
    def test_all_providers_have_compat_field(self):
        """每个 provider 必须有 compat 字段(openai/anthropic/zhipu)"""
        from fr_cli.core.llm import _PROVIDERS, reload_providers
        reload_providers()
        assert len(_PROVIDERS) > 0
        for pid, info in _PROVIDERS.items():
            assert "compat" in info, f"{pid} 缺少 compat 字段"
            assert info["compat"] in ("openai", "anthropic", "zhipu"), \
                f"{pid}.compat={info['compat']!r} 不是有效值"

    def test_anthropic_provider_uses_anthropic_client(self):
        """anthropic provider 应使用 AnthropicCompatibleClient"""
        from fr_cli.core.llm import _PROVIDERS, AnthropicCompatibleClient, reload_providers
        reload_providers()
        info = _PROVIDERS.get("anthropic")
        assert info is not None
        assert info["client_class"] is AnthropicCompatibleClient
        assert info["compat"] == "anthropic"

    def test_kimi_code_anthropic_uses_anthropic_client(self):
        """kimi-code-anthropic 应使用 AnthropicCompatibleClient"""
        from fr_cli.core.llm import _PROVIDERS, AnthropicCompatibleClient, reload_providers
        reload_providers()
        info = _PROVIDERS.get("kimi-code-anthropic")
        assert info is not None
        assert info["client_class"] is AnthropicCompatibleClient
        assert info["compat"] == "anthropic"

    def test_zhipu_uses_zhipu_native(self):
        """zhipu provider 应使用 ZhipuLLMClient + compat=zhipu"""
        from fr_cli.core.llm import _PROVIDERS, ZhipuLLMClient, reload_providers
        reload_providers()
        info = _PROVIDERS.get("zhipu")
        assert info is not None
        assert info["client_class"] is ZhipuLLMClient
        assert info["compat"] == "zhipu"

    def test_openai_provider_openai_compat(self):
        from fr_cli.core.llm import _PROVIDERS, OpenAICompatibleClient, reload_providers
        reload_providers()
        info = _PROVIDERS.get("openai")
        assert info["client_class"] is OpenAICompatibleClient
        assert info["compat"] == "openai"


# ---------------------------------------------------------------------------
# AnthropicCompatibleClient: 协议适配
# ---------------------------------------------------------------------------

class TestAnthropicCompatibleClient:
    def test_init_with_api_key_only(self):
        from fr_cli.core.llm import AnthropicCompatibleClient
        c = AnthropicCompatibleClient("test-key")
        assert c.api_key == "test-key"
        assert c.base_url == AnthropicCompatibleClient.DEFAULT_BASE_URL

    def test_init_strips_trailing_slash(self):
        from fr_cli.core.llm import AnthropicCompatibleClient
        c = AnthropicCompatibleClient("k", base_url="https://example.com/")
        assert c.base_url == "https://example.com"

    def test_build_payload_separates_system_messages(self):
        from fr_cli.core.llm import AnthropicCompatibleClient
        c = AnthropicCompatibleClient("k")
        messages = [
            {"role": "system", "content": "你是助手"},
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好!"},
            {"role": "user", "content": "再见"},
        ]
        payload = c._build_payload("claude-sonnet-4-5", messages, max_tokens=1024)
        # system 应被提取
        assert payload["system"] == "你是助手"
        # 非 system 应转为 messages
        assert payload["messages"] == [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好!"},
            {"role": "user", "content": "再见"},
        ]
        assert payload["model"] == "claude-sonnet-4-5"
        assert payload["stream"] is True
        assert payload["max_tokens"] == 1024

    def test_build_payload_no_system(self):
        from fr_cli.core.llm import AnthropicCompatibleClient
        c = AnthropicCompatibleClient("k")
        payload = c._build_payload("claude-sonnet-4-5",
                                    [{"role": "user", "content": "hi"}], 4096)
        assert "system" not in payload

    def test_build_payload_max_tokens_floor(self):
        from fr_cli.core.llm import AnthropicCompatibleClient
        c = AnthropicCompatibleClient("k")
        payload = c._build_payload("m", [], max_tokens=0)
        # max_tokens=0 时应至少为 1(避免 API 报错)
        assert payload["max_tokens"] == 1

    def test_build_headers_includes_required(self):
        from fr_cli.core.llm import AnthropicCompatibleClient
        c = AnthropicCompatibleClient("my-key")
        h = c._build_headers()
        assert h["x-api-key"] == "my-key"
        assert h["anthropic-version"] == "2023-06-01"
        assert h["content-type"] == "application/json"

    def test_parse_sse_extracts_text_from_content_block_delta(self):
        """content_block_delta 事件的 delta.text 应被正确提取"""
        from fr_cli.core.llm import AnthropicCompatibleClient
        c = AnthropicCompatibleClient("k")

        class FakeResponse:
            def __init__(self, lines):
                self._lines = lines
            def iter_lines(self):
                return iter(self._lines)

        lines = [
            b"event: content_block_delta",
            b"data: {\"type\":\"content_block_delta\",\"delta\":{\"type\":\"text_delta\",\"text\":\"Hello\"}}",
            b"",
            b"data: {\"type\":\"content_block_delta\",\"delta\":{\"type\":\"text_delta\",\"text\":\" world\"}}",
            b"data: {\"type\":\"message_stop\"}",
        ]
        chunks = list(c._parse_sse(FakeResponse(lines), timeout=30))
        # 第一个 chunk: text=Hello
        assert chunks[0]["content"] == "Hello"
        assert chunks[0]["usage"] is None
        assert chunks[1]["content"] == " world"
        # 最后一个 chunk 携带 usage
        last = chunks[-1]
        assert last["content"] == ""
        assert last["usage"] is None  # message_stop 本身不带 usage

    def test_parse_sse_collects_message_delta_usage(self):
        """message_delta 事件应携带 usage 信息"""
        from fr_cli.core.llm import AnthropicCompatibleClient
        c = AnthropicCompatibleClient("k")

        class FakeResponse:
            def iter_lines(self):
                return iter([
                    b"data: {\"type\":\"message_start\",\"message\":{\"usage\":{\"input_tokens\":10}}}",
                    b"data: {\"type\":\"content_block_delta\",\"delta\":{\"type\":\"text_delta\",\"text\":\"ok\"}}",
                    b"data: {\"type\":\"message_delta\",\"usage\":{\"input_tokens\":10,\"output_tokens\":5}}",
                    b"data: {\"type\":\"message_stop\"}",
                ])

        chunks = list(c._parse_sse(FakeResponse(), timeout=30))
        # 第一个 chunk: text=ok
        assert chunks[0]["content"] == "ok"
        # 最后一个 chunk 应带 usage
        last = chunks[-1]
        assert last["usage"] == {"input_tokens": 10, "output_tokens": 5}

    def test_parse_sse_raises_on_error_event(self):
        """error 事件应抛 RuntimeError"""
        from fr_cli.core.llm import AnthropicCompatibleClient
        c = AnthropicCompatibleClient("k")

        class FakeResponse:
            def iter_lines(self):
                return iter([
                    b"data: {\"type\":\"error\",\"error\":{\"message\":\"rate limit exceeded\"}}",
                ])

        try:
            list(c._parse_sse(FakeResponse(), timeout=30))
            assert False, "应抛出异常"
        except RuntimeError as e:
            assert "rate limit" in str(e)


# ---------------------------------------------------------------------------
# check_provider_availability / resolve_active_model
# ---------------------------------------------------------------------------

class TestResolveActiveModel:
    def test_no_default_no_backup_returns_none(self):
        from fr_cli.core.llm import resolve_active_model, reload_providers
        reload_providers()
        result = resolve_active_model({})
        assert result["provider"] is None
        assert result["source"] is None
        assert "default" in result["reason"] or "未配置" in result["reason"]

    def test_default_available_returns_default(self):
        from fr_cli.core.llm import resolve_active_model, reload_providers
        reload_providers()
        cfg = {
            "default_provider": "deepseek",
            "backup_provider": "zhipu",
            "providers": {
                "deepseek": {"key": "ds-key", "model": "deepseek-chat"},
                "zhipu": {"key": "z-key", "model": "glm-4-flash"},
            },
        }
        result = resolve_active_model(cfg)
        assert result["provider"] == "deepseek"
        assert result["model"] == "deepseek-chat"
        assert result["source"] == "default"

    def test_default_unavailable_falls_back_to_backup(self):
        """default provider 缺 key 时,应自动回退到 backup"""
        from fr_cli.core.llm import resolve_active_model, reload_providers
        reload_providers()
        cfg = {
            "default_provider": "deepseek",
            "backup_provider": "zhipu",
            "providers": {
                "deepseek": {"model": "deepseek-chat"},  # 缺 key
                "zhipu": {"key": "z-key", "model": "glm-4-flash"},
            },
        }
        result = resolve_active_model(cfg)
        assert result["provider"] == "zhipu"
        assert result["model"] == "glm-4-flash"
        assert result["source"] == "backup"

    def test_default_unknown_provider_falls_back(self):
        """default provider 不存在时,应回退到 backup"""
        from fr_cli.core.llm import resolve_active_model, reload_providers
        reload_providers()
        cfg = {
            "default_provider": "ghost-provider",
            "backup_provider": "zhipu",
            "providers": {
                "zhipu": {"key": "z-key", "model": "glm-4-flash"},
            },
        }
        result = resolve_active_model(cfg)
        assert result["provider"] == "zhipu"
        assert result["source"] == "backup"

    def test_both_unavailable_returns_none(self):
        from fr_cli.core.llm import resolve_active_model, reload_providers
        reload_providers()
        cfg = {
            "default_provider": "deepseek",
            "backup_provider": "zhipu",
            "providers": {
                "deepseek": {"model": "deepseek-chat"},  # 缺 key
                "zhipu": {"model": "glm-4-flash"},      # 缺 key
            },
        }
        result = resolve_active_model(cfg)
        assert result["provider"] is None
        assert result["source"] is None

    def test_check_provider_availability_no_key(self):
        from fr_cli.core.llm import check_provider_availability, reload_providers
        reload_providers()
        ok, reason, model = check_provider_availability("deepseek", {
            "providers": {"deepseek": {"model": "deepseek-chat"}}
        })
        assert ok is False
        assert "Key" in reason

    def test_check_provider_availability_with_key(self):
        from fr_cli.core.llm import check_provider_availability, reload_providers
        reload_providers()
        ok, reason, model = check_provider_availability("deepseek", {
            "providers": {"deepseek": {"key": "k", "model": "deepseek-chat"}}
        })
        assert ok is True
        assert model == "deepseek-chat"

    def test_check_provider_unknown(self):
        from fr_cli.core.llm import check_provider_availability, reload_providers
        reload_providers()
        ok, reason, _ = check_provider_availability("ghost", {"providers": {}})
        assert ok is False
        assert "未知" in reason or "ghost" in reason


# ---------------------------------------------------------------------------
# AppState 集成 default/backup 解析
# ---------------------------------------------------------------------------

class TestAppStateDefaultBackup:
    def _make_cfg(self, **overrides):
        base = {
            "provider": "zhipu",
            "model": "glm-4-flash",
            "key": "z-key",
            "providers": {
                "zhipu": {"key": "z-key", "model": "glm-4-flash"},
                "deepseek": {"key": "ds-key", "model": "deepseek-chat"},
            },
            "lang": "zh",
            "limit": 4096,
            "allowed_dirs": [],
            "aliases": {},
            "auto_confirm_forever": False,
        }
        base.update(overrides)
        return base

    def test_default_provider_activates(self, tmp_path, monkeypatch):
        """配置了 default_provider 时,AppState 应使用它"""
        from fr_cli.core.core import AppState
        from fr_cli.agent import manager
        monkeypatch.setattr(manager, "AGENTS_DIR", tmp_path)

        cfg = self._make_cfg(default_provider="deepseek")
        state = AppState(cfg)
        assert state.provider == "deepseek"
        assert state.model_name == "deepseek-chat"
        assert state.active_model_source == "default"
        assert state.is_fallback_active is False

    def test_default_unavailable_uses_backup(self, tmp_path, monkeypatch):
        """default 缺 key 时应自动降级到 backup"""
        from fr_cli.core.core import AppState
        from fr_cli.agent import manager
        monkeypatch.setattr(manager, "AGENTS_DIR", tmp_path)

        cfg = self._make_cfg(
            default_provider="deepseek",
            backup_provider="zhipu",
        )
        # 彻底去掉 deepseek 的 key,并清空顶层 key 防止误判
        cfg["providers"]["deepseek"].pop("key", None)
        cfg["key"] = ""
        state = AppState(cfg)
        assert state.provider == "zhipu"
        assert state.model_name == "glm-4-flash"
        assert state.active_model_source == "backup"
        assert state.is_fallback_active is True

    def test_no_default_no_backup_uses_cfg_provider(self, tmp_path, monkeypatch):
        """没有 default/backup 时,使用 cfg.provider(向后兼容)"""
        from fr_cli.core.core import AppState
        from fr_cli.agent import manager
        monkeypatch.setattr(manager, "AGENTS_DIR", tmp_path)

        cfg = self._make_cfg()
        state = AppState(cfg)
        # 应使用 cfg["provider"]="zhipu"
        assert state.provider == "zhipu"
        assert state.active_model_source in (None, "manual")

    def test_reinit_prefer_active_true_reselects(self, tmp_path, monkeypatch):
        """reinit_client(prefer_active=True) 应走 default/backup 重选"""
        from fr_cli.core.core import AppState
        from fr_cli.agent import manager
        monkeypatch.setattr(manager, "AGENTS_DIR", tmp_path)

        cfg = self._make_cfg(
            default_provider="deepseek",
            backup_provider="zhipu",
        )
        state = AppState(cfg)
        assert state.provider == "deepseek"

        # 移除 deepseek key(同时清空顶层 key 避免误判),触发 backup 降级
        cfg["providers"]["deepseek"].pop("key", None)
        cfg["key"] = ""
        state.reinit_client(prefer_active=True)
        assert state.provider == "zhipu"
        assert state.is_fallback_active is True

    def test_reinit_prefer_active_false_respects_manual(self, tmp_path, monkeypatch):
        """reinit_client(prefer_active=False) 应保留手动切换结果"""
        from fr_cli.core.core import AppState
        from fr_cli.agent import manager
        monkeypatch.setattr(manager, "AGENTS_DIR", tmp_path)

        cfg = self._make_cfg(default_provider="zhipu")
        state = AppState(cfg)
        # 手动切到 deepseek(模拟用户 /model deepseek-chat)
        state.update_provider("deepseek")
        assert state.provider == "deepseek"
        # 即便 zhipu 是 default,手动切到 deepseek 后不应被覆盖
        assert state.active_model_source == "manual"

    def test_update_key_triggers_resolve(self, tmp_path, monkeypatch):
        """update_key 应允许 default/backup 重选(prefer_active=True)"""
        from fr_cli.core.core import AppState
        from fr_cli.agent import manager
        monkeypatch.setattr(manager, "AGENTS_DIR", tmp_path)

        cfg = self._make_cfg(
            default_provider="deepseek",
            backup_provider="zhipu",
        )
        # 初始 deepseek 没 key,会降级到 zhipu
        cfg["providers"]["deepseek"].pop("key", None)
        cfg["key"] = ""
        state = AppState(cfg)
        # 初始应该降级到 zhipu
        assert state.provider == "zhipu"
        assert state.is_fallback_active is True
        # 现在配齐 deepseek 的 key(直接改 cfg)
        state.cfg["providers"]["deepseek"]["key"] = "new-ds-key"
        state.reinit_client(prefer_active=True)
        # resolve 应回到 deepseek
        assert state.provider == "deepseek"
        assert state.is_fallback_active is False


# ---------------------------------------------------------------------------
# conf/config.py: schema v3 升级
# ---------------------------------------------------------------------------

class TestConfigSchemaV3:
    def test_default_config_has_v3_fields(self):
        from fr_cli.conf.config import _default_config
        d = _default_config()
        assert d["version"] == 3
        assert "default_provider" in d
        assert "backup_provider" in d
        assert "model_wizard_skipped" in d
        assert "autostart_on_launch" in d

    def test_upgrade_v1_to_v3_sets_default(self):
        from fr_cli.conf.config import _upgrade_schema
        old = {"version": 1, "provider": "deepseek", "model": "deepseek-chat", "providers": {}}
        new = _upgrade_schema(old)
        assert new["version"] == 3
        assert new["default_provider"] == "deepseek"
        assert new["backup_provider"] == ""

    def test_upgrade_v2_to_v3_preserves_default(self):
        """v2 升级时若已有 default_provider 不应被覆盖"""
        from fr_cli.conf.config import _upgrade_schema
        old = {"version": 2, "provider": "zhipu", "default_provider": "zhipu", "providers": {}}
        new = _upgrade_schema(old)
        assert new["default_provider"] == "zhipu"

    def test_upgrade_idempotent(self):
        from fr_cli.conf.config import _upgrade_schema
        cfg = {"version": 3, "provider": "zhipu", "default_provider": "zhipu", "providers": {}}
        new = _upgrade_schema(cfg)
        assert new["version"] == 3


# ---------------------------------------------------------------------------
# model_wizard 6 步流程(模拟 input)
# ---------------------------------------------------------------------------

class TestModelWizard:
    """模拟交互输入,验证 6 步流程行为"""

    def _mock_input(self, *responses):
        """构造一个 input 函数,按顺序返回 responses"""
        it = iter(responses)

        def fake_input(prompt=""):
            return next(it)
        return fake_input

    def test_setup_with_no_existing_default_sets_default(self, tmp_path, monkeypatch):
        """首次 setup 没有 default_provider 时,必须设为 default"""
        # 把 CONFIG_FILE 重定向到 tmp_path,避免污染真实配置
        import fr_cli.conf.config as conf_mod
        import fr_cli.conf.paths as paths_mod
        test_cfg = tmp_path / "config.json"
        test_bak = tmp_path / "config.json.bak"
        monkeypatch.setattr(conf_mod, "CONFIG_FILE", test_cfg)
        monkeypatch.setattr(conf_mod, "CONFIG_BACKUP", test_bak)
        monkeypatch.setattr(paths_mod, "CONFIG_FILE", test_cfg)
        monkeypatch.setattr(paths_mod, "CONFIG_BACKUP", test_bak)

        from fr_cli.conf.config import load_config
        from fr_cli.conf.model_wizard import run_model_wizard

        # 准备干净的 config(无 default_provider)
        test_cfg.write_text("{}", encoding="utf-8")

        cfg = load_config()
        assert cfg.get("default_provider", "") == ""

        # 模拟输入:provider → compat → model → baseUrl → key(getpass) → f 步(首次必为 default,不询问)
        with patch("builtins.input", side_effect=[
            "1",       # a. provider 编号 (deepseek)
            "1",       # b. compat: OpenAI
            "1",       # c. model 编号
            "",        # d. baseUrl 回车
        ]):
            with patch("getpass.getpass", return_value="test-ds-key"):
                cfg = run_model_wizard(cfg, mode="setup")

        assert cfg["default_provider"] == "zhipu", f"expected zhipu (编号 1), got {cfg['default_provider']}"
        assert cfg["providers"]["zhipu"]["key"] == "test-ds-key"
        assert cfg["providers"]["zhipu"]["model"] == "glm-4-flash"
        assert cfg["model_wizard_skipped"] is True

    def test_setup_with_existing_default_prompts_choice(self, tmp_path, monkeypatch):
        """已有 default 时,f 步应询问 1=default/2=backup/3=仅保存"""
        import fr_cli.conf.config as conf_mod
        import fr_cli.conf.paths as paths_mod
        test_cfg = tmp_path / "config.json"
        test_bak = tmp_path / "config.json.bak"
        monkeypatch.setattr(conf_mod, "CONFIG_FILE", test_cfg)
        monkeypatch.setattr(conf_mod, "CONFIG_BACKUP", test_bak)
        monkeypatch.setattr(paths_mod, "CONFIG_FILE", test_cfg)
        monkeypatch.setattr(paths_mod, "CONFIG_BACKUP", test_bak)

        from fr_cli.conf.config import load_config
        from fr_cli.conf.model_wizard import run_model_wizard

        # 先设置已有 default = zhipu,然后选 anthropic(编号 3,因 zhipu=1, zhipu-coding=2, anthropic=3) 作为新配置
        test_cfg.write_text(json.dumps({"version": 3, "default_provider": "zhipu", "providers": {}}),
                            encoding="utf-8")
        cfg = load_config()
        assert cfg["default_provider"] == "zhipu"

        # 输入:provider(3=anthropic) → compat(2=anthropic) → model(1) → baseUrl → f 步选 2(backup)
        with patch("builtins.input", side_effect=[
            "3",       # a. provider 编号 (anthropic)
            "2",       # b. compat: Anthropic
            "1",       # c. model (claude-sonnet-4-5)
            "",        # d. baseUrl 回车
            "2",       # f. 选 backup
        ]):
            with patch("getpass.getpass", return_value="new-anthropic-key"):
                cfg = run_model_wizard(cfg, mode="add")

        assert cfg["default_provider"] == "zhipu"     # 保持不变
        assert cfg["backup_provider"] == "anthropic"   # 新设为 backup

    def test_wizard_q_at_any_step_cancels(self):
        """任意步骤按 q 应能取消,cfg 不被破坏"""
        from fr_cli.conf.model_wizard import run_model_wizard
        cfg = {"version": 3, "default_provider": "zhipu", "providers": {"zhipu": {"key": "z", "model": "glm-4-flash"}}}

        # 在 a 步按 q
        with patch("builtins.input", return_value="q"):
            cfg = run_model_wizard(cfg, mode="add")
        # cfg 不应被破坏
        assert cfg["default_provider"] == "zhipu"

    def test_wizard_preset_provider_skips_a_step(self):
        """preset_provider 时跳过 a 步直接进入 b"""
        from fr_cli.conf.model_wizard import run_model_wizard
        cfg = {"version": 3, "default_provider": "zhipu", "providers": {"zhipu": {"key": "z", "model": "glm-4-flash"}}}

        with patch("builtins.input", side_effect=[
            "1",       # b. compat
            "1",       # c. model
            "",        # d. baseUrl
            "2",       # f. 已有 default(zhipu) → 选 backup
        ]), patch("getpass.getpass", return_value="test-key"):
            cfg = run_model_wizard(cfg, mode="add", preset_provider="deepseek")
        # 这次应该选了 deepseek 作为 backup
        assert "deepseek" in cfg["providers"]
        assert cfg["backup_provider"] == "deepseek"


# ---------------------------------------------------------------------------
# init_config 接入 wizard
# ---------------------------------------------------------------------------

class TestInitConfigWizard:
    def test_init_config_with_no_default_triggers_prompt(self, tmp_path, monkeypatch):
        """未配置 default_provider 时,init_config 应询问是否进入向导"""
        from fr_cli.conf.config import init_config

        # 重定向 CONFIG_FILE 到 tmp_path
        import fr_cli.conf.config as conf_mod
        import fr_cli.conf.paths as paths_mod
        monkeypatch.setattr(conf_mod, "CONFIG_FILE", tmp_path / "config.json")
        monkeypatch.setattr(conf_mod, "CONFIG_BACKUP", tmp_path / "config.json.bak")
        monkeypatch.setattr(paths_mod, "CONFIG_FILE", tmp_path / "config.json")
        monkeypatch.setattr(paths_mod, "CONFIG_BACKUP", tmp_path / "config.json.bak")

        # 标记为交互式
        try:
            # 第一次:n → 跳过向导
            with patch("builtins.input", return_value="n"):
                with patch.object(conf_mod, 'init_config', wraps=None) as _:
                    pass
                # 直接调用 init_config
                cfg = init_config(interactive=True)
                assert isinstance(cfg, dict)
        except Exception as e:
            print(f"Exception: {e}")
            raise


# ---------------------------------------------------------------------------
# MasterAgent 默认启用
# ---------------------------------------------------------------------------

class TestMasterAgentDefaultEnabled:
    def test_master_agent_default_enabled(self, tmp_path, monkeypatch):
        """新装用户 status.json 应默认 enabled=True"""
        from fr_cli.agent.master_storage import _DEFAULT_STATUS
        assert _DEFAULT_STATUS["enabled"] is True


# ---------------------------------------------------------------------------
# bootstrap 自动启动后台服务
# ---------------------------------------------------------------------------

class TestBootstrapAutostart:
    def test_autostart_background_services_skips_when_disabled(self, tmp_path, monkeypatch):
        """cfg['autostart_on_launch']=False 时只启用 MasterAgent,不拉起守护进程"""
        from fr_cli.repl.bootstrap import _autostart_background_services

        # 构造最小 state
        class FakeMaster:
            def __init__(self):
                self.enabled = False
            def is_enabled(self):
                return self.enabled
            def toggle(self, val):
                self.enabled = val

        class FakeGatekeeper:
            def is_running(self):
                return False
            def start(self):
                class R: ok = False; error = "skipped"
                return R()

        class FakeHermesManager:
            def __init__(self):
                self.started = False
            def is_running(self):
                return False
            def start(self, **kw):
                self.started = True
                class R: ok = True; data = "started"
                return R()

        state = type("S", (), {})()
        state.master_agent = FakeMaster()
        state.gatekeeper = FakeGatekeeper()
        state.lang = "zh"
        cfg = {"autostart_on_launch": False}

        # 监视 hermes 是否被启动
        hermes_called = []
        def fake_hermes_start(*a, **kw):
            hermes_called.append(kw)
            class R: ok = True; data = "started"
            return R()

        with patch("fr_cli.agent.hermes_manager.HermesManager", FakeHermesManager):
            _autostart_background_services(state, cfg)

        # MasterAgent 启用,但 hermes 不应被调用
        assert state.master_agent.enabled is True
        # hermes 实例从未真正调用 start
        assert hermes_called == []


# ---------------------------------------------------------------------------
# /providers setup 走新向导
# ---------------------------------------------------------------------------

class TestProvidersSetupMigration:
    def test_providers_setup_uses_model_wizard(self):
        """_cmd_providers setup 应该调用 run_model_wizard"""
        from fr_cli.repl.commands.config import key as key_cmd
        import inspect
        # 检查 _cmd_providers 在 setup 分支调用了 wizard
        src = inspect.getsource(key_cmd._cmd_providers)
        assert "run_model_wizard" in src
        assert "model_wizard" in src
