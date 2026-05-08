"""
模型工厂 - 从配置文件加载模型
"""

import os
import json
import yaml
from typing import Dict, Any, Optional


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
            config_path = os.path.expanduser("~/.fr_cli/models.yaml")
        
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
        """获取默认配置"""
        return {
            "zhipu": {
                "name": "智谱",
                "model": "glm-4-flash",
                "client": "ZhipuLLMClient",
                "base_url": None
            },
            "kimi": {
                "name": "Kimi",
                "model": "moonshot-v1-8k",
                "client": "OpenAICompatibleClient",
                "base_url": "https://api.moonshot.cn/v1"
            },
            "kimi-code": {
                "name": "Kimi Code",
                "model": "kimi-for-coding",
                "client": "OpenAICompatibleClient",
                "base_url": "https://api.moonshot.cn/v1"
            },
            "deepseek": {
                "name": "DeepSeek",
                "model": "deepseek-chat",
                "client": "OpenAICompatibleClient",
                "base_url": "https://api.deepseek.com"
            },
            "qwen": {
                "name": "通义千问",
                "model": "qwen-turbo",
                "client": "OpenAICompatibleClient",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"
            },
            "doubao": {
                "name": "豆包",
                "model": "doubao-1-5-pro-32k-250115",
                "client": "OpenAICompatibleClient",
                "base_url": "https://ark.cn-beijing.volces.com/api/v3"
            },
            "mimo": {
                "name": "小米 MiMo",
                "model": "mimo-v2-flash",
                "client": "OpenAICompatibleClient",
                "base_url": "https://api.xiaomimimo.com/v1"
            },
            "minimax": {
                "name": "MiniMax",
                "model": "MiniMax-Text-01",
                "client": "OpenAICompatibleClient",
                "base_url": "https://api.minimax.chat/v1"
            },
            "minimax-chat": {
                "name": "MiniMax Chat",
                "model": "abab6.5s-chat",
                "client": "OpenAICompatibleClient",
                "base_url": "https://api.minimax.chat/v1"
            },
            "minimax-m27": {
                "name": "MiniMax M2.7",
                "model": "MiniMax-M2.7",
                "client": "OpenAICompatibleClient",
                "base_url": "https://api.minimax.chat/v1"
            },
            "ernie": {
                "name": "文心一言",
                "model": "ernie-bot-4",
                "client": "WenxinLLMClient",
                "base_url": None
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
    
    def get_model_name(self, provider_id: str) -> str:
        """获取模型名称"""
        config = self._config.get(provider_id, {})
        return config.get("model", "glm-4-flash")
    
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
            "default_model": config.get("model", "glm-4-flash"),
            "client_class": client_map.get(config.get("client", "OpenAICompatibleClient"), "OpenAICompatibleClient"),
            "base_url": config.get("base_url"),
        }
    
    return result
