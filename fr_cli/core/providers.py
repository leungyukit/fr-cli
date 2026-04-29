"""
模型提供商配置模块
- 工厂模式
- 动态对象生成
- Provider 管理
"""

import os
import json
from typing import Dict, Any, Optional

class ModelProvider:
    """模型提供商基类"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.name = config.get("name")
        self.default_model = config.get("default_model")
        self.base_url = config.get("base_url")
        self.client_class = config.get("client_class")
    
    def create_client(self, api_key: str):
        """工厂方法：创建客户端"""
        from fr_cli.core.llm import ZhipuLLMClient, OpenAICompatibleClient, WenxinLLMClient
        
        if self.client_class == "ZhipuLLMClient":
            return ZhipuLLMClient(api_key)
        elif self.client_class == "OpenAICompatibleClient":
            return OpenAICompatibleClient(api_key, self.base_url)
        elif self.client_class == "WenxinLLMClient":
            return WenxinLLMClient(api_key)
        else:
            raise ValueError(f"未知客户端类型: {self.client_class}")


class ProviderRegistry:
    """Provider 注册表"""
    _providers = {}
    
    @classmethod
    def register(cls, provider_id: str, config: Dict):
        cls._providers[provider_id] = ModelProvider(config)
    
    @classmethod
    def get(cls, provider_id: str) -> Optional[ModelProvider]:
        return cls._providers.get(provider_id)
    
    @classmethod
    def list_all(cls):
        return list(cls._providers.keys())


# 默认 Provider
ProviderRegistry.register("zhipu", {
    "name": "智谱",
    "default_model": "glm-4-flash",
    "client_class": "ZhipuLLMClient",
    "base_url": None,
})
ProviderRegistry.register("kimi", {
    "name": "Kimi",
    "default_model": "moonshot-v1-8k",
    "client_class": "OpenAICompatibleClient",
    "base_url": "https://api.moonshot.cn/v1",
})
ProviderRegistry.register("kimi-code", {
    "name": "Kimi Code",
    "default_model": "kimi-for-coding",
    "client_class": "OpenAICompatibleClient",
    "base_url": "https://api.moonshot.cn/v1",
})
ProviderRegistry.register("deepseek", {
    "name": "DeepSeek",
    "default_model": "deepseek-chat",
    "client_class": "OpenAICompatibleClient",
    "base_url": "https://api.deepseek.com",
})
