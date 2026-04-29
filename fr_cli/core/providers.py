"""
模型提供商配置模块
- 所有模型配置独立管理
- 支持动态加载
- 方便维护和扩展
"""

PROVIDERS_CONFIG = {
    # ===== 智谱 AI =====
    "zhipu": {
        "name": "智谱 AI",
        "default_model": "glm-4-flash",
        "client_class": "ZhipuLLMClient",
        "base_url": None,
    },
    
    # ===== Kimi 系列 =====
    "kimi": {
        "name": "Kimi",
        "default_model": "moonshot-v1-8k",
        "client_class": "OpenAICompatibleClient",
        "base_url": "https://api.moonshot.cn/v1",
    },
    "kimi-k2": {
        "name": "Kimi K2",
        "default_model": "kimi-k2-0905-preview",
        "client_class": "OpenAICompatibleClient",
        "base_url": "https://api.moonshot.cn/v1",
    },
    "kimi-code": {
        "name": "Kimi Code",
        "default_model": "kimi-for-coding",
        "client_class": "OpenAICompatibleClient",
        "base_url": "https://api.moonshot.cn/v1",
    },
    
    # ===== DeepSeek =====
    "deepseek": {
        "name": "DeepSeek",
        "default_model": "deepseek-chat",
        "client_class": "OpenAICompatibleClient",
        "base_url": "https://api.deepseek.com",
    },
    
    # ===== 通义千问 =====
    "qwen": {
        "name": "通义千问",
        "default_model": "qwen-turbo",
        "client_class": "OpenAICompatibleClient",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    },
    
    # ===== 阶跃星辰 =====
    "stepfun": {
        "name": "阶跃星辰",
        "default_model": "step-1-8k",
        "client_class": "OpenAICompatibleClient",
        "base_url": "https://api.stepfun.com/v1",
    },
    
    # ===== MiniMax =====
    "minimax": {
        "name": "MiniMax",
        "default_model": "MiniMax-Text-01",
        "client_class": "OpenAICompatibleClient",
        "base_url": "https://api.minimax.chat/v1",
    },
    
    # ===== 文心一言 =====
    "ernie": {
        "name": "文心一言",
        "default_model": "ernie-bot-4",
        "client_class": "WenxinLLMClient",
        "base_url": "https://aip.baidubce.com",
    },
    
    # ===== 豆包 =====
    "doubao": {
        "name": "豆包",
        "default_model": "doubao-1-5-pro-32k",
        "client_class": "OpenAICompatibleClient",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
    },
}

# 获取所有 Provider 列表
def get_all_providers():
    return list(PROVIDERS_CONFIG.keys())

# 获取单个 Provider 配置
def get_provider(provider_id):
    return PROVIDERS_CONFIG.get(provider_id)

# 添加新 Provider
def add_provider(provider_id, config):
    PROVIDERS_CONFIG[provider_id] = config

# 删除 Provider
def remove_provider(provider_id):
    if provider_id in PROVIDERS_CONFIG:
        del PROVIDERS_CONFIG[provider_id]

# 更新 Provider
def update_provider(provider_id, **kwargs):
    if provider_id in PROVIDERS_CONFIG:
        PROVIDERS_CONFIG[provider_id].update(kwargs)
