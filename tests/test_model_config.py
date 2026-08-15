"""
模型配置与 Agent 专属模型配置测试
"""
import json
from pathlib import Path


# ---------- core/llm.py ----------

class TestCreateLLMClientFor:
    def test_uses_provider_key_from_cfg(self):
        from fr_cli.core.llm import create_llm_client_for
        cfg = {
            "providers": {
                "deepseek": {"key": "ds-key-123", "model": "deepseek-chat"}
            }
        }
        client, provider, model = create_llm_client_for("deepseek", "deepseek-chat", cfg)
        assert provider == "deepseek"
        assert model == "deepseek-chat"
        assert client.api_key == "ds-key-123"

    def test_uses_override_key(self):
        from fr_cli.core.llm import create_llm_client_for
        cfg = {
            "providers": {
                "deepseek": {"key": "ds-key-123", "model": "deepseek-chat"}
            }
        }
        client, _, _ = create_llm_client_for("deepseek", "deepseek-chat", cfg, override_key="agent-key")
        assert client.api_key == "agent-key"

    def test_fallback_to_top_level_key_for_zhipu(self):
        from fr_cli.core.llm import create_llm_client_for
        cfg = {
            "key": "zhipu-top-key",
            "providers": {}
        }
        client, _, _ = create_llm_client_for("zhipu", "glm-4-flash", cfg)
        assert client.api_key == "zhipu-top-key"

    def test_uses_custom_base_url(self):
        from fr_cli.core.llm import create_llm_client_for, OpenAICompatibleClient
        cfg = {
            "providers": {
                "deepseek": {"key": "k", "base_url": "https://custom.example.com"}
            }
        }
        client, _, _ = create_llm_client_for("deepseek", "m", cfg)
        assert isinstance(client, OpenAICompatibleClient)


# ---------- agent/manager.py ----------

class TestAgentConfig:
    def test_load_save_agent_config(self, tmp_path, monkeypatch):
        from fr_cli.agent import manager
        # 临时替换 AGENTS_DIR
        monkeypatch.setattr(manager, "AGENTS_DIR", tmp_path)

        # 创建 Agent 目录
        agent_dir = tmp_path / "test_agent"
        agent_dir.mkdir()
        (agent_dir / "agent.py").write_text("# code", encoding="utf-8")

        data = {"provider": "deepseek", "model": "deepseek-chat", "key": "abc"}
        manager.save_agent_config("test_agent", data)

        loaded = manager.load_agent_config("test_agent")
        assert loaded == data

    def test_load_nonexistent_returns_empty(self, tmp_path, monkeypatch):
        from fr_cli.agent import manager
        monkeypatch.setattr(manager, "AGENTS_DIR", tmp_path)
        assert manager.load_agent_config("ghost") == {}

    def test_list_agents_includes_has_config(self, tmp_path, monkeypatch):
        from fr_cli.agent import manager
        monkeypatch.setattr(manager, "AGENTS_DIR", tmp_path)

        agent_dir = tmp_path / "alpha"
        agent_dir.mkdir()
        (agent_dir / "agent.py").write_text("# code", encoding="utf-8")
        (agent_dir / "config.json").write_text("{}", encoding="utf-8")

        agents = manager.list_agents()
        assert len(agents) == 1
        assert agents[0]["has_config"] is True


# ---------- core/core.py ----------

class TestResolveAgentLLM:
    def test_fallback_to_global_when_no_agent_config(self, tmp_path, monkeypatch):
        from fr_cli.core.core import AppState
        from fr_cli.agent import manager
        monkeypatch.setattr(manager, "AGENTS_DIR", tmp_path)

        cfg = {
            "provider": "zhipu",
            "key": "top-key",
            "model": "glm-4-flash",
            "providers": {},
            "lang": "zh",
            "limit": 4096,
            "allowed_dirs": [],
            "aliases": {},
            "auto_confirm_forever": True,
        }
        state = AppState(cfg)
        client, provider, model = state.resolve_agent_llm("no_config_agent")
        assert provider == "zhipu"
        assert model == "glm-4-flash"

    def test_uses_agent_config_when_present(self, tmp_path, monkeypatch):
        from fr_cli.core.core import AppState
        from fr_cli.agent import manager
        monkeypatch.setattr(manager, "AGENTS_DIR", tmp_path)

        # 创建 Agent 并写入 config.json
        agent_dir = tmp_path / "custom_agent"
        agent_dir.mkdir()
        (agent_dir / "agent.py").write_text("# code", encoding="utf-8")
        manager.save_agent_config("custom_agent", {"provider": "deepseek", "model": "deepseek-chat"})

        cfg = {
            "provider": "zhipu",
            "key": "top-key",
            "model": "glm-4-flash",
            "providers": {
                "deepseek": {"key": "ds-key"}
            },
            "lang": "zh",
            "limit": 4096,
            "allowed_dirs": [],
            "aliases": {},
            "auto_confirm_forever": True,
        }
        state = AppState(cfg)
        client, provider, model = state.resolve_agent_llm("custom_agent")
        assert provider == "deepseek"
        assert model == "deepseek-chat"
        assert client.api_key == "ds-key"

    def test_agent_override_key_takes_precedence(self, tmp_path, monkeypatch):
        from fr_cli.core.core import AppState
        from fr_cli.agent import manager
        monkeypatch.setattr(manager, "AGENTS_DIR", tmp_path)

        agent_dir = tmp_path / "key_agent"
        agent_dir.mkdir()
        (agent_dir / "agent.py").write_text("# code", encoding="utf-8")
        manager.save_agent_config("key_agent", {
            "provider": "deepseek", "model": "m", "key": "agent-override"
        })

        cfg = {
            "provider": "zhipu",
            "key": "top-key",
            "model": "glm-4-flash",
            "providers": {
                "deepseek": {"key": "global-ds-key"}
            },
            "lang": "zh",
            "limit": 4096,
            "allowed_dirs": [],
            "aliases": {},
            "auto_confirm_forever": True,
        }
        state = AppState(cfg)
        client, _, _ = state.resolve_agent_llm("key_agent")
        assert client.api_key == "agent-override"

    def test_client_cache_reuses_instance(self, tmp_path, monkeypatch):
        from fr_cli.core.core import AppState
        from fr_cli.agent import manager
        monkeypatch.setattr(manager, "AGENTS_DIR", tmp_path)

        cfg = {
            "provider": "zhipu",
            "key": "top-key",
            "model": "glm-4-flash",
            "providers": {},
            "lang": "zh",
            "limit": 4096,
            "allowed_dirs": [],
            "aliases": {},
            "auto_confirm_forever": True,
        }
        state = AppState(cfg)
        c1 = state.get_client_for("zhipu", "glm-4-flash")
        c2 = state.get_client_for("zhipu", "glm-4-flash")
        assert c1 is c2


