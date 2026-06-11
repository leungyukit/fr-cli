"""
LLM 统一召唤接口 —— 万法归一

为各大模型提供商提供统一的流式对话接口，
使主程序无需关心底层 SDK 差异。

模型配置已迁移到配置文件 ~/.fr_cli/models.yaml
"""
from abc import ABC, abstractmethod
from typing import Iterator, Optional, Dict, Any, List

_PROVIDERS: Dict[str, Dict[str, Any]] = {}
# 模型名 → Provider 反向映射（用于从模型名推断所属提供商）
_MODEL_TO_PROVIDER: Dict[str, str] = {}

def _load_providers_from_factory():
    """从工厂加载 Provider 配置，同时建立模型名 → Provider 反向映射"""
    global _PROVIDERS, _MODEL_TO_PROVIDER
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

            default_model = cfg.get("model", "glm-4-flash")
            _PROVIDERS[pid] = {
                "name": cfg.get("name", pid),
                "default_model": default_model,
                "models": cfg.get("models", [default_model]),
                "client_class": client_cls,
                "base_url": cfg.get("base_url"),
                "token_plan_base_url": cfg.get("token_plan_base_url"),
                "is_token_plan": cfg.get("is_token_plan", False),
            }
            # 建立反向映射：模型名 → provider（默认模型 + 所有可选模型）
            all_models = cfg.get("models", [])
            for m in [default_model] + all_models:
                if m and m not in _MODEL_TO_PROVIDER:
                    _MODEL_TO_PROVIDER[m] = pid
    except Exception as e:
        import warnings
        warnings.warn(f"从工厂加载 Provider 失败: {e}")

def reload_providers():
    """重新加载 Provider 配置"""
    global _PROVIDERS, _MODEL_TO_PROVIDER
    _PROVIDERS = {}
    _MODEL_TO_PROVIDER = {}
    _load_providers_from_factory()

def get_provider_list() -> List[str]:
    """获取 Provider 列表"""
    if not _PROVIDERS:
        _load_providers_from_factory()
    return list(_PROVIDERS.keys())

def get_provider_info(provider: str) -> Optional[Dict[str, Any]]:
    """获取 Provider 信息，无效 provider 返回 None"""
    if not _PROVIDERS:
        _load_providers_from_factory()
    return _PROVIDERS.get(provider)

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

    DEFAULT_TIMEOUT = 60  # 默认请求超时（秒）

    def __init__(self, api_key: str, **kwargs):
        self.api_key = api_key

    @abstractmethod
    def stream_chat(self, model: str, messages: list, max_tokens: int = 4096, timeout: int = None) -> Iterator[dict]:
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

    def stream_chat(self, model: str, messages: list, max_tokens: int = 4096, timeout: int = None) -> Iterator[dict]:
        response = self._client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            max_tokens=max_tokens,
            timeout=timeout or self.DEFAULT_TIMEOUT,
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

    def stream_chat(self, model: str, messages: list, max_tokens: int = 4096, timeout: int = None) -> Iterator[dict]:
        response = self._client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            max_tokens=max_tokens,
            timeout=timeout or self.DEFAULT_TIMEOUT,
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

    def stream_chat(self, model: str, messages: list, max_tokens: int = 4096, timeout: int = None) -> Iterator[dict]:
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

        response = requests.post(url, json=payload, headers=headers, stream=True, timeout=timeout or self.DEFAULT_TIMEOUT)

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

    info = _PROVIDERS.get(provider, {})
    if not info:
        # provider 不存在时回退到 factory 第一个 provider
        first_provider = list(_PROVIDERS.keys())[0] if _PROVIDERS else None
        info = _PROVIDERS.get(first_provider, {}) if first_provider else {}
    client_class = info.get("client_class", OpenAICompatibleClient)

    # Token Plan 与一般 API 的 Base URL 可能不同；若 provider 标记为 token plan，
    # 优先使用 token_plan_base_url，否则使用通用 base_url。
    is_token_plan = pcfg.get("is_token_plan") or info.get("is_token_plan", False)
    if is_token_plan:
        base_url = pcfg.get("token_plan_base_url") or pcfg.get("base_url") or info.get("token_plan_base_url") or info.get("base_url")
    else:
        base_url = pcfg.get("base_url") or info.get("base_url")

    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url

    return client_class, kwargs


# ============================================================
# Mock LLM 客户端 —— 零配置试用 / API 不可用时的降级方案
# ============================================================

