"""
LLM 统一召唤接口 —— 万法归一

为各大模型提供商提供统一的流式对话接口，
使主程序无需关心底层 SDK 差异。
"""
from abc import ABC, abstractmethod
from typing import Iterator, Optional, Dict, Any


class BaseLLMClient(ABC):
    """大模型客户端抽象基类"""

    def __init__(self, api_key: str, **kwargs):
        self.api_key = api_key

    @abstractmethod
    def stream_chat(self, model: str, messages: list, max_tokens: int = 4096) -> Iterator[dict]:
        """
        流式对话，yield 每个 token 块
        格式: {"content": str, "usage": dict or None}
        """
        pass

    @staticmethod
    def _yield_chunks(response) -> Iterator[dict]:
        """通用 chunk 解析生成器，供各子类复用"""
        for chunk in response:
            content = ""
            usage = None
            if chunk.choices and chunk.choices[0].delta:
                content = chunk.choices[0].delta.content or ""
            if hasattr(chunk, 'usage') and chunk.usage:
                usage = chunk.usage.model_dump() if hasattr(chunk.usage, 'model_dump') else vars(chunk.usage)
            yield {"content": content, "usage": usage}


class ZhipuLLMClient(BaseLLMClient):
    """智谱 AI 客户端 (zhipuai SDK)"""

    def __init__(self, api_key: str, **kwargs):
        super().__init__(api_key, **kwargs)
        from zhipuai import ZhipuAI
        self._client = ZhipuAI(api_key=api_key)

    def stream_chat(self, model: str, messages: list, max_tokens: int = 4096) -> Iterator[dict]:
        response = self._client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            max_tokens=max_tokens,
        )
        yield from self._yield_chunks(response)


class OpenAICompatibleClient(BaseLLMClient):
    """
    OpenAI 兼容格式客户端
    覆盖：DeepSeek / Kimi(Moonshot) / 通义千问(Qwen) / StepFun / MiniMax / 讯飞星火(Spark)
    """

    def __init__(self, api_key: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(api_key, **kwargs)
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def stream_chat(self, model: str, messages: list, max_tokens: int = 4096) -> Iterator[dict]:
        response = self._client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            max_tokens=max_tokens,
        )
        yield from self._yield_chunks(response)


# 提供商配置表
_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "zhipu": {
        "name": "智谱AI (Zhipu)",
        "default_model": "glm-4-flash",
        "client_class": ZhipuLLMClient,
        "base_url": None,
    },
    "deepseek": {
        "name": "DeepSeek",
        "default_model": "deepseek-chat",
        "client_class": OpenAICompatibleClient,
        "base_url": "https://api.deepseek.com",
    },
    "kimi": {
        "name": "Kimi (Moonshot)",
        "default_model": "moonshot-v1-8k",
        "client_class": OpenAICompatibleClient,
        "base_url": "https://api.moonshot.cn/v1",
    },
    "qwen": {
        "name": "通义千问 (Qwen)",
        "default_model": "qwen-turbo",
        "client_class": OpenAICompatibleClient,
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    },
    "stepfun": {
        "name": "阶跃星辰 (StepFun)",
        "default_model": "step-1-8k",
        "client_class": OpenAICompatibleClient,
        "base_url": "https://api.stepfun.com/v1",
    },
    "minimax": {
        "name": "MiniMax",
        "default_model": "abab6.5-chat",
        "client_class": OpenAICompatibleClient,
        "base_url": "https://api.minimax.chat/v1",
    },
    "spark": {
        "name": "讯飞星火 (Spark)",
        "default_model": "generalv3.5",
        "client_class": OpenAICompatibleClient,
        "base_url": "https://spark-api-open.xf-yun.com/v1",
    },
}


def create_llm_client(cfg: dict):
    """
    根据配置创建对应的 LLM 客户端

    cfg 格式支持：
      新版: {"provider": "deepseek", "providers": {"deepseek": {"key": "xxx", "model": "..."}}}
      旧版: {"key": "xxx", "model": "glm-4-flash"}  (自动识别为 zhipu)

    返回: (client_instance, provider_id, model_name)
    """
    provider = cfg.get("provider", "zhipu")
    providers_cfg = cfg.get("providers", {})

    # 获取当前提供商配置
    pcfg = providers_cfg.get(provider, {})

    # 向后兼容：如果 providers 中没有当前 provider，从顶层读取 key/model
    # 使用 'or' 确保空字符串也能正确回退到顶层 key
    api_key = pcfg.get("key") or cfg.get("key", "")
    default_model = _PROVIDERS.get(provider, _PROVIDERS["zhipu"])["default_model"]
    model = pcfg.get("model") or cfg.get("model", default_model)

    info = _PROVIDERS.get(provider, _PROVIDERS["zhipu"])
    client_class = info["client_class"]
    # 优先使用用户自定义的 base_url，其次使用内置默认
    base_url = pcfg.get("base_url") or info.get("base_url")

    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url

    return client_class(**kwargs), provider, model


def list_providers():
    """返回所有支持的提供商列表"""
    return [
        {"id": k, "name": v["name"], "default_model": v["default_model"]}
        for k, v in _PROVIDERS.items()
    ]


def get_provider_info(provider_id: str):
    """获取指定提供商信息"""
    return _PROVIDERS.get(provider_id)


def resolve_provider_model(arg: str) -> tuple:
    """
    解析用户输入的模型参数
    支持格式：
      - "deepseek:deepseek-chat" → ("deepseek", "deepseek-chat")
      - "deepseek-chat"          → (None, "deepseek-chat")  (仅模型名，保持当前提供商)
    """
    if ":" in arg:
        parts = arg.split(":", 1)
        return parts[0].strip(), parts[1].strip()
    return None, arg.strip()
