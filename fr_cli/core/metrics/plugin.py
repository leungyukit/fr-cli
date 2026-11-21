"""
MetricsPlugin 类 —— 4 类指标(counter/histogram/timer/gauge) + 事件钩子 + 多格式导出

这是核心类,负责:
- 内部状态存储(thread-safe)
- 监听 v3 EventBus 自动收 16 类事件
- 3 种导出格式:Prometheus 文本 / JSON / 人类可读摘要

模块拆分(原单文件 485 行,按职责拆为 4 个 mixin):
- primitives.py: counter/histogram/timer/gauge 原语 + 状态存储
- hooks.py:      16 个 @hook 事件处理器
- render.py:     metrics_text / metrics_json / metrics_summary / reset
- labels.py:     标签提取与序列化(_EXCLUDED_LABEL_KEYS 等)

本文件只保留 DEFAULT_BUCKETS 与类组装,公开导入路径不变:
    from fr_cli.core.metrics import MetricsPlugin
    from fr_cli.core.metrics.plugin import MetricsPlugin, DEFAULT_BUCKETS
"""
from __future__ import annotations

from typing import Tuple

from fr_cli.v3.core.plugin import Plugin

from fr_cli.core.metrics.primitives import MetricsPrimitivesMixin
from fr_cli.core.metrics.hooks import MetricsHooksMixin
from fr_cli.core.metrics.render import MetricsRenderMixin
from fr_cli.core.metrics.labels import MetricsLabelsMixin


# Prometheus 直方图默认桶(秒)
DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, float("inf"))


class MetricsPlugin(
    MetricsLabelsMixin,
    MetricsHooksMixin,
    MetricsRenderMixin,
    MetricsPrimitivesMixin,
    Plugin,
):
    """生产级指标收集插件

    用法:
        from fr_cli.core.metrics import MetricsPlugin, install_metrics
        pm = install_metrics(bus)  # 一行启动
        # ... 业务代码 ...
        # pm.metrics_text() / pm.metrics_json() / pm.metrics_summary()

    或直接注册:
        from fr_cli.v3.core.plugin import PluginManager
        pm = PluginManager()
        pm.register(MetricsPlugin())

    标签(label)自动提取:
        - event.data 中的字符串字段会被当作标签
        - 默认排除:error, message, description, result, args, _source, _sub
    """

    name = "metrics"
    version = "2.0.0"
    description = "生产级指标收集(counter/histogram/timer/gauge + Prometheus 导出)"

    def __init__(self, buckets: Tuple[float, ...] = DEFAULT_BUCKETS):
        # 显式调用 primitives mixin 的初始化(不依赖 MRO 顺序,
        # 也不用 super()——Plugin 基类没有 __init__,super() 链容易踩坑)
        MetricsPrimitivesMixin.__init__(self, buckets)