class MockLLMClient(BaseLLMClient):
    """Mock LLM：不调任何远程 API，本地回声式响应

    适用场景：
    1. 用户首次启动还没配 API Key（init_config 检测到无 key 时切换）
    2. 远程 API 调用失败（网络/限流/key 错）的临时降级
    3. 演示 / 测试场景
    """

    def __init__(self, api_key: str = "mock", **kwargs):
        super().__init__(api_key, **kwargs)
        self.model = kwargs.get("model", "mock-echo")
        self.is_mock = True

    def stream_chat(self, model: str, messages: list, max_tokens: int = 4096, timeout: int = None) -> Iterator[dict]:
        """回声响应：把最后一条 user message 包装一下吐出来"""
        import time as _time

        # 提取最后一条 user 消息
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = m.get("content", "")
                break

        # 简单响应模板
        if not last_user:
            response = "【Mock 模式】我是本地 mock 客户端，没收到你的输入。配置 API Key 后可启用真实 LLM（/key <your-key>）。"
        elif last_user.startswith("/"):
            response = f"【Mock 模式】你输入了命令 {last_user[:60]}。当前在 mock 模式，命令执行仍可工作（不依赖 LLM），只是 AI 回答部分是模拟的。"
        else:
            short = last_user[:200]
            response = (
                f"【Mock 模式 🧪】当前未配置 API Key 或 LLM 不可用。\n"
                f"你刚才说的是：{short}\n\n"
                f"**配置真实 LLM 的方式：**\n"
                f"- `/key sk-xxx` 设置当前提供商（zhipu）的 key\n"
                f"- `/providers use deepseek` 切换到其他提供商\n"
                f"- `/providers setup` 交互式配置\n\n"
                f"**Mock 模式仍能用的功能：**\n"
                f"- `/help` / `/cat` / `/ls` / `/web` 等命令\n"
                f"- `/shell` 执行系统命令\n"
                f"- `@local` / `@RAG` 等不依赖 LLM 的 Agent\n"
            )

        # 模拟流式输出：按词切分
        for word in response.split(" "):
            yield {"content": word + " ", "usage": None}
            _time.sleep(0.02)  # 让用户看到流式效果

        # 最后给个 usage
        yield {"content": "", "usage": {
            "prompt_tokens": sum(len(m.get("content", "")) for m in messages) // 4,
            "completion_tokens": len(response) // 4,
            "total_tokens": (sum(len(m.get("content", "")) for m in messages) + len(response)) // 4,
        }}


def create_llm_client(cfg: dict, prefer_saved_model: bool = True):
    """根据配置创建对应的 LLM 客户端

    核心原则：
    1. provider 不再硬编码为 zhipu，从 factory 第一个 provider 回退
    2. model 优先从 factory 默认配置获取；当 prefer_saved_model=True 时
       允许从用户配置持久化字段读取（供运行时 /model 切换后 reinit 使用）
    3. 当检测到无 API Key 时，自动回退到 MockLLMClient

    Args:
        prefer_saved_model: True 时优先使用 providers_cfg 中保存的 model（默认）；
                            False 时强制使用 factory 默认。
    """
    if not _PROVIDERS:
        _load_providers_from_factory()

    # provider：配置文件中指定，未指定则返回 None（由调用方处理）
    provider = cfg.get("provider")
    if not provider:
        # 未配置 provider，回退到 Mock（状态栏显示"未配置"）
        return MockLLMClient(model="未配置"), None, "未配置"

    default_model = _PROVIDERS.get(provider, {}).get("default_model", "glm-4-flash")

    providers_cfg = cfg.get("providers", {})
    pcfg = providers_cfg.get(provider, {})

    # 优先读取用户保存的 model，无配置时回退到 factory 默认
    if prefer_saved_model:
        model = pcfg.get("model", default_model)
    else:
        model = default_model

    api_key = pcfg.get("key") or cfg.get("key", "")

    # 零配置试用：检测到无 API Key → 自动回退到 Mock
    if not api_key:
        client = MockLLMClient(model=model)
        return client, provider, model

    client_class, kwargs = _resolve_llm_kwargs(provider, cfg)
    return client_class(**kwargs), provider, model


def create_llm_client_for(provider: str, model: str, cfg: dict, override_key: str = None):
    """根据全局配置创建指定 provider + model 的 LLM 客户端"""
    client_class, kwargs = _resolve_llm_kwargs(provider, cfg, override_key)
    return client_class(**kwargs), provider, model


def get_provider_by_model(model_name: str) -> Optional[str]:
    """根据模型名查找所属 provider（基于 factory 默认配置中的反向映射）"""
    if not _PROVIDERS:
        _load_providers_from_factory()
    return _MODEL_TO_PROVIDER.get(model_name)


def resolve_provider_model(arg: str) -> tuple:
    """解析用户输入的模型参数

    支持格式：
      - provider:model   显式指定 provider 和 model
      - provider         仅 provider ID，使用其默认模型
      - model            仅模型名，尝试自动推断所属 provider

    返回: (provider_or_None, model)
    """
    if ":" in arg:
        parts = arg.split(":", 1)
        return parts[0].strip(), parts[1].strip()
    val = arg.strip()
    # 优先检查是否为 provider ID（如 stepfun-step-plan）
    if not _PROVIDERS:
        _load_providers_from_factory()
    if val in _PROVIDERS:
        return val, _PROVIDERS[val]["default_model"]
    inferred_provider = get_provider_by_model(val)
    return inferred_provider, val


# 初始化加载
_load_providers_from_factory()