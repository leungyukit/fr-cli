"""
MetricsPlugin 事件钩子 —— 监听 v3 EventBus 16 类事件

从 fr_cli.core.metrics.plugin 拆出。本 mixin 只含 @hook 装饰的方法:
PluginManager._collect_hooks 在 register 时用 `dir(plugin)` 扫描,
mixin 中定义的方法可被继承发现(装饰元数据挂在函数对象上,与定义位置无关)。
"""
from __future__ import annotations

from fr_cli.v3.core.plugin import hook


class MetricsHooksMixin:
    """16 类事件的自动计数/采样钩子"""

    @hook("tool.invoked")
    def on_tool_invoked(self, event):
        self.counter_inc("tool.invoked", **self._labels_from_event(event))

    @hook("tool.succeeded")
    def on_tool_succeeded(self, event):
        self.counter_inc("tool.succeeded", **self._labels_from_event(event))

    @hook("tool.failed")
    def on_tool_failed(self, event):
        self.counter_inc("tool.failed", **self._labels_from_event(event))

    @hook("tool.blocked")
    def on_tool_blocked(self, event):
        self.counter_inc("tool.blocked", **self._labels_from_event(event))

    @hook("llm.requested")
    def on_llm_requested(self, event):
        self.counter_inc("llm.requested", **self._labels_from_event(event))

    @hook("llm.responded")
    def on_llm_responded(self, event):
        labels = self._labels_from_event(event)
        self.counter_inc("llm.responded", **labels)

        # 响应时间直方图
        rt = event.data.get("response_time")
        if isinstance(rt, (int, float)):
            self.histogram_observe("llm.response_time", float(rt), **labels)

        # token gauge
        usage = event.data.get("usage") or {}
        if "total_tokens" in usage:
            self.gauge_inc("llm.tokens.total", float(usage["total_tokens"]))
        if "prompt_tokens" in usage:
            self.gauge_inc("llm.tokens.prompt", float(usage["prompt_tokens"]))
        if "completion_tokens" in usage:
            self.gauge_inc("llm.tokens.completion", float(usage["completion_tokens"]))

    @hook("llm.failed")
    def on_llm_failed(self, event):
        self.counter_inc("llm.failed", **self._labels_from_event(event))

    @hook("agent.invoked")
    def on_agent_invoked(self, event):
        self.counter_inc("agent.invoked", **self._labels_from_event(event))

    @hook("agent.responded")
    def on_agent_responded(self, event):
        labels = self._labels_from_event(event)
        self.counter_inc("agent.responded", **labels)

    @hook("agent.failed")
    def on_agent_failed(self, event):
        self.counter_inc("agent.failed", **self._labels_from_event(event))

    @hook("command.executed")
    def on_command_executed(self, event):
        self.counter_inc("command.executed", **self._labels_from_event(event))

    @hook("session.created")
    def on_session_created(self, event):
        self.counter_inc("session.created", **self._labels_from_event(event))

    @hook("session.saved")
    def on_session_saved(self, event):
        self.counter_inc("session.saved", **self._labels_from_event(event))

    @hook("app.started")
    def on_app_started(self, event):
        self.counter_inc("app.started", **self._labels_from_event(event))

    @hook("app.stopped")
    def on_app_stopped(self, event):
        self.counter_inc("app.stopped", **self._labels_from_event(event))

    @hook("*", priority=-1000)
    def on_any(self, event):
        """任意事件计数(便于总流量统计)"""
        with self._lock:
            self._total_events += 1