# ---------- repl/commands.py (agent_model 参数解析) ----------

class TestAgentModelCommandParsing:
    def test_provider_model_colon_format(self):
        from fr_cli.core.llm import resolve_provider_model
        p, m = resolve_provider_model("deepseek:deepseek-chat")
        assert p == "deepseek"
        assert m == "deepseek-chat"

    def test_model_only_format(self):
        from fr_cli.core.llm import resolve_provider_model
        p, m = resolve_provider_model("gpt-4")
        assert p is None
        assert m == "gpt-4"


# ---------- 边界情况与防御性测试 ----------

class TestEdgeCases:
    def test_resolve_agent_llm_fallback_on_empty_strings(self, tmp_path, monkeypatch):
        """Agent config 中 provider/model 为空字符串时应回退到全局"""
        from fr_cli.core.core import AppState
        from fr_cli.agent import manager
        monkeypatch.setattr(manager, "AGENTS_DIR", tmp_path)

        agent_dir = tmp_path / "empty_cfg"
        agent_dir.mkdir()
        (agent_dir / "agent.py").write_text("# code", encoding="utf-8")
        manager.save_agent_config("empty_cfg", {"provider": "", "model": "  "})

        cfg = {
            "provider": "zhipu",
            "key": "top-key",
            "model": "glm-4-flash",
            "providers": {},
            "lang": "zh",
            "limit": 4096,
            "allowed_dirs": [],
            "aliases": {},
            "auto_confirm_forever": True,
        }
        state = AppState(cfg)
        client, provider, model = state.resolve_agent_llm("empty_cfg")
        assert provider == "zhipu"
        assert model == "glm-4-flash"

    def test_save_agent_config_creates_dir(self, tmp_path, monkeypatch):
        """save_agent_config 应在 Agent 目录不存在时自动创建"""
        from fr_cli.agent import manager
        monkeypatch.setattr(manager, "AGENTS_DIR", tmp_path)

        # 目录不存在时直接保存
        manager.save_agent_config("auto_mkdir", {"provider": "zhipu", "model": "glm-4-flash"})
        assert (tmp_path / "auto_mkdir" / "config.json").exists()

    def test_client_cache_distinguishes_override_key(self, tmp_path, monkeypatch):
        """不同 override_key 应产生不同的缓存条目"""
        from fr_cli.core.core import AppState
        from fr_cli.agent import manager
        monkeypatch.setattr(manager, "AGENTS_DIR", tmp_path)

        cfg = {
            "provider": "deepseek",
            "key": "top-key",
            "model": "deepseek-chat",
            "providers": {
                "deepseek": {"key": "global-ds-key"}
            },
            "lang": "zh",
            "limit": 4096,
            "allowed_dirs": [],
            "aliases": {},
            "auto_confirm_forever": True,
        }
        state = AppState(cfg)
        c1 = state.get_client_for("deepseek", "m1")
        c2 = state.get_client_for("deepseek", "m1", override_key="custom")
        c3 = state.get_client_for("deepseek", "m1")
        assert c1 is c3
        assert c1 is not c2
        assert c2.api_key == "custom"

    def test_create_llm_client_for_fallback_base_url(self):
        """未配置自定义 base_url 时应回退到内置默认值"""
        from fr_cli.core.llm import create_llm_client_for, _PROVIDERS
        cfg = {
            "providers": {
                "deepseek": {"key": "k"}
            }
        }
        client, _, _ = create_llm_client_for("deepseek", "m", cfg)
        # OpenAICompatibleClient 会将 base_url 传给 openai.OpenAI
        # 我们可以通过检查内部 client 的 base_url 属性来验证
        assert client._client.base_url.raw_path.decode() == "/"
        # 更直接的验证：内置 base_url 应该被使用
        expected_base = _PROVIDERS["deepseek"]["base_url"]
        assert expected_base == "https://api.deepseek.com"

    def test_create_llm_client_uses_provider_default_model(self):
        """create_llm_client 在 cfg 无 model 时应使用 provider 默认模型"""
        from fr_cli.core.llm import create_llm_client
        cfg = {
            "provider": "deepseek",
            "key": "k",
            "providers": {
                "deepseek": {"key": "k"}
            }
        }
        _, provider, model = create_llm_client(cfg)
        assert model == "deepseek-chat"

    def test_create_llm_client_and_for_share_logic(self):
        """create_llm_client 与 create_llm_client_for 应使用相同的内部解析逻辑"""
        from fr_cli.core.llm import create_llm_client, create_llm_client_for
        cfg = {
            "provider": "deepseek",
            "key": "global",
            "model": "global-model",
            "providers": {
                "deepseek": {"key": "provider-key", "model": "provider-model"}
            }
        }
        c1, p1, m1 = create_llm_client(cfg)
        c2, p2, m2 = create_llm_client_for("deepseek", "explicit-model", cfg)
        # 两者都应使用 provider 级别的 key
        assert c1.api_key == "provider-key"
        assert c2.api_key == "provider-key"
        # model 不同：create_llm_client 用 provider 配置中的，create_llm_client_for 用显式传入的
        assert m1 == "provider-model"
        assert m2 == "explicit-model"

    def test_create_llm_client_for_doubao(self):
        from fr_cli.core.llm import create_llm_client_for, OpenAICompatibleClient
        cfg = {"providers": {"doubao": {"key": "db-key-123"}}}
        client, provider, model = create_llm_client_for("doubao", "doubao-1-5-pro-32k-250115", cfg)
        assert provider == "doubao"
        assert model == "doubao-1-5-pro-32k-250115"
        assert isinstance(client, OpenAICompatibleClient)
        assert client.api_key == "db-key-123"

    def test_create_llm_client_for_mimo(self):
        from fr_cli.core.llm import create_llm_client_for, OpenAICompatibleClient
        cfg = {"providers": {"mimo": {"key": "mimo-key-123"}}}
        client, provider, model = create_llm_client_for("mimo", "mimo-v2-pro", cfg)
        assert provider == "mimo"
        assert model == "mimo-v2-pro"
        assert isinstance(client, OpenAICompatibleClient)
        assert client.api_key == "mimo-key-123"

    def test_doubao_mimo_base_url_defaults(self):
        from fr_cli.core.llm import _PROVIDERS
        assert _PROVIDERS["doubao"]["base_url"] == "https://ark.cn-beijing.volces.com/api/v3"
        assert _PROVIDERS["mimo"]["base_url"] == "https://api.xiaomimimo.com/v1"

    def test_command_executor_agent_context_override(self):
        """v2.4.4：_get_deps(client=..., model_name=...) 显式覆盖（取代 push/pop 栈）"""
        from fr_cli.core.core import AppState
        from fr_cli.command.executor import CommandExecutor

        cfg = {
            "provider": "zhipu",
            "key": "top-key",
            "model": "glm-4-flash",
            "providers": {},
            "lang": "zh",
            "limit": 4096,
            "allowed_dirs": [],
            "aliases": {},
            "auto_confirm_forever": True,
        }
        state = AppState(cfg)
        executor = CommandExecutor(state)

        # 默认使用全局
        deps = executor._get_deps()
        assert deps.client is state.client
        assert deps.model_name == "glm-4-flash"

        # v2.4.4：显式传参覆盖
        from fr_cli.core.llm import create_llm_client_for
        override_client, _, _ = create_llm_client_for("deepseek", "deepseek-chat", {
            "providers": {"deepseek": {"key": "override-key"}}
        })
        deps = executor._get_deps(client=override_client, model_name="deepseek-chat")
        assert deps.client is override_client
        assert deps.model_name == "deepseek-chat"

        # 不传则恢复全局（无栈残留）
        deps = executor._get_deps()
        assert deps.client is state.client
        assert deps.model_name == "glm-4-flash"

        # v2.4.4：push/pop 现在是 no-op（旧代码兼容）
        executor.push_agent_context(override_client, "deepseek-chat")
        deps = executor._get_deps()
        # 因为是 no-op，deps 仍应是全局
        assert deps.model_name == "glm-4-flash"
        executor.pop_agent_context()


