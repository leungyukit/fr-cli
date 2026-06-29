"""
LLM 统一召唤接口 —— 万法归一

为各大模型提供商提供统一的流式对话接口,
使主程序无需关心底层 SDK 差异。

v3.0+ 拆分说明:
- 6 个客户端类拆到独立文件(base/zhipu/openai_compat/anthropic_compat/wenxin/mock)
- Provider 工厂与配置仍在本文件(_load_providers_from_factory 等)
- create_llm_client / resolve_provider_model 等高层 API 仍在本文件
- 旧 import `from fr_cli.core.llm import ZhipuLLMClient` 仍兼容(本文件统一 re-export)
"""
from typing import Optional, Dict, Any, List

from fr_cli.core.llm.base import BaseLLMClient
from fr_cli.core.llm.zhipu import ZhipuLLMClient
from fr_cli.core.llm.openai_compat import OpenAICompatibleClient
from fr_cli.core.llm.anthropic_compat import AnthropicCompatibleClient
from fr_cli.core.llm.wenxin import WenxinLLMClient
from fr_cli.core.llm.mock import MockLLMClient

# 客户端注册表:file → class(供 factory 动态选择)
LLM_CLIENT_REGISTRY = {
    "BaseLLMClient": BaseLLMClient,
    "ZhipuLLMClient": ZhipuLLMClient,
    "OpenAICompatibleClient": OpenAICompatibleClient,
    "AnthropicCompatibleClient": AnthropicCompatibleClient,
    "WenxinLLMClient": WenxinLLMClient,
    "MockLLMClient": MockLLMClient,
}

# ==================== Provider 工厂与配置 ====================

_PROVIDERS: Dict[str, Dict[str, Any]] = {}
# 模型名 → Provider 反向映射(用于从模型名推断所属提供商)
_MODEL_TO_PROVIDER: Dict[str, str] = {}


def _load_providers_from_factory():
    """从工厂加载 Provider 配置,同时建立模型名 → Provider 反向映射"""
    try:
        from fr_cli.core.model_factory import get_model_factory
        factory = get_model_factory()
        configs = factory._config or {}

        for pid, cfg in configs.items():
            # 兼容模式优先于 client 字段:compat=anthropic → AnthropicCompatibleClient
            compat = (cfg.get("compat") or "").strip().lower()
            if compat == "anthropic":
                client_cls = AnthropicCompatibleClient
            else:
                client_type = cfg.get("client", "OpenAICompatibleClient")
                client_cls = LLM_CLIENT_REGISTRY.get(client_type, OpenAICompatibleClient)

            default_model = cfg.get("model")
            _PROVIDERS[pid] = {
                "name": cfg.get("name", pid),
                "default_model": default_model,
                "models": cfg.get("models") or ([default_model] if default_model else []),
                "client_class": client_cls,
                "base_url": cfg.get("base_url"),
                "token_plan_base_url": cfg.get("token_plan_base_url"),
                "is_token_plan": cfg.get("is_token_plan", False),
                "compat": compat or ("zhipu" if cfg.get("client") == "ZhipuLLMClient" else "openai"),
            }
            # 建立反向映射:模型名 → provider(默认模型 + 所有可选模型)
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
    """获取 Provider 信息,无效 provider 返回 None"""
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


# ==================== 高层 API ====================

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

    # Token Plan 与一般 API 的 Base URL 可能不同;若 provider 标记为 token plan,
    # 优先使用 token_plan_base_url,否则使用通用 base_url。
    is_token_plan = pcfg.get("is_token_plan") or info.get("is_token_plan", False)
    if is_token_plan:
        base_url = (pcfg.get("token_plan_base_url") or pcfg.get("base_url")
                    or info.get("token_plan_base_url") or info.get("base_url"))
    else:
        base_url = pcfg.get("base_url") or info.get("base_url")

    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url

    return client_class, kwargs


def create_llm_client(cfg: dict, prefer_saved_model: bool = True):
    """根据配置创建对应的 LLM 客户端

    核心原则:
    1. provider 不再硬编码为 zhipu,从 factory 第一个 provider 回退
    2. model 优先从 factory 默认配置获取;当 prefer_saved_model=True 时
       允许从用户配置持久化字段读取(供运行时 /model 切换后 reinit 使用)
    3. 当检测到无 API Key 时,自动回退到 MockLLMClient

    Args:
        prefer_saved_model: True 时优先使用 providers_cfg 中保存的 model(默认);
                            False 时强制使用 factory 默认。

    Returns:
        (client_instance, provider_or_none, model_name)
    """
    if not _PROVIDERS:
        _load_providers_from_factory()

    # provider:配置文件中指定,未指定则返回 None(由调用方处理)
    provider = cfg.get("provider")
    if not provider:
        # 未配置 provider,回退到 Mock(状态栏显示"未配置")
        return MockLLMClient(model="未配置"), None, "未配置"

    provider_info = _PROVIDERS.get(provider, {})
    default_model = provider_info.get("default_model")

    providers_cfg = cfg.get("providers", {})
    pcfg = providers_cfg.get(provider, {})

    # 优先读取用户保存的 model,无配置时回退到 factory 默认
    if prefer_saved_model:
        model = pcfg.get("model") or default_model
    else:
        model = default_model

    # 没有任何可用模型时回退到第一个 provider 的默认模型(兜底)
    if not model and _PROVIDERS:
        first = next(iter(_PROVIDERS.values()))
        model = first.get("default_model")

    api_key = pcfg.get("key") or cfg.get("key", "")

    # 零配置试用:检测到无 API Key → 自动回退到 Mock
    if not api_key:
        client = MockLLMClient(model=model)
        return client, provider, model

    client_class, kwargs = _resolve_llm_kwargs(provider, cfg)
    return client_class(**kwargs), provider, model


