from fr_cli.conf.paths import MODELS_YAML
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
        """获取默认配置 —— 每个 provider 包含常用模型列表，供 /model config 交互选择"""
        return {
            "zhipu": {
                "name": "智谱",
                "model": "glm-4-flash",
                "models": ["glm-4-flash", "glm-4-plus", "glm-4", "glm-4v-plus", "glm-4-air", "glm-4-long"],
                "client": "ZhipuLLMClient",
                "base_url": None,
                "token_plan_base_url": "https://open.bigmodel.cn/api/coding/paas/v4",
                "is_token_plan": False
            },
            "zhipu-coding": {
                "name": "智谱 GLM Coding Plan",
                "model": "glm-4.7",
                "models": ["glm-4.7", "glm-5.1", "glm-4.5-air"],
                "client": "OpenAICompatibleClient",
                "base_url": "https://open.bigmodel.cn/api/coding/paas/v4",
                "token_plan_base_url": "https://open.bigmodel.cn/api/coding/paas/v4",
                "is_token_plan": True
            },
            "kimi": {
                "name": "Kimi (Moonshot)",
                "model": "moonshot-v1-8k",
                "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
                "client": "OpenAICompatibleClient",
                "base_url": "https://api.moonshot.cn/v1",
                "token_plan_base_url": None,
                "is_token_plan": False
            },
            "kimi-k2": {
                "name": "Kimi K2 (代码优化版)",
                "model": "kimi-k2-0905-preview",
                "models": ["kimi-k2-0905-preview"],
                "client": "OpenAICompatibleClient",
                "base_url": "https://api.moonshot.cn/v1",
                "token_plan_base_url": None,
                "is_token_plan": False
            },
            "kimi-code": {
                "name": "Kimi Code (代码平台)",
                "model": "kimi-for-coding",
                "models": ["kimi-for-coding"],
                "client": "OpenAICompatibleClient",
                "base_url": "https://api.kimi.com/coding/v1",
                "token_plan_base_url": None,
                "is_token_plan": False
            },
            "kimi-code-anthropic": {
                "name": "Kimi Code (Anthropic兼容)",
                "model": "kimi-for-coding",
                "models": ["kimi-for-coding"],
                "client": "OpenAICompatibleClient",
                "base_url": "https://api.kimi.com/coding/",
                "token_plan_base_url": None,
                "is_token_plan": False
            },
            "openai": {
                "name": "OpenAI",
                "model": "gpt-4o-mini",
                "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo", "o1-mini", "o3-mini"],
                "client": "OpenAICompatibleClient",
                "base_url": "https://api.openai.com/v1",
                "token_plan_base_url": None,
                "is_token_plan": False
            },
            "deepseek": {
                "name": "DeepSeek",
                "model": "deepseek-chat",
                "models": ["deepseek-chat", "deepseek-reasoner", "deepseek-coder"],
                "client": "OpenAICompatibleClient",
                "base_url": "https://api.deepseek.com",
                "token_plan_base_url": None,
                "is_token_plan": False
            },
            "qwen": {
                "name": "通义千问",
                "model": "qwen-turbo",
                "models": ["qwen-turbo", "qwen-plus", "qwen-max", "qwen-coder-plus"],
                "client": "OpenAICompatibleClient",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "token_plan_base_url": None,
                "is_token_plan": False
            },
            "doubao": {
                "name": "豆包 (Doubao)",
                "model": "doubao-1-5-pro-32k-250115",
                "models": ["doubao-1-5-pro-32k-250115", "doubao-1-5-lite-32k-250115"],
                "client": "OpenAICompatibleClient",
                "base_url": "https://ark.cn-beijing.volces.com/api/v3",
                "token_plan_base_url": None,
                "is_token_plan": False
            },
            "mimo": {
                "name": "小米 MiMo",
                "model": "mimo-v2-flash",
                "models": ["mimo-v2-flash", "mimo-v2-pro"],
                "client": "OpenAICompatibleClient",
                "base_url": "https://api.xiaomimimo.com/v1",
                "token_plan_base_url": "https://token-plan-sgp.xiaomimimo.com/v1",
                "is_token_plan": False
            },
            "mimo-token-plan": {
                "name": "小米 MiMo (Token Plan)",
                "model": "mimo-v2-flash",
                "models": ["mimo-v2-flash", "mimo-v2-pro"],
                "client": "OpenAICompatibleClient",
                "base_url": "https://token-plan-sgp.xiaomimimo.com/v1",
                "token_plan_base_url": "https://token-plan-sgp.xiaomimimo.com/v1",
                "is_token_plan": True
            },
            "minimax": {
                "name": "MiniMax",
                "model": "MiniMax-Text-01",
                "models": ["MiniMax-Text-01", "MiniMax-M2.1", "abab6.5s-chat", "abab6.5t-chat"],
                "client": "OpenAICompatibleClient",
                "base_url": "https://api.minimax.io/v1",
                "token_plan_base_url": "https://api.minimax.chat/v1",
                "is_token_plan": False
            },
            "minimax-chat": {
                "name": "MiniMax Chat",
                "model": "abab6.5s-chat",
                "models": ["abab6.5s-chat"],
                "client": "OpenAICompatibleClient",
                "base_url": "https://api.minimax.io/v1",
                "token_plan_base_url": "https://api.minimax.chat/v1",
                "is_token_plan": False
            },
            "minimax-m27": {
                "name": "MiniMax M2.7 (Token Plan)",
                "model": "MiniMax-M2.7",
                "models": ["MiniMax-M2.7"],
                "client": "OpenAICompatibleClient",
                "base_url": "https://api.minimax.chat/v1",
                "token_plan_base_url": "https://api.minimax.chat/v1",
                "is_token_plan": True
            },
            "minimax-m27-fast": {
                "name": "MiniMax M2.7-HighSpeed (Token Plan)",
                "model": "MiniMax-M2.7-HighSpeed",
                "models": ["MiniMax-M2.7-HighSpeed"],
                "client": "OpenAICompatibleClient",
                "base_url": "https://api.minimax.chat/v1",
                "token_plan_base_url": "https://api.minimax.chat/v1",
                "is_token_plan": True
            },
            "minimax-token-plan": {
                "name": "MiniMax Token Plan (全模态)",
                "model": "MiniMax-M2.7",
                "models": ["MiniMax-M2.7"],
                "client": "OpenAICompatibleClient",
                "base_url": "https://api.minimax.chat/v1",
                "token_plan_base_url": "https://api.minimax.chat/v1",
                "is_token_plan": True
            },
            "stepfun": {
                "name": "阶跃星辰 (StepFun)",
                "model": "step-1-8k",
                "models": ["step-1-8k", "step-1-32k", "step-1-128k", "step-2-16k", "step-3-auto", "step-3.7-flash"],
                "client": "OpenAICompatibleClient",
                "base_url": "https://api.stepfun.com/v1",
                "token_plan_base_url": "https://api.stepfun.com/step_plan/v1",
                "is_token_plan": False
            },
            "step-1": {
                "name": "Step-1 (阶跃星辰)",
                "model": "step-1-8k",
                "models": ["step-1-8k"],
                "client": "OpenAICompatibleClient",
                "base_url": "https://api.stepfun.com/v1",
                "token_plan_base_url": "https://api.stepfun.com/step_plan/v1",
                "is_token_plan": False
            },
            "step-2": {
                "name": "Step-2 (阶跃星辰)",
                "model": "step-2-16k",
                "models": ["step-2-16k"],
                "client": "OpenAICompatibleClient",
                "base_url": "https://api.stepfun.com/v1",
                "token_plan_base_url": "https://api.stepfun.com/step_plan/v1",
                "is_token_plan": False
            },
            "step-3": {
                "name": "Step-3 (阶跃星辰)",
                "model": "step-3-auto",
                "models": ["step-3-auto"],
                "client": "OpenAICompatibleClient",
                "base_url": "https://api.stepfun.com/v1",
                "token_plan_base_url": "https://api.stepfun.com/step_plan/v1",
                "is_token_plan": False
            },
            "step-audio": {
                "name": "Step-Audio (实时语音)",
                "model": "step-audio-2",
                "models": ["step-audio-2"],
                "client": "OpenAICompatibleClient",
                "base_url": "https://api.stepfun.com/v1",
                "token_plan_base_url": "https://api.stepfun.com/step_plan/v1",
                "is_token_plan": False
            },
            "stepfun-step-plan": {
                "name": "阶跃星辰 Step Plan",
                "model": "step-3-auto",
                "models": ["step-3-auto", "step-2-16k", "step-1-8k", "step-3.7-flash"],
                "client": "OpenAICompatibleClient",
                "base_url": "https://api.stepfun.com/step_plan/v1",
                "token_plan_base_url": "https://api.stepfun.com/step_plan/v1",
                "is_token_plan": True
            },
            "ernie": {
                "name": "文心一言",
                "model": "ernie-bot-4",
                "models": ["ernie-bot-4", "ernie-bot-4-turbo", "ernie-speed-128k"],
                "client": "WenxinLLMClient",
                "base_url": None,
                "token_plan_base_url": None,
                "is_token_plan": False
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
            "token_plan_base_url": config.get("token_plan_base_url"),
            "is_token_plan": config.get("is_token_plan", False),
        }
    
    return result
