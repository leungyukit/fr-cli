"""
fr-cli v3.0 —— 渐进式架构重构

新增基础架构,完全向后兼容 v2.x:
- EventBus(events)—— 事件驱动,取代直接函数调用
- Container(container)—— 依赖注入,取代 AppState 上帝对象
- Lifecycle(lifecycle)—— 应用生命周期,统一 start/stop
- Provider(provider)—— 统一 LLM/Tool/Resource/Prompt 抽象
- Plugin(plugin)—— 规范化插件接口
- Pipeline(pipeline)—— 流式处理

设计文档:fr_cli/v3/README.md
"""
from fr_cli.v3.core.events import (
    Event, EventBus, Events, bus, emit, on,
)
from fr_cli.v3.core.errors import (
    FrCliError, ConfigError, ProviderError, LLMError, LLMTimeoutError,
    LLMRateLimitError, LLMContextOverflowError,
    ToolError, ToolNotFoundError, ToolPermissionDeniedError,
    MCPError, PluginError, SecurityError, VFSError, NetworkError,
    NotFoundError, ValidationError,
    ErrorAggregator, to_frcli_error, collect_errors,
)
from fr_cli.v3.core.container import (
    Container, Registration,
    global_container, reset_global_container,
)
from fr_cli.v3.core.lifecycle import Lifecycle, LifecyclePhase, App
from fr_cli.v3.core.provider import (
    Provider, BaseProvider,
    ProviderRequest, ProviderResponse,
    LLMRequest, ToolRequest, ResourceRequest, PromptRequest,
    ProviderRegistry, ToolProviderAdapter,
    global_registry, reset_global_registry,
)
from fr_cli.v3.core.plugin import (
    Plugin, PluginManager, hook,
    LoggingPlugin, MetricsPlugin,
    global_plugin_manager, reset_global_plugin_manager,
)
from fr_cli.v3.core.pipeline import (
    Chunk, PipelineRequest, Pipeline, PipelineManager,
    pipeline, stream_to_callback, collect_stream,
    global_pipeline_manager, reset_global_pipeline_manager,
)

__all__ = [
    # events
    "Event", "EventBus", "Events", "bus", "emit", "on",
    # errors
    "FrCliError", "ConfigError", "ProviderError",
    "LLMError", "LLMTimeoutError", "LLMRateLimitError", "LLMContextOverflowError",
    "ToolError", "ToolNotFoundError", "ToolPermissionDeniedError",
    "MCPError", "PluginError", "SecurityError", "VFSError", "NetworkError",
    "NotFoundError", "ValidationError",
    "ErrorAggregator", "to_frcli_error", "collect_errors",
    # container
    "Container", "Registration", "global_container", "reset_global_container",
    # lifecycle
    "Lifecycle", "LifecyclePhase", "App",
    # provider
    "Provider", "BaseProvider",
    "ProviderRequest", "ProviderResponse",
    "LLMRequest", "ToolRequest", "ResourceRequest", "PromptRequest",
    "ProviderRegistry", "ToolProviderAdapter",
    "global_registry", "reset_global_registry",
    # plugin
    "Plugin", "PluginManager", "hook",
    "LoggingPlugin", "MetricsPlugin",
    "global_plugin_manager", "reset_global_plugin_manager",
    # pipeline
    "Chunk", "PipelineRequest", "Pipeline", "PipelineManager",
    "pipeline", "stream_to_callback", "collect_stream",
    "global_pipeline_manager", "reset_global_pipeline_manager",
]


__version__ = "3.0.0"