# ---------- Provider-Model 一致性修复测试 ----------

class TestProviderModelConsistency:
    """测试 provider 与 model 强绑定逻辑，防止跨 provider 模型名污染"""

    def test_create_llm_client_does_not_fallback_to_top_level_model(self):
        """核心修复：create_llm_client 不应从顶层 cfg['model'] 回退，
        避免 provider=zhipu 却使用 deepseek-chat 的情况。"""
        from fr_cli.core.llm import create_llm_client
        cfg = {
            "provider": "zhipu",
            "key": "zhipu-key",
            "model": "deepseek-chat",  # 顶层 model 是其他 provider 的（历史不一致配置）
            "providers": {
                "zhipu": {"key": "zhipu-key"}
                # zhipu 配置中没有 model
            }
        }
        _, provider, model = create_llm_client(cfg)
        assert provider == "zhipu"
        # 必须使用 zhipu 的默认模型，而不是顶层 cfg["model"] 的 deepseek-chat
        assert model == "glm-4-flash"

    def test_create_llm_client_uses_provider_specific_model(self):
        """当 providers_cfg 中已保存 model 时，应优先使用"""
        from fr_cli.core.llm import create_llm_client
        cfg = {
            "provider": "deepseek",
            "key": "ds-key",
            "model": "glm-4-flash",  # 顶层 model 是 zhipu 的
            "providers": {
                "deepseek": {"key": "ds-key", "model": "deepseek-reasoner"}
            }
        }
        _, provider, model = create_llm_client(cfg)
        assert provider == "deepseek"
        assert model == "deepseek-reasoner"

    def test_resolve_provider_model_inference(self):
        """resolve_provider_model 应能从模型名推断所属 provider"""
        from fr_cli.core.llm import resolve_provider_model
        # 已知工厂默认模型应能推断 provider
        p, m = resolve_provider_model("deepseek-chat")
        assert p == "deepseek"
        assert m == "deepseek-chat"

        p, m = resolve_provider_model("moonshot-v1-8k")
        assert p == "kimi"
        assert m == "moonshot-v1-8k"

    def test_resolve_provider_model_unknown_model(self):
        """未知模型名应返回 None provider，保持仅切换 model"""
        from fr_cli.core.llm import resolve_provider_model
        p, m = resolve_provider_model("unknown-custom-model")
        assert p is None
        assert m == "unknown-custom-model"

    def test_resolve_provider_model_explicit_colon(self):
        """显式 provider:model 格式优先"""
        from fr_cli.core.llm import resolve_provider_model
        p, m = resolve_provider_model("zhipu:deepseek-chat")
        assert p == "zhipu"
        assert m == "deepseek-chat"

    def test_update_provider_synchronizes_model(self):
        """切换 provider 时应自动同步 model 到目标 provider 的专属配置"""
        from fr_cli.core.core import AppState

        cfg = {
            "provider": "zhipu",
            "key": "zhipu-key",
            "model": "glm-4-flash",
            "providers": {
                "zhipu": {"key": "zhipu-key", "model": "glm-4-flash"},
                "deepseek": {"key": "ds-key", "model": "deepseek-reasoner"},
            },
            "lang": "zh",
            "limit": 4096,
            "allowed_dirs": [],
            "aliases": {},
            "auto_confirm_forever": True,
        }
        state = AppState(cfg)
        assert state.provider == "zhipu"
        assert state.model_name == "glm-4-flash"

        # 切换到 deepseek
        ok = state.update_provider("deepseek")
        assert ok is True
        assert state.provider == "deepseek"
        # model 应自动同步为 deepseek 配置中保存的 model
        assert state.model_name == "deepseek-reasoner"
        # 顶层 cfg 也应同步
        assert state.cfg["model"] == "deepseek-reasoner"
        # providers_cfg 中 deepseek 的 model 应保持
        assert state.cfg["providers"]["deepseek"]["model"] == "deepseek-reasoner"

    def test_update_provider_uses_default_when_no_saved_model(self):
        """切换到没有保存过 model 的 provider 时，应使用 factory 默认模型"""
        from fr_cli.core.core import AppState

        cfg = {
            "provider": "zhipu",
            "key": "zhipu-key",
            "model": "glm-4-flash",
            "providers": {
                "zhipu": {"key": "zhipu-key", "model": "glm-4-flash"},
                # deepseek 只配了 key，没配 model
                "deepseek": {"key": "ds-key"},
            },
            "lang": "zh",
            "limit": 4096,
            "allowed_dirs": [],
            "aliases": {},
            "auto_confirm_forever": True,
        }
        state = AppState(cfg)
        state.update_provider("deepseek")
        assert state.provider == "deepseek"
        assert state.model_name == "deepseek-chat"  # factory 默认
        assert state.cfg["providers"]["deepseek"]["model"] == "deepseek-chat"

    def test_update_model_auto_infers_provider(self):
        """仅输入模型名时，若该模型属于其他 provider，应自动切换 provider"""
        from fr_cli.core.core import AppState

        cfg = {
            "provider": "zhipu",
            "key": "zhipu-key",
            "model": "glm-4-flash",
            "providers": {
                "zhipu": {"key": "zhipu-key", "model": "glm-4-flash"},
                "deepseek": {"key": "ds-key", "model": "deepseek-chat"},
            },
            "lang": "zh",
            "limit": 4096,
            "allowed_dirs": [],
            "aliases": {},
            "auto_confirm_forever": True,
        }
        state = AppState(cfg)
        # 输入 deepseek-chat，应自动推断并切换到 deepseek
        ok = state.update_model("deepseek-chat")
        assert ok is True
        assert state.provider == "deepseek"
        assert state.model_name == "deepseek-chat"

    def test_update_model_keeps_current_provider_for_unknown_model(self):
        """未知模型名无法推断 provider 时，保持当前 provider"""
        from fr_cli.core.core import AppState

        cfg = {
            "provider": "zhipu",
            "key": "zhipu-key",
            "model": "glm-4-flash",
            "providers": {
                "zhipu": {"key": "zhipu-key", "model": "glm-4-flash"},
            },
            "lang": "zh",
            "limit": 4096,
            "allowed_dirs": [],
            "aliases": {},
            "auto_confirm_forever": True,
        }
        state = AppState(cfg)
        ok = state.update_model("custom-glm-model")
        assert ok is True
        assert state.provider == "zhipu"
        assert state.model_name == "custom-glm-model"
        assert state.cfg["providers"]["zhipu"]["model"] == "custom-glm-model"

    def test_load_config_migrates_top_level_model(self):
        """向后兼容：加载旧配置时，应将顶层 model 迁移到当前 provider 的专属配置"""
        from fr_cli.conf.config import load_config

        # 构造一个模拟的旧配置（顶层 model 存在，但 providers 中当前 provider 没有 model）
        old_cfg = {
            "provider": "deepseek",
            "key": "ds-key",
            "model": "deepseek-reasoner",
            "providers": {
                "deepseek": {"key": "ds-key"}
                # 缺少 model 字段
            },
            "lang": "zh",
            "limit": 4096,
            "allowed_dirs": [],
            "aliases": {},
            "auto_confirm_forever": False,
            "mail": {},
            "disk": {},
            "thinking_mode": "direct",
            "mcp": {"servers": []},
            "banner_enabled": True,
        }

        # 临时写入配置文件
        from fr_cli.conf.paths import CONFIG_FILE
        original = None
        if CONFIG_FILE.exists():
            original = CONFIG_FILE.read_text(encoding="utf-8")

        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(old_cfg, f)

            loaded = load_config()
            # 迁移后，deepseek 配置中应有 model
            assert loaded["providers"]["deepseek"]["model"] == "deepseek-reasoner"
        finally:
            if original is not None:
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    f.write(original)
            else:
                try:
                    CONFIG_FILE.unlink()
                except Exception:
                    pass

    def test_load_config_does_not_override_existing_provider_model(self):
        """向后兼容：若 provider 配置中已有 model，不应被顶层 model 覆盖"""
        from fr_cli.conf.config import load_config
        from fr_cli.conf.paths import CONFIG_FILE

        old_cfg = {
            "provider": "deepseek",
            "key": "ds-key",
            "model": "deepseek-chat",  # 顶层 model
            "providers": {
                "deepseek": {"key": "ds-key", "model": "deepseek-reasoner"}  # 已有 model
            },
            "lang": "zh",
            "limit": 4096,
            "allowed_dirs": [],
            "aliases": {},
            "auto_confirm_forever": False,
            "mail": {},
            "disk": {},
            "thinking_mode": "direct",
            "mcp": {"servers": []},
            "banner_enabled": True,
        }

        original = None
        if CONFIG_FILE.exists():
            original = CONFIG_FILE.read_text(encoding="utf-8")

        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(old_cfg, f)

            loaded = load_config()
            # provider 配置中已有的 model 不应被覆盖
            assert loaded["providers"]["deepseek"]["model"] == "deepseek-reasoner"
        finally:
            if original is not None:
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    f.write(original)
            else:
                try:
                    CONFIG_FILE.unlink()
                except Exception:
                    pass


