"""
LLM 统一召唤接口 —— 万法归一

为各大模型提供商提供统一的流式对话接口，
使主程序无需关心底层 SDK 差异。

模型配置已迁移到配置文件 ~/.fr_cli/models.yaml
"""
from abc import ABC, abstractmethod
from typing import Iterator, Optional, Dict, Any, List

_PROVIDERS: Dict[str, Dict[str, Any]] = {}

def _load_providers_from_factory():
    """从工厂加载 Provider 配置"""
    global _PROVIDERS
    try:
        from fr_cli.core.model_factory import get_model_factory
        factory = get_model_factory()
        configs = factory._config or {}

        # 导入客户端类
        from fr_cli.core.llm import ZhipuLLMClient, OpenAICompatibleClient, WenxinLLMClient

        for pid, cfg in configs.items():
            client_type = cfg.get("client", "OpenAICompatibleClient")
            if client_type == "ZhipuLLMClient":
                client_cls = ZhipuLLMClient
            elif client_type == "WenxinLLMClient":
                client_cls = WenxinLLMClient
            else:
                client_cls = OpenAICompatibleClient

            _PROVIDERS[pid] = {
                "name": cfg.get("name", pid),
                "default_model": cfg.get("model", "glm-4-flash"),
                "client_class": client_cls,
                "base_url": cfg.get("base_url"),
            }
    except Exception as e:
        import warnings
        warnings.warn(f"从工厂加载 Provider 失败: {e}")

def reload_providers():
    """重新加载 Provider 配置"""
    global _PROVIDERS
    _PROVIDERS = {}
    _load_providers_from_factory()

def get_provider_list() -> List[str]:
    """获取 Provider 列表"""
    if not _PROVIDERS:
        _load_providers_from_factory()
    return list(_PROVIDERS.keys())

def get_provider_info(provider: str) -> Dict[str, Any]:
    """获取 Provider 信息"""
    if not _PROVIDERS:
        _load_providers_from_factory()
    return _PROVIDERS.get(provider, _PROVIDERS.get("zhipu", {}))

def list_providers() -> List[Dict]:
    """列出所有可用的 Provider"""
    if not _PROVIDERS:
        _load_providers_from_factory()
    return [
        {"id": k, "name": v["name"], "default_model": v["default_model"]}
        for k, v in _PROVIDERS.items()
    ]


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

    def __init__(self, api_key: str, base_url: str = None, **kwargs):
        super().__init__(api_key, **kwargs)
        from openai import OpenAI
        if base_url:
            self._client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            self._client = OpenAI(api_key=api_key)

    def stream_chat(self, model: str, messages: list, max_tokens: int = 4096) -> Iterator[dict]:
        response = self._client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            max_tokens=max_tokens,
        )
        yield from self._yield_chunks(response)


class WenxinLLMClient(BaseLLMClient):
    """百度文心一言客户端"""

    def __init__(self, api_key: str, secret_key: str = None, **kwargs):
        super().__init__(api_key, **kwargs)
        self.secret_key = secret_key or api_key
        self._access_token = None
        self._token_expires_at = 0

    def _get_access_token(self):
        """获取 Access Token（自动续期）"""
        import time
        if self._access_token and time.time() < self._token_expires_at - 300:
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


def _resolve_llm_kwargs(provider: str, cfg: dict, override_key: str = None):
    """根据配置解析创建 LLM 客户端所需的参数"""
    if not _PROVIDERS:
        _load_providers_from_factory()

    providers_cfg = cfg.get("providers", {})
    pcfg = providers_cfg.get(provider, {})

    api_key = override_key or pcfg.get("key") or cfg.get("key", "")

    info = _PROVIDERS.get(provider, _PROVIDERS.get("zhipu", {}))
    client_class = info.get("client_class", OpenAICompatibleClient)
    base_url = pcfg.get("base_url") or info.get("base_url")

    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url

    return client_class, kwargs


def create_llm_client(cfg: dict):
    """根据配置创建对应的 LLM 客户端"""
    if not _PROVIDERS:
        _load_providers_from_factory()

    provider = cfg.get("provider", "zhipu")
    providers_cfg = cfg.get("providers", {})
    pcfg = providers_cfg.get(provider, {})

    default_model = _PROVIDERS.get(provider, {}).get("default_model", "glm-4-flash")
    model = pcfg.get("model") or cfg.get("model", default_model)

    client_class, kwargs = _resolve_llm_kwargs(provider, cfg)
    return client_class(**kwargs), provider, model


def get_provider_info_static(provider_id: str):
    """获取指定提供商信息"""
    if not _PROVIDERS:
        _load_providers_from_factory()
    return _PROVIDERS.get(provider_id)


def create_llm_client_for(provider: str, model: str, cfg: dict, override_key: str = None):
    """根据全局配置创建指定 provider + model 的 LLM 客户端"""
    client_class, kwargs = _resolve_llm_kwargs(provider, cfg, override_key)
    return client_class(**kwargs), provider, model


def resolve_provider_model(arg: str) -> tuple:
    """解析用户输入的模型参数"""
    if ":" in arg:
        parts = arg.split(":", 1)
        return parts[0].strip(), parts[1].strip()
    return None, arg.strip()


# 初始化加载
_load_providers_from_factory()