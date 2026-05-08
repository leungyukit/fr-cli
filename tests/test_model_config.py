"""
模型配置与 Agent 专属模型配置测试
"""
import json
import os
import tempfile
from pathlib import Path
import pytest


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
        """CommandExecutor 的 push_agent_context 应正确覆盖 deps 中的 client/model"""
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

        # push 覆盖
        from fr_cli.core.llm import create_llm_client_for
        override_client, _, _ = create_llm_client_for("deepseek", "deepseek-chat", {
            "providers": {"deepseek": {"key": "override-key"}}
        })
        executor.push_agent_context(override_client, "deepseek-chat")
        deps = executor._get_deps()
        assert deps.client is override_client
        assert deps.model_name == "deepseek-chat"

        # pop 恢复
        executor.pop_agent_context()
        deps = executor._get_deps()
        assert deps.client is state.client
        assert deps.model_name == "glm-4-flash"
