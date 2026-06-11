"""
新提供商支持测试 - MiniMax 和 Kimi-for-code

测试目标：
1. 验证新添加的 provider 配置正确
2. 验证可以创建对应的客户端
3. 验证配置解析正确
"""
import pytest
from fr_cli.core.llm import (
    _PROVIDERS,
    create_llm_client_for,
    list_providers,
    get_provider_info,
    resolve_provider_model
)


class TestMiniMaxProviders:
    """测试 MiniMax 相关 provider"""

    def test_minimax_provider_exists(self):
        """验证 minimax provider 存在"""
        assert "minimax" in _PROVIDERS
        info = _PROVIDERS["minimax"]
        assert info["name"] == "MiniMax"
        assert info["default_model"] == "MiniMax-Text-01"
        assert info["base_url"] == "https://api.minimax.io/v1"
        assert info["token_plan_base_url"] == "https://api.minimax.chat/v1"
        assert info["is_token_plan"] is False

    def test_minimax_chat_provider_exists(self):
        """验证 minimax-chat provider 存在"""
        assert "minimax-chat" in _PROVIDERS
        info = _PROVIDERS["minimax-chat"]
        assert info["name"] == "MiniMax Chat"
        assert info["default_model"] == "abab6.5s-chat"
        assert info["base_url"] == "https://api.minimax.io/v1"

    def test_create_minimax_client(self):
        """测试创建 MiniMax 客户端"""
        cfg = {
            "providers": {
                "minimax": {"key": "test-key"}
            }
        }
        client, provider, model = create_llm_client_for("minimax", "MiniMax-Text-01", cfg)
        assert provider == "minimax"
        assert model == "MiniMax-Text-01"
        assert client.api_key == "test-key"

    def test_create_minimax_chat_client(self):
        """测试创建 MiniMax Chat 客户端"""
        cfg = {
            "providers": {
                "minimax-chat": {"key": "test-key"}
            }
        }
        client, provider, model = create_llm_client_for("minimax-chat", "abab6.5s-chat", cfg)
        assert provider == "minimax-chat"
        assert model == "abab6.5s-chat"
        assert client.api_key == "test-key"

    def test_minimax_m27_provider_exists(self):
        """验证 minimax-m27 provider 存在 (M2.7 模型)"""
        assert "minimax-m27" in _PROVIDERS
        info = _PROVIDERS["minimax-m27"]
        assert info["name"] == "MiniMax M2.7 (Token Plan)"
        assert info["default_model"] == "MiniMax-M2.7"
        assert info["base_url"] == "https://api.minimax.chat/v1"
        assert info["is_token_plan"] is True

    def test_minimax_m27_fast_provider_exists(self):
        """验证 minimax-m27-fast provider 存在 (高速版)"""
        assert "minimax-m27-fast" in _PROVIDERS
        info = _PROVIDERS["minimax-m27-fast"]
        assert info["name"] == "MiniMax M2.7-HighSpeed (Token Plan)"
        assert info["default_model"] == "MiniMax-M2.7-HighSpeed"
        assert info["base_url"] == "https://api.minimax.chat/v1"
        assert info["is_token_plan"] is True

    def test_minimax_token_plan_provider_exists(self):
        """验证 minimax-token-plan provider 存在 (全模态)"""
        assert "minimax-token-plan" in _PROVIDERS
        info = _PROVIDERS["minimax-token-plan"]
        assert info["name"] == "MiniMax Token Plan (全模态)"
        assert info["default_model"] == "MiniMax-M2.7"
        assert info["base_url"] == "https://api.minimax.chat/v1"
        assert info["is_token_plan"] is True

    def test_create_minimax_m27_client(self):
        """测试创建 MiniMax M2.7 客户端"""
        cfg = {
            "providers": {
                "minimax-m27": {"key": "test-key"}
            }
        }
        client, provider, model = create_llm_client_for("minimax-m27", "MiniMax-M2.7", cfg)
        assert provider == "minimax-m27"
        assert model == "MiniMax-M2.7"
        assert client.api_key == "test-key"

    def test_create_minimax_m27_fast_client(self):
        """测试创建 MiniMax M2.7-HighSpeed 客户端"""
        cfg = {
            "providers": {
                "minimax-m27-fast": {"key": "test-key"}
            }
        }
        client, provider, model = create_llm_client_for("minimax-m27-fast", "MiniMax-M2.7-HighSpeed", cfg)
        assert provider == "minimax-m27-fast"
        assert model == "MiniMax-M2.7-HighSpeed"
        assert client.api_key == "test-key"