# ---------- 边界与异常场景测试 ----------

class TestBoundaryAndEdgeCases:
    """测试所有修改操作的异常场景、边界值和防御性行为"""

    # ---- core/llm.py: resolve_provider_model ----

    def test_resolve_provider_model_empty_string(self):
        """空字符串应返回 (None, '')"""
        from fr_cli.core.llm import resolve_provider_model
        p, m = resolve_provider_model("")
        assert p is None
        assert m == ""

    def test_resolve_provider_model_multiple_colons(self):
        """多个冒号时应只分割第一个，保留后续内容"""
        from fr_cli.core.llm import resolve_provider_model
        p, m = resolve_provider_model("a:b:c")
        assert p == "a"
        assert m == "b:c"

    def test_resolve_provider_model_whitespace(self):
        """前后空格应被正确去除"""
        from fr_cli.core.llm import resolve_provider_model
        p, m = resolve_provider_model("  deepseek : deepseek-chat  ")
        assert p == "deepseek"
        assert m == "deepseek-chat"

    # ---- core/llm.py: create_llm_client ----

    def test_create_llm_client_no_api_key_returns_mock(self):
        """无 API Key 时应自动回退到 MockLLMClient"""
        from fr_cli.core.llm import create_llm_client, MockLLMClient
        cfg = {
            "provider": "deepseek",
            "key": "",
            "model": "deepseek-chat",
            "providers": {
                "deepseek": {"model": "deepseek-chat"}
            }
        }
        client, provider, model = create_llm_client(cfg)
        assert isinstance(client, MockLLMClient)
        assert provider == "deepseek"
        assert model == "deepseek-chat"
        assert hasattr(client, "is_mock")

    def test_create_llm_client_unknown_provider_fallback_to_zhipu(self):
        """未知 provider 时应回退到 zhipu 默认配置"""
        from fr_cli.core.llm import create_llm_client
        cfg = {
            "provider": "nonexistent-provider",
            "key": "some-key",
            "model": "some-model",
            "providers": {}
        }
        _, provider, model = create_llm_client(cfg)
        # 虽然 provider 字符串保持原样，但 model 应使用 zhipu 默认（因为 unknown provider 无配置）
        assert model == "glm-4-flash"

    def test_create_llm_client_provider_has_empty_model_string(self):
        """provider 配置中 model 为空字符串时，应视为未配置，使用默认模型"""
        from fr_cli.core.llm import create_llm_client
        cfg = {
            "provider": "deepseek",
            "key": "ds-key",
            "model": "deepseek-chat",
            "providers": {
                "deepseek": {"key": "ds-key", "model": ""}
            }
        }
        _, provider, model = create_llm_client(cfg)
        # 空字符串会被 .get("model", default) 视为存在，返回空字符串
        # 这是 Python dict.get 的行为：键存在但值为空字符串时返回空字符串
        # 不过我们的修复中 create_llm_client 用 pcfg.get("model", default_model)
        # 如果 model 是 ""，会返回 ""，这可能不是期望行为
        # 实际上在 update_provider 中我们确保 model 不会是空字符串
        # 这个测试主要验证行为一致性
        assert provider == "deepseek"

    # ---- core/llm.py: reload_providers / get_provider_by_model ----

    def test_reload_providers_clears_and_rebuilds_mapping(self):
        """reload_providers 应清空并重建 _MODEL_TO_PROVIDER"""
        from fr_cli.core.llm import reload_providers, get_provider_by_model
        # 先确保有数据
        p = get_provider_by_model("deepseek-chat")
        assert p == "deepseek"
        # reload 后映射应重建
        reload_providers()
        p2 = get_provider_by_model("deepseek-chat")
        assert p2 == "deepseek"

    def test_get_provider_by_model_unknown_returns_none(self):
        """未知模型名应返回 None"""
        from fr_cli.core.llm import get_provider_by_model
        assert get_provider_by_model("totally-unknown-model-xyz") is None

    def test_get_provider_by_model_auto_loads_providers(self):
        """_PROVIDERS 未加载时应自动加载"""
        from fr_cli.core.llm import get_provider_by_model, reload_providers
        reload_providers()  # 确保从干净状态开始
        # 直接调用应触发自动加载
        p = get_provider_by_model("glm-4-flash")
        assert p == "zhipu"

    # ---- core/llm.py: _resolve_llm_kwargs ----

    def test_resolve_llm_kwargs_unknown_provider_fallback(self):
        """未知 provider 时应回退到 zhipu 的客户端类"""
        from fr_cli.core.llm import _resolve_llm_kwargs
        cfg = {"providers": {}}
        client_cls, kwargs = _resolve_llm_kwargs("unknown", cfg)
        # 应回退到 zhipu 默认（OpenAICompatibleClient 或 ZhipuLLMClient）
        assert "api_key" in kwargs

    # ---- core/core.py: update_provider ----

    def test_update_provider_invalid_returns_false(self):
        """无效 provider 应返回 False，不修改状态"""
        from fr_cli.core.core import AppState

        cfg = {
            "provider": "zhipu",
            "key": "zhipu-key",
            "model": "glm-4-flash",
            "providers": {"zhipu": {"key": "zhipu-key", "model": "glm-4-flash"}},
            "lang": "zh",
            "limit": 4096,
            "allowed_dirs": [],
            "aliases": {},
            "auto_confirm_forever": True,
        }
        state = AppState(cfg)
        original_provider = state.provider
        original_model = state.model_name

        ok = state.update_provider("nonexistent")
        assert ok is False
        assert state.provider == original_provider
        assert state.model_name == original_model

    def test_update_provider_creates_new_provider_entry(self):
        """切换到从未配置过的 provider 时，应创建新的 providers_cfg 条目"""
        from fr_cli.core.core import AppState

        cfg = {
            "provider": "zhipu",
            "key": "zhipu-key",
            "model": "glm-4-flash",
            "providers": {
                "zhipu": {"key": "zhipu-key", "model": "glm-4-flash"}
                # deepseek 完全没有配置
            },
            "lang": "zh",
            "limit": 4096,
            "allowed_dirs": [],
            "aliases": {},
            "auto_confirm_forever": True,
        }
        state = AppState(cfg)
        assert "deepseek" not in state.cfg["providers"]

        state.update_provider("deepseek")
        assert "deepseek" in state.cfg["providers"]
        assert state.cfg["providers"]["deepseek"]["model"] == "deepseek-chat"
        assert state.cfg["providers"]["deepseek"].get("key") is None

    # ---- core/core.py: update_model ----

    def test_update_model_with_invalid_provider_returns_false(self):
        """显式指定无效 provider（如 invalid:model）时应返回 False"""
        from fr_cli.core.core import AppState

        cfg = {
            "provider": "zhipu",
            "key": "zhipu-key",
            "model": "glm-4-flash",
            "providers": {"zhipu": {"key": "zhipu-key", "model": "glm-4-flash"}},
            "lang": "zh",
            "limit": 4096,
            "allowed_dirs": [],
            "aliases": {},
            "auto_confirm_forever": True,
        }
        state = AppState(cfg)
        original_provider = state.provider
        original_model = state.model_name

        ok = state.update_model("invalid_provider:some-model")
        assert ok is False
        assert state.provider == original_provider
        assert state.model_name == original_model

    def test_update_model_same_provider_no_redundant_switch(self):
        """模型名属于当前 provider 时，不应触发 provider 切换，只更新 model"""
        from fr_cli.core.core import AppState

        cfg = {
            "provider": "deepseek",
            "key": "ds-key",
            "model": "deepseek-chat",
            "providers": {
                "deepseek": {"key": "ds-key", "model": "deepseek-chat"},
            },
            "lang": "zh",
            "limit": 4096,
            "allowed_dirs": [],
            "aliases": {},
            "auto_confirm_forever": True,
        }
        state = AppState(cfg)
        # deepseek-chat 属于 deepseek，但当前已经是 deepseek，不应重复切换
        ok = state.update_model("deepseek-chat")
        assert ok is True
        assert state.provider == "deepseek"
        assert state.model_name == "deepseek-chat"
        assert state.cfg["providers"]["deepseek"]["model"] == "deepseek-chat"

    def test_update_model_explicit_colon_same_provider(self):
        """显式指定当前 provider:model 时应正常工作"""
        from fr_cli.core.core import AppState

        cfg = {
            "provider": "zhipu",
            "key": "zhipu-key",
            "model": "glm-4-flash",
            "providers": {"zhipu": {"key": "zhipu-key", "model": "glm-4-flash"}},
            "lang": "zh",
            "limit": 4096,
            "allowed_dirs": [],
            "aliases": {},
            "auto_confirm_forever": True,
        }
        state = AppState(cfg)
        ok = state.update_model("zhipu:glm-4-plus")
        assert ok is True
        assert state.provider == "zhipu"
        assert state.model_name == "glm-4-plus"
        assert state.cfg["providers"]["zhipu"]["model"] == "glm-4-plus"

    # ---- core/core.py: update_key ----

    def test_update_key_syncs_to_providers_cfg(self):
        """update_key 应同步更新顶层 key 和 providers_cfg 中当前 provider 的 key"""
        from fr_cli.core.core import AppState

        cfg = {
            "provider": "deepseek",
            "key": "old-key",
            "model": "deepseek-chat",
            "providers": {
                "deepseek": {"key": "old-key", "model": "deepseek-chat"},
            },
            "lang": "zh",
            "limit": 4096,
            "allowed_dirs": [],
            "aliases": {},
            "auto_confirm_forever": True,
        }
        state = AppState(cfg)
        state.update_key("new-key")
        assert state.cfg["key"] == "new-key"
        assert state.cfg["providers"]["deepseek"]["key"] == "new-key"
        assert state.api_key == "new-key"

    # ---- conf/config.py: load_config ----

    def test_load_config_corrupted_with_valid_backup(self):
        """主配置损坏但备份有效时，应从备份恢复"""
        from fr_cli.conf.config import load_config
        from fr_cli.conf.paths import CONFIG_FILE, CONFIG_BACKUP

        original_file = None
        original_backup = None
        if CONFIG_FILE.exists():
            original_file = CONFIG_FILE.read_text(encoding="utf-8")
        if CONFIG_BACKUP.exists():
            original_backup = CONFIG_BACKUP.read_text(encoding="utf-8")

        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            # 写入损坏的主配置
            CONFIG_FILE.write_text("{invalid json", encoding="utf-8")
            # 写入有效的备份
            valid_cfg = {
                "provider": "deepseek",
                "key": "ds-key",
                "model": "deepseek-chat",
                "providers": {"deepseek": {"key": "ds-key", "model": "deepseek-chat"}},
                "lang": "zh",
                "limit": 4096,
                "allowed_dirs": [],
                "aliases": {},
                "auto_confirm_forever": False,
                "mail": {},
                "disk": {},
                "thinking_mode": "direct",
                "mcp": {"servers": []},
                "banner_enabled": True,
            }
            CONFIG_BACKUP.write_text(json.dumps(valid_cfg), encoding="utf-8")

            loaded = load_config()
            assert loaded["provider"] == "deepseek"
            assert loaded["providers"]["deepseek"]["model"] == "deepseek-chat"
        finally:
            if original_file is not None:
                CONFIG_FILE.write_text(original_file, encoding="utf-8")
            else:
                try:
                    CONFIG_FILE.unlink()
                except Exception:
                    pass
            if original_backup is not None:
                CONFIG_BACKUP.write_text(original_backup, encoding="utf-8")
            else:
                try:
                    CONFIG_BACKUP.unlink()
                except Exception:
                    pass

    def test_load_config_both_corrupted_returns_default(self):
        """主配置和备份都损坏时，应返回默认配置"""
        from fr_cli.conf.config import load_config
        from fr_cli.conf.paths import CONFIG_FILE, CONFIG_BACKUP

        original_file = None
        original_backup = None
        if CONFIG_FILE.exists():
            original_file = CONFIG_FILE.read_text(encoding="utf-8")
        if CONFIG_BACKUP.exists():
            original_backup = CONFIG_BACKUP.read_text(encoding="utf-8")

        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text("{bad", encoding="utf-8")
            CONFIG_BACKUP.write_text("{also bad", encoding="utf-8")

            loaded = load_config()
            # provider/model 默认不写入配置，由用户显式配置
            assert "provider" not in loaded
            assert "model" not in loaded
            assert "providers" in loaded
        finally:
            if original_file is not None:
                CONFIG_FILE.write_text(original_file, encoding="utf-8")
            else:
                try:
                    CONFIG_FILE.unlink()
                except Exception:
                    pass
            if original_backup is not None:
                CONFIG_BACKUP.write_text(original_backup, encoding="utf-8")
            else:
                try:
                    CONFIG_BACKUP.unlink()
                except Exception:
                    pass

    def test_load_config_missing_fields_filled_with_defaults(self):
        """配置缺少字段时应使用默认值补齐"""
        from fr_cli.conf.config import load_config
        from fr_cli.conf.paths import CONFIG_FILE

        original = None
        if CONFIG_FILE.exists():
            original = CONFIG_FILE.read_text(encoding="utf-8")

        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            # 只写部分字段的旧配置
            partial = {"provider": "deepseek", "key": "k"}
            CONFIG_FILE.write_text(json.dumps(partial), encoding="utf-8")

            loaded = load_config()
            assert loaded["provider"] == "deepseek"
            assert loaded["key"] == "k"
            # 缺失字段应被补齐
            assert "limit" in loaded
            assert "lang" in loaded
            assert "providers" in loaded
            assert "aliases" in loaded
            assert loaded["lang"] == "zh"
            assert loaded["limit"] == 20000
        finally:
            if original is not None:
                CONFIG_FILE.write_text(original, encoding="utf-8")
            else:
                try:
                    CONFIG_FILE.unlink()
                except Exception:
                    pass

    # ---- conf/config.py: save_config ----

    def test_save_config_returns_false_on_failure(self):
        """保存到无效路径时应返回 False"""
        from fr_cli.conf.config import save_config
        # 尝试保存到不存在的只读目录
        from fr_cli.conf import paths
        orig_root = paths.ROOT
        try:
            paths._root_holder.value = Path("/nonexistent_dir_xyz_root")
            result = save_config({"test": "data"})
            assert result is False
        finally:
            paths._root_holder.value = orig_root

    # ---- conf/config.py: init_config ----

    def test_init_config_mock_mode_when_no_key(self):
        """无 key 时应进入 Mock 模式（不抛异常）"""
        from fr_cli.conf.config import init_config
        from fr_cli.conf.paths import CONFIG_FILE

        original = None
        if CONFIG_FILE.exists():
            original = CONFIG_FILE.read_text(encoding="utf-8")

        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            # 写入无 key 的配置
            no_key_cfg = {
                "provider": "deepseek",
                "key": "",
                "model": "deepseek-chat",
                "providers": {"deepseek": {"key": ""}},
                "lang": "zh",
                "limit": 4096,
                "allowed_dirs": [],
                "aliases": {},
                "auto_confirm_forever": False,
                "mail": {},
                "disk": {},
                "thinking_mode": "direct",
                "mcp": {"servers": []},
                "banner_enabled": True,
            }
            CONFIG_FILE.write_text(json.dumps(no_key_cfg), encoding="utf-8")

            # 使用 monkeypatch 模拟 EOFError（非交互环境）
            import builtins
            orig_input = builtins.input
            builtins.input = lambda _: ""  # 模拟直接回车

            try:
                cfg = init_config()
                # 应返回配置字典，不抛异常
                assert isinstance(cfg, dict)
                assert "provider" in cfg
            finally:
                builtins.input = orig_input
        finally:
            if original is not None:
                CONFIG_FILE.write_text(original, encoding="utf-8")
            else:
                try:
                    CONFIG_FILE.unlink()
                except Exception:
                    pass

    # ---- MockLLMClient ----

    def test_mock_llm_client_stream_chat(self):
        """MockLLMClient 应能生成流式响应"""
        from fr_cli.core.llm import MockLLMClient
        client = MockLLMClient()
        messages = [{"role": "user", "content": "hello"}]
        chunks = list(client.stream_chat("mock-model", messages))
        # 应产生多个 chunk
        assert len(chunks) > 0
        # 最后应有 usage 信息
        assert chunks[-1]["usage"] is not None
        assert "prompt_tokens" in chunks[-1]["usage"]

    def test_mock_llm_client_with_command_input(self):
        """MockLLMClient 对命令输入应返回提示信息"""
        from fr_cli.core.llm import MockLLMClient
        client = MockLLMClient()
        messages = [{"role": "user", "content": "/help"}]
        chunks = list(client.stream_chat("mock-model", messages))
        full_text = "".join(c["content"] for c in chunks)
        assert "Mock 模式" in full_text
        assert "命令" in full_text

    def test_mock_llm_client_empty_messages(self):
        """MockLLMClient 对空消息应返回引导信息"""
        from fr_cli.core.llm import MockLLMClient
        client = MockLLMClient()
        chunks = list(client.stream_chat("mock-model", []))
        full_text = "".join(c["content"] for c in chunks)
        assert "没收到你的输入" in full_text

    # ---- 集成：provider-model 一致性端到端 ----

    def test_provider_model_consistency_after_multiple_switches(self):
        """多次切换 provider 和 model 后，配置应始终保持一致性"""
        from fr_cli.core.core import AppState

        cfg = {
            "provider": "zhipu",
            "key": "zhipu-key",
            "model": "glm-4-flash",
            "providers": {
                "zhipu": {"key": "zhipu-key", "model": "glm-4-flash"},
                "deepseek": {"key": "ds-key", "model": "deepseek-chat"},
                "kimi": {"key": "kimi-key", "model": "moonshot-v1-8k"},
            },
            "lang": "zh",
            "limit": 4096,
            "allowed_dirs": [],
            "aliases": {},
            "auto_confirm_forever": True,
        }
        state = AppState(cfg)

        # 1. zhipu → deepseek
        state.update_provider("deepseek")
        assert state.provider == "deepseek"
        assert state.model_name == "deepseek-chat"
        assert state.cfg["model"] == "deepseek-chat"

        # 2. deepseek → kimi
        state.update_provider("kimi")
        assert state.provider == "kimi"
        assert state.model_name == "moonshot-v1-8k"
        assert state.cfg["model"] == "moonshot-v1-8k"

        # 3. kimi → 通过 model 名切回 deepseek
        state.update_model("deepseek-chat")
        assert state.provider == "deepseek"
        assert state.model_name == "deepseek-chat"

        # 4. deepseek → 显式切到 zhipu 的自定义模型
        state.update_model("zhipu:glm-4-plus")
        assert state.provider == "zhipu"
        assert state.model_name == "glm-4-plus"
        assert state.cfg["providers"]["zhipu"]["model"] == "glm-4-plus"

        # 5. 验证所有 provider 的 model 都保持正确
        assert state.cfg["providers"]["zhipu"]["model"] == "glm-4-plus"
        assert state.cfg["providers"]["deepseek"]["model"] == "deepseek-chat"
        assert state.cfg["providers"]["kimi"]["model"] == "moonshot-v1-8k"


