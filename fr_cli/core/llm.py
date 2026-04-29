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


class WenxinLLMClient(BaseLLMClient):
    """
    百度文心一言客户端
    需要先通过 OAuth 获取 Access Token
    """

    def __init__(self, api_key: str, secret_key: str = None, **kwargs):
        super().__init__(api_key, **kwargs)
        self.secret_key = secret_key or api_key
        self._access_token = None
        self._token_expires_at = 0

    def _get_access_token(self) -> str:
        """获取 Access Token（带缓存）"""
        import time
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token

        import requests
        token_url = "https://aip.baidubce.com/oauth/2.0/token"
        params = {
            "grant_type": "client_credentials",
            "client_id": self.api_key,
            "client_secret": self.secret_key
        }
        response = requests.post(token_url, params=params, timeout=30)
        data = response.json()

        if "access_token" in data:
            self._access_token = data["access_token"]
            self._token_expires_at = time.time() + data.get("expires_in", 2592000)
            return self._access_token
        else:
            raise Exception(f"获取文心 Access Token 失败: {data}")

    def stream_chat(self, model: str, messages: list, max_tokens: int = 4096) -> Iterator[dict]:
        """文心流式对话"""
        import requests
        import json

        access_token = self._get_access_token()
        url = f"https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/completions?access_token={access_token}"

        headers = {"Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": messages,
            "stream": True
        }

        response = requests.post(url, json=payload, headers=headers, stream=True, timeout=60)

        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data:'):
                    data_str = line[5:].strip()
                    if data_str and data_str != '[DONE]':
                        try:
                            data = json.loads(data_str)
                            content = ""
                            if 'choices' in data and len(data['choices']) > 0:
                                delta = data['choices'][0].get('delta', {})
                                content = delta.get('content', '')
                            yield {"content": content, "usage": None}
                        except json.JSONDecodeError:
                            pass


