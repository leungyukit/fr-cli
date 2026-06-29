"""
统一指标收集 —— MetricsPlugin 入口

通过 v3 EventBus 自动收集应用指标,无需在每个调用点埋点。

模块拆分:
- fr_cli.core.metrics.plugin:MetricsPlugin 类本身(counter/histogram/timer/gauge + 事件钩子 + 导出)
- fr_cli.core.metrics:本文件(全局单例 + 安装 / 卸载 / 查询)

四类指标:
  - Counter:    单调递增计数(如 tool.invoked.total)
  - Histogram:  数值分布(桶 + p50/p95/p99),如 llm.response_time
  - Timer:      操作耗时统计(count/total/min/max/avg)
  - Gauge:      瞬时值(可增可减,如当前 token 使用)
"""
from __future__ import annotations

import threading
from typing import Optional, Tuple

from fr_cli.v3.core.events import EventBus
from fr_cli.v3.core.plugin import PluginManager

from fr_cli.core.metrics.plugin import MetricsPlugin, DEFAULT_BUCKETS

# Prometheus 直方图默认桶(秒):re-export
DEFAULT_BUCKETS = DEFAULT_BUCKETS

# ---------------- 全局单例 ----------------

_global_metrics: Optional[MetricsPlugin] = None
_global_lock = threading.Lock()


def get_metrics() -> Optional[MetricsPlugin]:
    """获取全局 MetricsPlugin 实例(已注册过则返回,否则 None)"""
    return _global_metrics


def install_metrics(bus=None, plugin_manager=None,
                    buckets: Tuple[float, ...] = DEFAULT_BUCKETS) -> MetricsPlugin:
    """安装 MetricsPlugin 到 v3 bus(幂等)

    Args:
        bus: v3 EventBus,默认全局单例
        plugin_manager: v3 PluginManager,可选。如果提供则注册到该 manager;
                       默认创建一个新的并绑定全局 EventBus
        buckets: 直方图桶(秒)

    Returns:
        已安装(或已存在)的 MetricsPlugin 实例
    """
    global _global_metrics
    if _global_metrics is not None:
        return _global_metrics

    with _global_lock:
        if _global_metrics is not None:
            return _global_metrics

        if bus is None:
            bus = EventBus.instance()
        if plugin_manager is None:
            plugin_manager = PluginManager()
        # 总是确保 plugin_manager 绑定了 bus,否则 register 时 hook 不会生效
        try:
            if getattr(plugin_manager, "_event_bus", None) is None:
                plugin_manager.set_event_bus(bus)
        except Exception:
            pass

        plugin = MetricsPlugin(buckets=buckets)
        plugin_manager.register(plugin)

        _global_metrics = plugin
        return plugin


def reset_metrics_for_testing():
    """重置全局 metrics 引用(测试用)"""
    global _global_metrics
    with _global_lock:
        _global_metrics = None


__all__ = [
    "MetricsPlugin",
    "DEFAULT_BUCKETS",
    "install_metrics",
    "get_metrics",
    "reset_metrics_for_testing",
]