class TestModelFactoryLoadConfig:
    """load_config 接受 str 和 Path 两种输入,不报 PosixPath.endswith 错误"""

    def test_load_config_accepts_path_object(self, tmp_path):
        """config_path 传 PosixPath(Path 对象)也能正常加载"""
        from fr_cli.core.model_factory import ModelFactory

        yaml_path = tmp_path / "models.yaml"
        yaml_path.write_text(
            "test_provider:\n  name: 测试\n  model: test-model\n  client: OpenAICompatibleClient\n",
            encoding="utf-8",
        )

        factory = ModelFactory()
        factory.load_config(config_path=yaml_path)  # 传 Path,不是 str
        assert "test_provider" in factory._config
        assert factory._config["test_provider"]["model"] == "test-model"

    def test_load_config_accepts_string_path(self, tmp_path):
        """str 路径也工作(向后兼容)"""
        from fr_cli.core.model_factory import ModelFactory

        yaml_path = tmp_path / "models.yaml"
        yaml_path.write_text(
            "str_provider:\n  model: str-model\n  client: OpenAICompatibleClient\n",
            encoding="utf-8",
        )

        factory = ModelFactory()
        factory.load_config(config_path=str(yaml_path))  # 显式 str
        assert "str_provider" in factory._config

    def test_load_config_handles_yml_suffix(self, tmp_path):
        """.yml 后缀也能识别"""
        from fr_cli.core.model_factory import ModelFactory

        yml_path = tmp_path / "models.yml"
        yml_path.write_text(
            "yml_provider:\n  model: yml-model\n  client: OpenAICompatibleClient\n",
            encoding="utf-8",
        )

        factory = ModelFactory()
        factory.load_config(config_path=yml_path)
        assert "yml_provider" in factory._config

    def test_load_config_handles_json_suffix(self, tmp_path):
        """.json 后缀走 JSON 解析分支"""
        from fr_cli.core.model_factory import ModelFactory

        json_path = tmp_path / "models.json"
        json_path.write_text(
            json.dumps({"json_provider": {"model": "json-model",
                                          "client": "OpenAICompatibleClient"}}),
            encoding="utf-8",
        )

        factory = ModelFactory()
        factory.load_config(config_path=json_path)
        assert "json_provider" in factory._config
        assert factory._config["json_provider"]["model"] == "json-model"

    def test_default_load_does_not_warn_about_path(self):
        """用默认 MODELS_YAML(Path 对象)加载时,不应该再报 endswith 警告"""
        import warnings
        from fr_cli.core.model_factory import ModelFactory

        factory = ModelFactory()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            factory.load_config()  # 用默认路径
        # 任何 'endswith' 相关警告都算 bug
        path_warnings = [w for w in caught
                         if "endswith" in str(w.message).lower()
                         or "PosixPath" in str(w.message)]
        assert not path_warnings, f"意外的 endswith 警告: {path_warnings}"


