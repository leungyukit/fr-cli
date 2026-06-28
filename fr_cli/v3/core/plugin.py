"""
v3 Plugin —— 规范化的插件接口

v2.x 插件机制混乱:
- /plugin/<name>.py: 子进程执行(runpy)
- ~/.fr_cli/agents/<name>/agent.py: import 加载
- /addon/plugin.py: 不一致

v3 统一规范:
- 一个 Plugin 类,有 name / version / hooks
- 注册到 PluginManager
- 自动发现 entry_points("fr_cli.plugins")
- hooks 是声明式的(用装饰器标记)

示例:
    class MyPlugin(Plugin):
        name = "my-plugin"
        version = "1.0.0"

        @hook("tool.before_invoke")
        def audit(self, event):
            log.info(f"tool: {event.data['name']}")

    plugin_manager.register(MyPlugin())
"""
from __future__ import annotations

import abc
import logging
import threading
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)


def hook(event_type: str, priority: int = 0):
    """装饰器:把方法标记为某事件的钩子

    用法:
        class MyPlugin(Plugin):
            @hook("tool.before_invoke")
            def audit(self, event): ...

            @hook("app.started", priority=100)
            def first(self, event): ...
    """
    def decorator(func: Callable) -> Callable:
        # 把 hook 元数据附在函数上
        func._hook_metadata = {
            "event_type": event_type,
            "priority": priority,
        }
        return func
    return decorator


class Plugin(abc.ABC):
    """插件基类

    插件必须:
    - 实现 name(唯一标识)
    - 可选实现 version / description
    - 用 @hook 装饰器声明钩子
    """

    name: str = ""
    version: str = "0.0.0"
    description: str = ""

    def setup(self):
        """插件加载时调用(可选)"""
        pass

    def teardown(self):
        """插件卸载时调用(可选)"""
        pass


class PluginManager:
    """插件管理器"""

    def __init__(self):
        self._plugins: Dict[str, Plugin] = {}
        self._hooks: Dict[str, List] = {}  # event_type -> [(priority, plugin, method)]
        self._lock = threading.RLock()
        self._event_bus = None
        self._enabled: Dict[str, bool] = {}

    def set_event_bus(self, bus):
        """绑定 EventBus(注册插件的钩子到总线)"""
        self._event_bus = bus

    def register(self, plugin: Plugin, override: bool = True,
                 enabled: bool = True) -> bool:
        """注册插件"""
        if not plugin.name:
            log.warning("plugin has no name, skip")
            return False

        with self._lock:
            if plugin.name in self._plugins and not override:
                log.debug(f"plugin {plugin.name} already registered")
                return False

            self._plugins[plugin.name] = plugin
            self._enabled[plugin.name] = enabled
            self._collect_hooks(plugin)

            # 调用 setup
            try:
                plugin.setup()
            except Exception as e:
                log.error(f"plugin {plugin.name} setup failed: {e}")

            # 注册到 EventBus(若绑定)
            if self._event_bus is not None:
                self._bind_hooks_to_bus(plugin)

            log.info(f"plugin registered: {plugin.name} v{plugin.version}")
            return True

    def _collect_hooks(self, plugin: Plugin):
        """扫描插件方法,收集所有 @hook 装饰的钩子"""
        for attr_name in dir(plugin):
            try:
                attr = getattr(plugin, attr_name)
            except AttributeError:
                continue
            if not callable(attr):
                continue
            meta = getattr(attr, "_hook_metadata", None)
            if meta is None:
                continue
            event_type = meta["event_type"]
            priority = meta["priority"]
            with self._lock:
                self._hooks.setdefault(event_type, []).append((priority, plugin, attr))
                self._hooks[event_type].sort(key=lambda x: -x[0])

    def _bind_hooks_to_bus(self, plugin: Plugin):
        """把插件钩子绑定到 EventBus"""
        if self._event_bus is None:
            return
        for attr_name in dir(plugin):
            attr = getattr(plugin, attr_name, None)
            meta = getattr(attr, "_hook_metadata", None) if attr else None
            if meta is None:
                continue
            event_type = meta["event_type"]
            priority = meta["priority"]

            def make_handler(method):
                def handler(event):
                    if not self._enabled.get(plugin.name, True):
                        return
                    try:
                        method(event)
                    except Exception as e:
                        log.error(f"plugin {plugin.name} hook {method.__name__} failed: {e}",
                                  exc_info=True)
                return handler

            self._event_bus.on(event_type, make_handler(attr), priority=priority)

    def unregister(self, name: str) -> bool:
        """注销插件"""
        with self._lock:
            plugin = self._plugins.pop(name, None)
            if plugin is None:
                return False
            # 清理钩子
            for event_type in list(self._hooks.keys()):
                self._hooks[event_type] = [
                    (p, pl, m) for (p, pl, m) in self._hooks[event_type]
                    if pl.name != name
                ]
                if not self._hooks[event_type]:
                    del self._hooks[event_type]
            # 调用 teardown
            try:
                plugin.teardown()
            except Exception as e:
                log.error(f"plugin {name} teardown failed: {e}")
            log.info(f"plugin unregistered: {name}")
            return True

    def enable(self, name: str) -> bool:
        """启用插件"""
        with self._lock:
            if name in self._plugins:
                self._enabled[name] = True
                return True
            return False

    def disable(self, name: str) -> bool:
        """禁用插件"""
        with self._lock:
            if name in self._plugins:
                self._enabled[name] = False
                return True
            return False

    def is_enabled(self, name: str) -> bool:
        with self._lock:
            return self._enabled.get(name, False)

    def get(self, name: str) -> Optional[Plugin]:
        with self._lock:
            return self._plugins.get(name)

    def list_plugins(self) -> List[Dict[str, Any]]:
        """列出所有插件"""
        with self._lock:
            return [
                {
                    "name": p.name,
                    "version": p.version,
                    "description": p.description,
                    "enabled": self._enabled.get(p.name, True),
                }
                for p in self._plugins.values()
            ]

    def list_hooks(self, event_type: Optional[str] = None) -> Dict[str, List]:
        """列出所有钩子

        Returns:
            {event_type: [(plugin_name, method_name, priority), ...]}
        """
        with self._lock:
            if event_type:
                return {event_type: [
                    (pl.name, m.__name__, prio)
                    for prio, pl, m in self._hooks.get(event_type, [])
                ]}
            return {
                e_type: [
                    (pl.name, m.__name__, prio)
                    for prio, pl, m in hooks
                ]
                for e_type, hooks in self._hooks.items()
            }

    def discover(self):
        """从 entry_points 自动发现插件(setuptools 风格)

        第三方插件可以在 pyproject.toml 注册:
            [project.entry-points."fr_cli.plugins"]
            my_plugin = "my_pkg.plugin:MyPlugin"
        """
        try:
            from importlib.metadata import entry_points
            eps = entry_points(group="fr_cli.plugins")
        except (ImportError, AttributeError):
            log.debug("entry_points discovery unavailable")
            return []

        count = 0
        for ep in eps:
            try:
                cls_or_obj = ep.load()
                if isinstance(cls_or_obj, type):
                    plugin = cls_or_obj()
                else:
                    plugin = cls_or_obj
                if isinstance(plugin, Plugin):
                    if self.register(plugin):
                        count += 1
            except Exception as e:
                log.error(f"failed to load plugin {ep.name}: {e}")
        log.info(f"discovered {count} plugin(s)")
        return count

    def clear(self):
        """清空(测试用)"""
        with self._lock:
            for name in list(self._plugins.keys()):
                self.unregister(name)


