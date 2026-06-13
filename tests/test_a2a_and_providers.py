"""
多提供商测试

测试目标：验证新增的 StepFun 系列 Provider 与 provider 管理功能。
"""
import pytest
from fr_cli.core.llm import (
    _PROVIDERS,
    create_llm_client_for,
    list_providers,
    get_provider_info,
    resolve_provider_model
)


class TestStepFunProviders:
    """测试 StepFun 相关 provider"""

    def test_stepfun_provider_exists(self):
        """验证 stepfun provider 存在"""
        assert "stepfun" in _PROVIDERS
        info = _PROVIDERS["stepfun"]
        assert info["name"] == "阶跃星辰 (StepFun)"
        assert info["default_model"] == "step-1-8k"
        assert info["base_url"] == "https://api.stepfun.com/v1"
        assert info["token_plan_base_url"] == "https://api.stepfun.com/step_plan/v1"
        assert info["is_token_plan"] is False

    def test_step_1_provider_exists(self):
        """验证 step-1 provider 存在"""
        assert "step-1" in _PROVIDERS
        info = _PROVIDERS["step-1"]
        assert info["name"] == "Step-1 (阶跃星辰)"
        assert info["default_model"] == "step-1-8k"
        assert info["base_url"] == "https://api.stepfun.com/v1"

    def test_step_2_provider_exists(self):
        """验证 step-2 provider 存在"""
        assert "step-2" in _PROVIDERS
        info = _PROVIDERS["step-2"]
        assert info["name"] == "Step-2 (阶跃星辰)"
        assert info["default_model"] == "step-2-16k"
        assert info["base_url"] == "https://api.stepfun.com/v1"

    def test_step_3_provider_exists(self):
        """验证 step-3 provider 存在"""
        assert "step-3" in _PROVIDERS
        info = _PROVIDERS["step-3"]
        assert info["name"] == "Step-3 (阶跃星辰)"
        assert info["default_model"] == "step-3-auto"
        assert info["base_url"] == "https://api.stepfun.com/v1"

    def test_step_audio_provider_exists(self):
        """验证 step-audio provider 存在"""
        assert "step-audio" in _PROVIDERS
        info = _PROVIDERS["step-audio"]
        assert info["name"] == "Step-Audio (实时语音)"
        assert info["default_model"] == "step-audio-2"
        assert info["base_url"] == "https://api.stepfun.com/v1"

    def test_stepfun_step_plan_provider_exists(self):
        """验证 stepfun-step-plan provider 存在"""
        assert "stepfun-step-plan" in _PROVIDERS
        info = _PROVIDERS["stepfun-step-plan"]
        assert info["name"] == "阶跃星辰 Step Plan"
        assert info["default_model"] == "step-3-auto"
        assert info["base_url"] == "https://api.stepfun.com/step_plan/v1"
        assert info["token_plan_base_url"] == "https://api.stepfun.com/step_plan/v1"
        assert info["is_token_plan"] is True

    def test_create_stepfun_step_plan_client(self):
        """测试创建 StepFun Step Plan 客户端"""
        cfg = {
            "providers": {
                "stepfun-step-plan": {"key": "test-key"}
            }
        }
        client, provider, model = create_llm_client_for("stepfun-step-plan", "step-3-auto", cfg)
        assert provider == "stepfun-step-plan"
        assert model == "step-3-auto"
        assert client.api_key == "test-key"
        assert str(client._client.base_url).rstrip('/') == "https://api.stepfun.com/step_plan/v1"

    def test_create_stepfun_client(self):
        """测试创建 StepFun 客户端"""
        cfg = {
            "providers": {
                "stepfun": {"key": "test-key"}
            }
        }
        client, provider, model = create_llm_client_for("stepfun", "step-1-8k", cfg)
        assert provider == "stepfun"
        assert model == "step-1-8k"
        assert client.api_key == "test-key"

    def test_create_step_3_client(self):
        """测试创建 Step-3 客户端"""
        cfg = {
            "providers": {
                "step-3": {"key": "test-key"}
            }
        }
        client, provider, model = create_llm_client_for("step-3", "step-3-auto", cfg)
        assert provider == "step-3"
        assert model == "step-3-auto"
        assert client.api_key == "test-key"


class TestStepFunProviderManagement:
    """测试 StepFun provider 管理功能"""

    def test_list_providers_includes_stepfun(self):
        """验证列表包含 StepFun provider"""
        providers = list_providers()
        provider_ids = [p["id"] for p in providers]

        assert "stepfun" in provider_ids
        assert "step-1" in provider_ids
        assert "step-2" in provider_ids
        assert "step-3" in provider_ids
        assert "step-audio" in provider_ids
        assert "stepfun-step-plan" in provider_ids

    def test_get_stepfun_provider_info(self):
        """验证可以获取 StepFun provider 的信息"""
        info = get_provider_info("stepfun")
        assert info is not None
        assert info["name"] == "阶跃星辰 (StepFun)"

        info = get_provider_info("step-3")
        assert info is not None
        assert info["name"] == "Step-3 (阶跃星辰)"

    def test_resolve_stepfun_model(self):
        """测试解析 StepFun 模型"""
        provider, model = resolve_provider_model("stepfun:step-1-8k")
        assert provider == "stepfun"
        assert model == "step-1-8k"

    def test_resolve_step_3_model(self):
        """测试解析 Step-3 模型"""
        provider, model = resolve_provider_model("step-3:step-3-auto")
        assert provider == "step-3"
        assert model == "step-3-auto"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
