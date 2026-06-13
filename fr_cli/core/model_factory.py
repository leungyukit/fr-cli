"""
模型工厂 - 从配置文件加载模型

默认 provider/model/base_url/client 等配置已从 Python 代码中移除，
统一收敛到 fr_cli/conf/default_models.yaml 包内资源与 ~/.fr_cli/models.yaml 用户配置。
"""

import os
import json
import yaml
import importlib.resources as resources
from typing import Dict, Optional

from fr_cli.conf.paths import MODELS_YAML


class ModelFactory:
    """模型工厂 - 从配置文件加载并创建模型"""

    _instance = None
    _config = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load_config(self, config_path: str = None):
        """从配置文件加载模型配置"""
        if config_path is None:
            config_path = MODELS_YAML

        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                if config_path.endswith('.yaml') or config_path.endswith('.yml'):
                    self._config = yaml.safe_load(f)
                else:
                    self._config = json.load(f)
        else:
            self._config = self._get_default_config()
        return self

    def _get_default_config(self):
        """获取默认配置 —— 从包内 default_models.yaml 加载。

        仅在包内资源缺失或损坏时使用最小兜底配置。
        """
        try:
            ref = resources.files("fr_cli.conf") / "default_models.yaml"
            with ref.open("r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
                if cfg:
                    return cfg
        except Exception:
            pass

        # 最小兜底：确保至少有一个可用 provider
        return {
            "zhipu": {
                "name": "智谱",
                "model": "glm-4-flash",
                "models": ["glm-4-flash", "glm-4-plus", "glm-4", "glm-4v-plus", "glm-4-air", "glm-4-long"],
                "client": "ZhipuLLMClient",
                "base_url": None,
                "token_plan_base_url": "https://open.bigmodel.cn/api/coding/paas/v4",
                "is_token_plan": False,
                "image_model": "cogview-3-plus"
            }
        }

    def create_client(self, provider_id: str, api_key: str):
        """工厂方法：创建模型客户端"""
        config = self._config.get(provider_id)
        if not config:
            raise ValueError(f"Provider {provider_id} not found")

        client_type = config.get("client", "OpenAICompatibleClient")

        from fr_cli.core.llm import ZhipuLLMClient, OpenAICompatibleClient, WenxinLLMClient

        if client_type == "ZhipuLLMClient":
            return ZhipuLLMClient(api_key)
        elif client_type == "OpenAICompatibleClient":
            base_url = config.get("base_url")
            return OpenAICompatibleClient(api_key, base_url)
        elif client_type == "WenxinLLMClient":
            return WenxinLLMClient(api_key)
        else:
            raise ValueError(f"Unknown client type: {client_type}")

    def get_model_name(self, provider_id: str) -> Optional[str]:
        """获取模型名称；未知 provider 返回 None"""
        config = self._config.get(provider_id)
        if not config:
            return None
        return config.get("model")

    def list_providers(self):
        """列出所有 Provider"""
        return list(self._config.keys())

    def get_config(self, provider_id: str) -> Dict:
        """获取 Provider 配置"""
        return self._config.get(provider_id, {})


# 全局工厂实例
_factory = None

def get_model_factory() -> ModelFactory:
    """获取模型工厂实例"""
    global _factory
    if _factory is None:
        _factory = ModelFactory().load_config()
    return _factory


def build_models_dict() -> Dict[str, Dict]:
    """从配置文件构建模型字典（供 llm.py 使用）"""
    factory = get_model_factory()
    result = {}

    client_map = {
        "ZhipuLLMClient": "ZhipuLLMClient",
        "OpenAICompatibleClient": "OpenAICompatibleClient",
        "WenxinLLMClient": "WenxinLLMClient"
    }

    for provider_id in factory.list_providers():
        config = factory.get_config(provider_id)
        result[provider_id] = {
            "name": config.get("name", provider_id),
            "default_model": config.get("model"),
            "client_class": client_map.get(config.get("client", "OpenAICompatibleClient"), "OpenAICompatibleClient"),
            "base_url": config.get("base_url"),
            "token_plan_base_url": config.get("token_plan_base_url"),
            "is_token_plan": config.get("is_token_plan", False),
        }

    return result