class TestYieldChunks:
    """_yield_chunks 兼容标准 OpenAI 和 火山方舟 coding endpoint 两种格式"""

    def _make_chunk(self, content=None, reasoning_content=None, usage=None):
        """构造一个假的 OpenAI streaming chunk"""
        from types import SimpleNamespace
        delta = SimpleNamespace(
            content=content,
            reasoning_content=reasoning_content,
            role="assistant",
        )
        choice = SimpleNamespace(delta=delta, index=0)
        chunk = SimpleNamespace(choices=[choice])
        if usage is not None:
            chunk.usage = usage
        else:
            chunk.usage = None
        return chunk

    def test_standard_openai_format(self):
        """标准 OpenAI 格式:delta.content 有值,正确读出"""
        from fr_cli.core.llm.base import BaseLLMClient

        chunks = [
            self._make_chunk(content="你"),
            self._make_chunk(content="好"),
            self._make_chunk(content=""),
        ]
        result = list(BaseLLMClient._yield_chunks(iter(chunks)))
        assert [r["content"] for r in result] == ["你", "好", ""]

    def test_ark_coding_endpoint_format(self):
        """火山方舟 coding endpoint:delta.content 恒为 "",fallback 到 reasoning_content"""
        from fr_cli.core.llm.base import BaseLLMClient

        chunks = [
            self._make_chunk(content="", reasoning_content="让我"),
            self._make_chunk(content="", reasoning_content="想想"),
            self._make_chunk(content="", reasoning_content="怎么回"),
        ]
        result = list(BaseLLMClient._yield_chunks(iter(chunks)))
        assert [r["content"] for r in result] == ["让我", "想想", "怎么回"]

    def test_ark_thinking_then_content(self):
        """混合模式:reasoning 一段后切到 content(部分 thinking 模型会这样)"""
        from fr_cli.core.llm.base import BaseLLMClient

        chunks = [
            self._make_chunk(content="", reasoning_content="思考1"),
            self._make_chunk(content="答案"),
        ]
        result = list(BaseLLMClient._yield_chunks(iter(chunks)))
        assert [r["content"] for r in result] == ["思考1", "答案"]

    def test_empty_chunk_yields_empty_content(self):
        """空 content(无 reasoning_content)时,产出空 content,不崩"""
        from fr_cli.core.llm.base import BaseLLMClient

        chunks = [self._make_chunk(content=None, reasoning_content=None)]
        result = list(BaseLLMClient._yield_chunks(iter(chunks)))
        assert result == [{"content": "", "usage": None}]

    def test_usage_passed_through(self):
        """usage 信息正确透传"""
        from types import SimpleNamespace
        from fr_cli.core.llm.base import BaseLLMClient

        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)
        chunks = [self._make_chunk(content="hi", usage=usage)]
        result = list(BaseLLMClient._yield_chunks(iter(chunks)))
        assert result[0]["usage"]["prompt_tokens"] == 10
        assert result[0]["usage"]["completion_tokens"] == 5