# 全局 Plugin Manager
_global_pm: Optional[PluginManager] = None
_pm_lock = threading.Lock()


def global_plugin_manager() -> PluginManager:
    global _global_pm
    with _pm_lock:
        if _global_pm is None:
            _global_pm = PluginManager()
            # 自动绑定 EventBus
            try:
                from fr_cli.v3.core.events import EventBus
                _global_pm.set_event_bus(EventBus.instance())
            except ImportError:
                pass
        return _global_pm


def reset_global_plugin_manager():
    global _global_pm
    with _pm_lock:
        if _global_pm is not None:
            _global_pm.clear()
        _global_pm = None


# ---------------- 内置插件 ----------------

class LoggingPlugin(Plugin):
    """默认日志插件:把关键事件记到 logger"""

    name = "logging"
    version = "1.0.0"
    description = "把关键事件记录到 logger"

    @hook("tool.invoked")
    def on_tool_invoked(self, event):
        log.debug(f"[plugin:logging] tool invoked: {event.data.get('name')}")

    @hook("tool.failed")
    def on_tool_failed(self, event):
        log.warning(f"[plugin:logging] tool failed: {event.data.get('name')}: {event.data.get('error')}")

    @hook("llm.failed")
    def on_llm_failed(self, event):
        log.error(f"[plugin:logging] llm failed: {event.data.get('error')}")

    @hook("app.started")
    def on_app_started(self, event):
        log.info("[plugin:logging] app started")


class MetricsPlugin(Plugin):
    """示例:指标收集插件

    实际生产中可以接到 Prometheus / StatsD / 自家系统。
    """

    name = "metrics"
    version = "1.0.0"
    description = "指标收集(示例)"

    def __init__(self):
        self.counters: Dict[str, int] = {}

    @hook("tool.invoked")
    def count_tool(self, event):
        name = event.data.get("name", "unknown")
        self.counters[f"tool.{name}.invoked"] = self.counters.get(f"tool.{name}.invoked", 0) + 1

    @hook("tool.succeeded")
    def count_success(self, event):
        name = event.data.get("name", "unknown")
        self.counters[f"tool.{name}.success"] = self.counters.get(f"tool.{name}.success", 0) + 1

    @hook("tool.failed")
    def count_failure(self, event):
        name = event.data.get("name", "unknown")
        self.counters[f"tool.{name}.failure"] = self.counters.get(f"tool.{name}.failure", 0) + 1

    def metrics_text(self) -> str:
        return "\n".join(f"{k}: {v}" for k, v in sorted(self.counters.items()))