class TestOpenAIProvider:
    """测试 OpenAI 官方 provider"""

    def test_openai_provider_exists(self):
        """验证 openai provider 存在且配置正确"""
        assert "openai" in _PROVIDERS
        info = _PROVIDERS["openai"]
        assert info["name"] == "OpenAI"
        assert info["default_model"] == "gpt-4o-mini"
        assert info["base_url"] == "https://api.openai.com/v1"
        assert info["is_token_plan"] is False

    def test_create_openai_client(self):
        """测试创建 OpenAI 客户端"""
        cfg = {
            "providers": {
                "openai": {"key": "test-key"}
            }
        }
        client, provider, model = create_llm_client_for("openai", "gpt-4o-mini", cfg)
        assert provider == "openai"
        assert model == "gpt-4o-mini"
        assert client.api_key == "test-key"
        assert str(client._client.base_url).rstrip('/') == "https://api.openai.com/v1"

    def test_openai_custom_base_url(self):
        """测试 OpenAI provider 支持自定义兼容接口"""
        cfg = {
            "providers": {
                "openai": {
                    "key": "test-key",
                    "base_url": "https://my-openai-proxy.example.com/v1"
                }
            }
        }
        client, provider, model = create_llm_client_for("openai", "gpt-4o", cfg)
        assert provider == "openai"
        assert model == "gpt-4o"
        assert str(client._client.base_url).rstrip('/') == "https://my-openai-proxy.example.com/v1"


class TestKimiProviders:
    """测试 Kimi 相关 provider"""

    def test_kimi_k2_provider_exists(self):
        """验证 kimi-k2 provider 存在"""
        assert "kimi-k2" in _PROVIDERS
        info = _PROVIDERS["kimi-k2"]
        assert info["name"] == "Kimi K2 (代码优化版)"
        assert info["default_model"] == "kimi-k2-0905-preview"
        assert info["base_url"] == "https://api.moonshot.cn/v1"

    def test_kimi_code_provider_exists(self):
        """验证 kimi-code provider 存在"""
        assert "kimi-code" in _PROVIDERS
        info = _PROVIDERS["kimi-code"]
        assert info["name"] == "Kimi Code (代码平台)"
        assert info["default_model"] == "kimi-for-coding"
        assert info["base_url"] == "https://api.kimi.com/coding/v1"

    def test_kimi_code_anthropic_provider_exists(self):
        """验证 kimi-code-anthropic provider 存在"""
        assert "kimi-code-anthropic" in _PROVIDERS
        info = _PROVIDERS["kimi-code-anthropic"]
        assert info["name"] == "Kimi Code (Anthropic兼容)"
        assert info["default_model"] == "kimi-for-coding"
        assert info["base_url"] == "https://api.kimi.com/coding/"

    def test_kimi_provider_still_exists(self):
        """验证原有 kimi provider 仍然存在"""
        assert "kimi" in _PROVIDERS
        info = _PROVIDERS["kimi"]
        assert info["name"] == "Kimi (Moonshot)"
        assert info["default_model"] == "moonshot-v1-8k"
        assert info["base_url"] == "https://api.moonshot.cn/v1"

    def test_create_kimi_k2_client(self):
        """测试创建 Kimi K2 客户端"""
        cfg = {
            "providers": {
                "kimi-k2": {"key": "test-key"}
            }
        }
        client, provider, model = create_llm_client_for("kimi-k2", "kimi-k2-0905-preview", cfg)
        assert provider == "kimi-k2"
        assert model == "kimi-k2-0905-preview"
        assert client.api_key == "test-key"

    def test_create_kimi_code_client(self):
        """测试创建 Kimi Code 客户端"""
        cfg = {
            "providers": {
                "kimi-code": {"key": "test-key"}
            }
        }
        client, provider, model = create_llm_client_for("kimi-code", "kimi-for-coding", cfg)
        assert provider == "kimi-code"
        assert model == "kimi-for-coding"
        assert client.api_key == "test-key"

    def test_create_kimi_code_anthropic_client(self):
        """测试创建 Kimi Code Anthropic 客户端"""
        cfg = {
            "providers": {
                "kimi-code-anthropic": {"key": "test-key"}
            }
        }
        client, provider, model = create_llm_client_for("kimi-code-anthropic", "kimi-for-coding", cfg)
        assert provider == "kimi-code-anthropic"
        assert model == "kimi-for-coding"
        assert client.api_key == "test-key"


class TestProviderManagement:
    """测试 provider 管理功能"""

    def test_list_providers_includes_new(self):
        """验证列表包含新添加的 provider"""
        providers = list_providers()
        provider_ids = [p["id"] for p in providers]

        assert "openai" in provider_ids
        assert "minimax" in provider_ids
        assert "minimax-chat" in provider_ids
        assert "minimax-m27" in provider_ids
        assert "minimax-m27-fast" in provider_ids
        assert "minimax-token-plan" in provider_ids
        assert "kimi" in provider_ids
        assert "kimi-k2" in provider_ids
        assert "kimi-code" in provider_ids
        assert "kimi-code-anthropic" in provider_ids
        assert "mimo-token-plan" in provider_ids
        assert "zhipu-coding" in provider_ids

    def test_get_provider_info_new(self):
        """验证可以获取新 provider 的信息"""
        info = get_provider_info("minimax")
        assert info is not None
        assert info["name"] == "MiniMax"

        info = get_provider_info("minimax-m27")
        assert info is not None
        assert info["name"] == "MiniMax M2.7 (Token Plan)"

        info = get_provider_info("minimax-m27-fast")
        assert info is not None
        assert info["name"] == "MiniMax M2.7-HighSpeed (Token Plan)"

        info = get_provider_info("minimax-token-plan")
        assert info is not None
        assert info["name"] == "MiniMax Token Plan (全模态)"

        info = get_provider_info("kimi-k2")
        assert info is not None
        assert info["name"] == "Kimi K2 (代码优化版)"

    def test_resolve_kimi_k2_model(self):
        """测试解析 Kimi K2 模型"""
        provider, model = resolve_provider_model("kimi-k2:kimi-k2-0905-preview")
        assert provider == "kimi-k2"
        assert model == "kimi-k2-0905-preview"

    def test_resolve_minimax_model(self):
        """测试解析 MiniMax 模型"""
        provider, model = resolve_provider_model("minimax:MiniMax-Text-01")
        assert provider == "minimax"
        assert model == "MiniMax-Text-01"

    def test_resolve_minimax_m27_model(self):
        """测试解析 MiniMax M2.7 模型"""
        provider, model = resolve_provider_model("minimax-m27:MiniMax-M2.7")
        assert provider == "minimax-m27"
        assert model == "MiniMax-M2.7"


