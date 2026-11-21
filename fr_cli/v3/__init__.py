"""
fr-cli v3 基础设施 —— 渐进式架构重构(生产接线部分)

- EventBus(events)—— 事件驱动,取代直接函数调用 [已接线: core/events, core/metrics, web/console]
- Plugin(plugin)—— 规范化插件接口 + hook 装饰器 [已接线: core/metrics/plugin]

注: container(依赖注入) / lifecycle(生命周期) / provider(LLM 抽象) /
pipeline(流式处理) / errors(错误族) / builtin_plugins 等未接线设施
已在死代码清理中移除——生产代码零引用, 仅存自引用测试, 属预支复杂度。
后续确需引入时按真实需求重建, 并在接线当月补生产调用。
"""
from fr_cli.v3.core.events import (
    Event, EventBus, Events, bus, emit, on,
)
from fr_cli.v3.core.plugin import (
    Plugin, PluginManager, hook,
    global_plugin_manager, reset_global_plugin_manager,
)

__all__ = [
    # events
    "Event", "EventBus", "Events", "bus", "emit", "on",
    # plugin
    "Plugin", "PluginManager", "hook",
    "global_plugin_manager", "reset_global_plugin_manager",
]


__version__ = "3.0.0"