# 提供商配置表
_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "zhipu": {
        "name": "智谱AI (Zhipu)",
        "default_model": "glm-4-flash",
        "client_class": ZhipuLLMClient,
        "base_url": None,
    },
    "zhipu-coding": {
        "name": "智谱 Coding Plan",
        "default_model": "GLM-4.7",
        "client_class": OpenAICompatibleClient,
        "base_url": "https://open.bigmodel.cn/api/coding/paas/v4",
    },
    "zhipu-anthropic": {
        "name": "智谱 GLM (Anthropic兼容)",
        "default_model": "glm-4.6",
        "client_class": OpenAICompatibleClient,
        "base_url": "https://open.bigmodel.cn/api/anthropic",
    },
    "ernie": {
        "name": "文心一言 (ERNIE Bot)",
        "default_model": "ernie-bot-4",
        "client_class": WenxinLLMClient,
        "base_url": "https://aip.baidubce.com",
    },
    "ernie-4": {
        "name": "文心一言 4.0 (ERNIE Bot 4)",
        "default_model": "ernie-bot-4",
        "client_class": WenxinLLMClient,
        "base_url": "https://aip.baidubce.com",
    },
    "ernie-turbo": {
        "name": "文心一言 Turbo (高速版)",
        "default_model": "ernie-bot-turbo",
        "client_class": WenxinLLMClient,
        "base_url": "https://aip.baidubce.com",
    },
    "ernie-8k": {
        "name": "文心一言 8K",
        "default_model": "ernie-bot-8k",
        "client_class": WenxinLLMClient,
        "base_url": "https://aip.baidubce.com",
    },
    "longcat": {
        "name": "LongCat (龙猫)",
        "default_model": "LongCat-Flash-Chat",
        "client_class": OpenAICompatibleClient,
        "base_url": "https://api.longcat.chat/openai",
    },
    "longcat-anthropic": {
        "name": "LongCat (Anthropic兼容)",
        "default_model": "LongCat",
        "client_class": OpenAICompatibleClient,
        "base_url": "https://api.longcat.chat/anthropic",
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
    "kimi-k2": {
        "name": "Kimi K2 (代码优化版)",
        "default_model": "kimi-k2-0905-preview",
        "client_class": OpenAICompatibleClient,
        "base_url": "https://api.moonshot.cn/v1",
    },
    "kimi-code": {
        "name": "Kimi Code (代码平台)",
        "default_model": "kimi-cache-test",
        "client_class": OpenAICompatibleClient,
        "base_url": "https://api.kimi.com/coding/v1",
    },
    "kimi-code-anthropic": {
        "name": "Kimi Code (Anthropic兼容)",
        "default_model": "kimi-cache-test",
        "client_class": OpenAICompatibleClient,
        "base_url": "https://api.kimi.com/coding/Kimi",
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
    "step-1": {
        "name": "Step-1 (阶跃星辰)",
        "default_model": "step-1-8k",
        "client_class": OpenAICompatibleClient,
        "base_url": "https://api.stepfun.com/v1",
    },
    "step-2": {
        "name": "Step-2 (阶跃星辰)",
        "default_model": "step-2-16k",
        "client_class": OpenAICompatibleClient,
        "base_url": "https://api.stepfun.com/v1",
    },
    "step-3": {
        "name": "Step-3 (阶跃星辰)",
        "default_model": "step-3-auto",
        "client_class": OpenAICompatibleClient,
        "base_url": "https://api.stepfun.com/v1",
    },
    "step-audio": {
        "name": "Step-Audio (实时语音)",
        "default_model": "step-audio-2",
        "client_class": OpenAICompatibleClient,
        "base_url": "https://api.stepfun.com/v1",
    },
    "minimax": {
        "name": "MiniMax",
        "default_model": "MiniMax-Text-01",
        "client_class": OpenAICompatibleClient,
        "base_url": "https://api.minimax.chat/v1",
    },
    "minimax-chat": {
        "name": "MiniMax Chat",
        "default_model": "abab6.5s-chat",
        "client_class": OpenAICompatibleClient,
        "base_url": "https://api.minimax.chat/v1",
    },
    "minimax-m27": {
        "name": "MiniMax M2.7 (Token Plan)",
        "default_model": "MiniMax-M2.7",
        "client_class": OpenAICompatibleClient,
        "base_url": "https://api.minimax.chat/v1",
    },
    "minimax-m27-fast": {
        "name": "MiniMax M2.7-HighSpeed (Token Plan)",
        "default_model": "MiniMax-M2.7-HighSpeed",
        "client_class": OpenAICompatibleClient,
        "base_url": "https://api.minimax.chat/v1",
    },
    "minimax-token-plan": {
        "name": "MiniMax Token Plan (全模态)",
        "default_model": "MiniMax-M2.7",
        "client_class": OpenAICompatibleClient,
        "base_url": "https://api.minimax.chat/v1",
    },
    "spark": {
        "name": "讯飞星火 (Spark)",
        "default_model": "generalv3.5",
        "client_class": OpenAICompatibleClient,
        "base_url": "https://spark-api-open.xf-yun.com/v1",
    },
    "doubao": {
        "name": "豆包 (Doubao)",
        "default_model": "doubao-1-5-pro-32k-250115",
        "client_class": OpenAICompatibleClient,
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
    },
    "mimo": {
        "name": "小米 MiMo",
        "default_model": "mimo-v2-flash",
        "client_class": OpenAICompatibleClient,
        "base_url": "https://api.xiaomimimo.com/v1",
    },
}


def _resolve_llm_kwargs(provider: str, cfg: dict, override_key: str = None):
    """
    根据配置解析创建 LLM 客户端所需的参数。
    返回: (client_class, kwargs_dict)
    """
    providers_cfg = cfg.get("providers", {})
    pcfg = providers_cfg.get(provider, {})

    # 解析 key：override_key > provider 专属 > 顶层 key（zhipu 向后兼容）
    api_key = override_key or pcfg.get("key") or cfg.get("key", "")

    info = _PROVIDERS.get(provider, _PROVIDERS["zhipu"])
    client_class = info["client_class"]
    base_url = pcfg.get("base_url") or info.get("base_url")

    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url

    return client_class, kwargs


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
    pcfg = providers_cfg.get(provider, {})

    default_model = _PROVIDERS.get(provider, _PROVIDERS["zhipu"])["default_model"]
    model = pcfg.get("model") or cfg.get("model", default_model)

    client_class, kwargs = _resolve_llm_kwargs(provider, cfg)
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


def create_llm_client_for(provider: str, model: str, cfg: dict, override_key: str = None):
    """
    根据全局配置创建指定 provider + model 的 LLM 客户端

    Args:
        provider: 提供商 ID
        model: 模型名称
        cfg: 全局配置字典
        override_key: 可选的覆盖 key（如 Agent 专属 key）

    返回: (client_instance, provider_id, model_name)
    """
    client_class, kwargs = _resolve_llm_kwargs(provider, cfg, override_key)
    return client_class(**kwargs), provider, model


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
