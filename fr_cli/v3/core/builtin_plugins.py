"""
v3 内置插件集合

拆分自 v3/core/plugin.py,把示例/常用插件集中到一个文件,便于:
- 用户阅读(独立文件,不被 PluginManager 细节干扰)
- 扩展(新增 builtin plugin 只需在本文件添加类)
- 测试(单独 import 测试)

包含:
- LoggingPlugin:把关键事件记到 logger
- MetricsPlugin: 简单计数器示例(生产版在 fr_cli.core.metrics.MetricsPlugin)
"""
from __future__ import annotations

import logging
from typing import Dict

from fr_cli.v3.core.plugin import Plugin, hook

log = logging.getLogger(__name__)


class LoggingPlugin(Plugin):
    """默认日志插件:把关键事件记到 logger

    适合调试、审计、与外部日志系统集成。
    """

    name = "logging"
    version = "1.0.0"
    description = "把关键事件记录到 logger"

    @hook("tool.invoked")
    def on_tool_invoked(self, event):
        log.debug(f"[plugin:logging] tool invoked: {event.data.get('name')}")

    @hook("tool.failed")
    def on_tool_failed(self, event):
        log.warning(
            f"[plugin:logging] tool failed: "
            f"{event.data.get('name')}: {event.data.get('error')}"
        )

    @hook("llm.failed")
    def on_llm_failed(self, event):
        log.error(f"[plugin:logging] llm failed: {event.data.get('error')}")

    @hook("app.started")
    def on_app_started(self, event):
        log.info("[plugin:logging] app started")


class MetricsPlugin(Plugin):
    """示例:轻量级计数器插件(只数 tool.* 事件)

    生产环境请使用 fr_cli.core.metrics.MetricsPlugin(支持 counter/histogram/timer/gauge
    + Prometheus 导出 + 多维 label)。
    """

    name = "metrics"
    version = "1.0.0"
    description = "轻量计数器(示例);生产请用 fr_cli.core.metrics.MetricsPlugin"

    def __init__(self):
        self.counters: Dict[str, int] = {}

    @hook("tool.invoked")
    def count_tool(self, event):
        name = event.data.get("name", "unknown")
        self.counters[f"tool.{name}.invoked"] = (
            self.counters.get(f"tool.{name}.invoked", 0) + 1
        )

    @hook("tool.succeeded")
    def count_success(self, event):
        name = event.data.get("name", "unknown")
        self.counters[f"tool.{name}.success"] = (
            self.counters.get(f"tool.{name}.success", 0) + 1
        )

    @hook("tool.failed")
    def count_failure(self, event):
        name = event.data.get("name", "unknown")
        self.counters[f"tool.{name}.failure"] = (
            self.counters.get(f"tool.{name}.failure", 0) + 1
        )

    def metrics_text(self) -> str:
        return "\n".join(f"{k}: {v}" for k, v in sorted(self.counters.items()))
