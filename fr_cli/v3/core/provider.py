"""
v3 Provider —— 统一 Provider 抽象

v2.x:LLMClient / Tool / Resource / Prompt 各有不同接口
v3:统一 Provider 协议 + Request/Response dataclass

所有 Provider 都可以:
- invoke(request) → response(异步)
- stream(request) → AsyncIterator[chunk](可选,流式)
- 订阅 EventBus(状态变化时发事件)
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Protocol, runtime_checkable


# ---------------- Request / Response ----------------

@dataclass
class ProviderRequest:
    """统一的 Provider 请求基类

    子类按需扩展:
    - LLMRequest: messages, model, temperature, ...
    - ToolRequest: tool_name, arguments
    - ResourceRequest: uri
    - PromptRequest: prompt_name, arguments
    """
    type: str = "base"
    data: Dict[str, Any] = field(default_factory=dict)
    source: Optional[str] = None  # 调用来源
    trace_id: Optional[str] = None  # 用于追踪


@dataclass
class ProviderResponse:
    """统一的 Provider 响应基类"""
    ok: bool = True
    data: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "data": self.data,
            "error": self.error,
            "metadata": self.metadata,
            "duration_ms": self.duration_ms,
        }


# ---------------- 具体 Request / Response ----------------

@dataclass
class LLMRequest(ProviderRequest):
    type: str = "llm"
    messages: List[Dict[str, Any]] = field(default_factory=list)
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 4096
    stream: bool = False
    tools: Optional[List[Dict[str, Any]]] = None  # function calling

    def __init__(self, messages=None, model=None, temperature=0.7,
                 max_tokens=4096, stream=False, tools=None,
                 source=None, trace_id=None, data=None):
        super().__init__(type="llm", data=data or {}, source=source, trace_id=trace_id)
        self.messages = messages or []
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.stream = stream
        self.tools = tools


@dataclass
class ToolRequest(ProviderRequest):
    type: str = "tool"
    tool_name: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)

    def __init__(self, tool_name="", arguments=None, source=None, trace_id=None, data=None):
        super().__init__(type="tool", data=data or {}, source=source, trace_id=trace_id)
        self.tool_name = tool_name
        self.arguments = arguments or {}


@dataclass
class ResourceRequest(ProviderRequest):
    type: str = "resource"
    uri: str = ""

    def __init__(self, uri="", source=None, trace_id=None, data=None):
        super().__init__(type="resource", data=data or {}, source=source, trace_id=trace_id)
        self.uri = uri


@dataclass
class PromptRequest(ProviderRequest):
    type: str = "prompt"
    prompt_name: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)

    def __init__(self, prompt_name="", arguments=None, source=None, trace_id=None, data=None):
        super().__init__(type="prompt", data=data or {}, source=source, trace_id=trace_id)
        self.prompt_name = prompt_name
        self.arguments = arguments or {}


# ---------------- Provider 协议 ----------------

@runtime_checkable
class Provider(Protocol):
    """Provider 协议

    所有 Provider(LLM / Tool / Resource / Prompt)都实现这个接口。
    v3 不强制 ABC,因为 Protocol 支持 duck typing + runtime_checkable。
    """
    name: str
    type: str  # "llm" / "tool" / "resource" / "prompt"

    async def invoke(self, request: ProviderRequest) -> ProviderResponse:
        """同步调用"""
        ...

    async def stream(self, request: ProviderRequest) -> AsyncIterator[Any]:
        """流式调用(可选,不实现则 raise NotImplementedError)"""
        ...

    def capabilities(self) -> Dict[str, Any]:
        """返回 Provider 能力描述(给 AI 看)"""
        ...


class BaseProvider(abc.ABC):
    """Provider 基类(可选继承,提供一些默认实现)"""

    name: str = "base"
    type: str = "base"

    async def invoke(self, request: ProviderRequest) -> ProviderResponse:
        """子类必须实现"""
        raise NotImplementedError

    async def stream(self, request: ProviderRequest):
        """默认实现:调用 invoke 后 yield 整个结果"""
        result = await self.invoke(request)
        yield result

    def capabilities(self) -> Dict[str, Any]:
        """默认:返回基本信息"""
        return {"name": self.name, "type": self.type}


# ---------------- Registry ----------------

class ProviderRegistry:
    """Provider 注册中心(按 name 和 type 索引)"""

    def __init__(self):
        import threading
        self._providers: Dict[str, Provider] = {}
        self._by_type: Dict[str, Dict[str, Provider]] = {}
        self._lock = threading.RLock()

    def register(self, provider: Provider, override: bool = True) -> None:
        with self._lock:
            if provider.name in self._providers and not override:
                return
            self._providers[provider.name] = provider
            self._by_type.setdefault(provider.type, {})[provider.name] = provider

    def get(self, name: str) -> Optional[Provider]:
        with self._lock:
            return self._providers.get(name)

    def by_type(self, type: str) -> Dict[str, Provider]:
        with self._lock:
            return dict(self._by_type.get(type, {}))

    def names(self) -> List[str]:
        with self._lock:
            return list(self._providers.keys())

    def unregister(self, name: str) -> bool:
        with self._lock:
            p = self._providers.pop(name, None)
            if p:
                self._by_type.get(p.type, {}).pop(name, None)
                return True
            return False

    def clear(self):
        with self._lock:
            self._providers.clear()
            self._by_type.clear()


# 全局 Registry
_global_registry: Optional[ProviderRegistry] = None


def global_registry() -> ProviderRegistry:
    global _global_registry
    if _global_registry is None:
        _global_registry = ProviderRegistry()
    return _global_registry


def reset_global_registry():
    global _global_registry
    _global_registry = None


# ---------------- 适配器:把 v2 工具转 Provider ----------------

class ToolProviderAdapter(BaseProvider):
    """把 v2 工具(由 registry 调度)适配成 Provider"""

    type = "tool"

    def __init__(self, tool_name: str, v2_registry=None):
        self.name = tool_name
        self._v2_registry = v2_registry

    async def invoke(self, request: ToolRequest) -> ProviderResponse:
        if self._v2_registry is None:
            try:
                from fr_cli.command.registry import get_registry
                self._v2_registry = get_registry()
            except ImportError:
                return ProviderResponse(ok=False, error="v2 registry unavailable")

        result, err = self._v2_registry.dispatch_tool(
            self.name, request.arguments,
            msgs=request.data.get("msgs"),
        )
        return ProviderResponse(
            ok=err is None,
            data=result,
            error=err,
        )

    def capabilities(self) -> Dict[str, Any]:
        tool = self._v2_registry.get_tool(self.name) if self._v2_registry else None
        if not tool:
            return {"name": self.name, "type": self.type}
        return {
            "name": self.name,
            "type": self.type,
            "description": tool.get("description", ""),
            "params": tool.get("params", {}),
        }