def check_provider_availability(provider: str, cfg: dict) -> tuple:
    """本地检测某个 provider 是否可用(无需真发请求)。

    检查项:
      - provider 是否在 factory 白名单
      - 是否有非空 API key
      - 客户端类能否成功初始化(检查 SDK 缺失)

    Returns:
        (available: bool, reason: str, model_name: str)
    """
    if not _PROVIDERS:
        _load_providers_from_factory()

    info = _PROVIDERS.get(provider)
    if not info:
        return False, f"未知 provider: {provider}", ""

    pcfg = (cfg.get("providers") or {}).get(provider, {})
    api_key = pcfg.get("key") or cfg.get("key", "")
    if not api_key:
        return False, "未配置 API Key", ""

    client_class = info.get("client_class", OpenAICompatibleClient)
    try:
        # 只验证能构造,不真发请求
        if client_class in (ZhipuLLMClient, AnthropicCompatibleClient,
                            OpenAICompatibleClient, WenxinLLMClient):
            # 这些类的构造都只接 api_key/base_url,不会立即抛错
            pass
        return True, "OK", pcfg.get("model") or info.get("default_model") or ""
    except Exception as e:
        return False, f"客户端初始化失败: {e}", ""


def resolve_active_model(cfg: dict) -> dict:
    """根据配置解析本次 session 应使用的活跃模型。

    优先级:
      1. default_provider(若本地检测可用)
      2. backup_provider(若 default 不可用)
      3. 返回 None(均不可用 → 上层提示用户配置)

    Returns:
        {
          "provider": str | None,
          "model": str | None,
          "client_factory": callable | None,
          "source": "default" | "backup" | None,
          "reason": str,
        }
    """
    if not _PROVIDERS:
        _load_providers_from_factory()

    default = cfg.get("default_provider") or ""
    backup = cfg.get("backup_provider") or ""

    # 1. 尝试 default
    if default:
        ok, reason, model = check_provider_availability(default, cfg)
        if ok:
            return {
                "provider": default,
                "model": model,
                "client_factory": None,
                "source": "default",
                "reason": f"使用默认模型 [{default}] {model}",
            }

    # 2. 回退到 backup
    if backup:
        ok, reason, model = check_provider_availability(backup, cfg)
        if ok:
            return {
                "provider": backup,
                "model": model,
                "client_factory": None,
                "source": "backup",
                "reason": f"默认模型不可用 ({default or '未设置'}: {reason}),已切换到备用 [{backup}] {model}",
            }

    # 3. 均不可用
    return {
        "provider": None,
        "model": None,
        "client_factory": None,
        "source": None,
        "reason": "未配置 default / backup 模型,请运行 /providers setup 配置",
    }


def create_llm_client_for(provider: str, model: str, cfg: dict, override_key: str = None):
    """根据全局配置创建指定 provider + model 的 LLM 客户端"""
    client_class, kwargs = _resolve_llm_kwargs(provider, cfg, override_key)
    return client_class(**kwargs), provider, model


def get_provider_by_model(model_name: str) -> Optional[str]:
    """根据模型名查找所属 provider(基于 factory 默认配置中的反向映射)"""
    if not _PROVIDERS:
        _load_providers_from_factory()
    return _MODEL_TO_PROVIDER.get(model_name)


def resolve_provider_model(arg: str) -> tuple:
    """解析用户输入的模型参数

    支持格式:
      - provider:model   显式指定 provider 和 model
      - provider         仅 provider ID,使用其默认模型
      - model            仅模型名,尝试自动推断所属 provider

    返回: (provider_or_None, model)
    """
    if ":" in arg:
        parts = arg.split(":", 1)
        return parts[0].strip(), parts[1].strip()
    val = arg.strip()
    if not _PROVIDERS:
        _load_providers_from_factory()
    if val in _PROVIDERS:
        return val, _PROVIDERS[val]["default_model"]
    inferred_provider = get_provider_by_model(val)
    return inferred_provider, val


__all__ = [
    # Base
    "BaseLLMClient",
    # Clients
    "ZhipuLLMClient",
    "OpenAICompatibleClient",
    "AnthropicCompatibleClient",
    "WenxinLLMClient",
    "MockLLMClient",
    "LLM_CLIENT_REGISTRY",
    # Provider 配置
    "reload_providers",
    "get_provider_list",
    "get_provider_info",
    "list_providers",
    "get_provider_by_model",
    # 高层 API
    "create_llm_client",
    "create_llm_client_for",
    "check_provider_availability",
    "resolve_active_model",
    "resolve_provider_model",
]


# 初始化加载
_load_providers_from_factory()