class TestNewProviderConfiguration:
    """测试新 provider 的配置"""

    def test_minimax_with_custom_base_url(self):
        """测试 MiniMax 使用自定义 base_url"""
        cfg = {
            "providers": {
                "minimax": {
                    "key": "test-key",
                    "base_url": "https://custom.minimax.api/v1"
                }
            }
        }
        client, provider, model = create_llm_client_for("minimax", "MiniMax-Text-01", cfg)
        assert str(client._client.base_url).rstrip('/') == "https://custom.minimax.api/v1"

    def test_kimi_k2_with_custom_base_url(self):
        """测试 Kimi K2 使用自定义 base_url"""
        cfg = {
            "providers": {
                "kimi-k2": {
                    "key": "test-key",
                    "base_url": "https://custom.moonshot.api/v1"
                }
            }
        }
        client, provider, model = create_llm_client_for("kimi-k2", "kimi-k2-0905-preview", cfg)
        assert str(client._client.base_url).rstrip('/') == "https://custom.moonshot.api/v1"

    def test_minimax_with_override_key(self):
        """测试 MiniMax 使用 override key"""
        cfg = {
            "providers": {
                "minimax": {"key": "original-key"}
            }
        }
        client, provider, model = create_llm_client_for(
            "minimax", "MiniMax-Text-01", cfg, override_key="override-key"
        )
        assert client.api_key == "override-key"

    def test_mimo_token_plan_provider_exists(self):
        """验证 mimo-token-plan provider 存在"""
        assert "mimo-token-plan" in _PROVIDERS
        info = _PROVIDERS["mimo-token-plan"]
        assert info["name"] == "小米 MiMo (Token Plan)"
        assert info["default_model"] == "mimo-v2-flash"
        assert info["base_url"] == "https://token-plan-sgp.xiaomimimo.com/v1"
        assert info["token_plan_base_url"] == "https://token-plan-sgp.xiaomimimo.com/v1"
        assert info["is_token_plan"] is True

    def test_mimo_token_plan_client_uses_token_plan_url(self):
        """验证 mimo-token-plan 客户端使用 Token Plan Base URL"""
        cfg = {
            "providers": {
                "mimo-token-plan": {"key": "tp-key"}
            }
        }
        client, provider, model = create_llm_client_for("mimo-token-plan", "mimo-v2-flash", cfg)
        assert provider == "mimo-token-plan"
        assert model == "mimo-v2-flash"
        assert str(client._client.base_url).rstrip('/') == "https://token-plan-sgp.xiaomimimo.com/v1"

    def test_zhipu_coding_provider_exists(self):
        """验证 zhipu-coding provider 存在"""
        assert "zhipu-coding" in _PROVIDERS
        info = _PROVIDERS["zhipu-coding"]
        assert info["name"] == "智谱 GLM Coding Plan"
        assert info["default_model"] == "glm-4.7"
        assert info["base_url"] == "https://open.bigmodel.cn/api/coding/paas/v4"
        assert info["is_token_plan"] is True

    def test_zhipu_coding_client_uses_coding_url(self):
        """验证 zhipu-coding 客户端使用 Coding Plan Base URL"""
        cfg = {
            "providers": {
                "zhipu-coding": {"key": "coding-key"}
            }
        }
        client, provider, model = create_llm_client_for("zhipu-coding", "glm-4.7", cfg)
        assert provider == "zhipu-coding"
        assert model == "glm-4.7"
        assert str(client._client.base_url).rstrip('/') == "https://open.bigmodel.cn/api/coding/paas/v4"

    def test_minimax_token_plan_uses_token_plan_url(self):
        """验证 minimax-token-plan 客户端使用 Token Plan Base URL"""
        cfg = {
            "providers": {
                "minimax-token-plan": {"key": "tp-key"}
            }
        }
        client, provider, model = create_llm_client_for("minimax-token-plan", "MiniMax-M2.7", cfg)
        assert provider == "minimax-token-plan"
        assert model == "MiniMax-M2.7"
        assert str(client._client.base_url).rstrip('/') == "https://api.minimax.chat/v1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
