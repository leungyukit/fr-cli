"""
统一指标收集 —— MetricsPlugin 增强版

通过 v3 EventBus 自动收集应用指标,无需在每个调用点埋点。

四类指标:
  - Counter:    单调递增计数(如 tool.invoked.total)
  - Histogram:  数值分布(桶 + p50/p95/p99),如 llm.response_time
  - Timer:      操作耗时统计(count/total/min/max/avg),如 tool.duration
  - Gauge:      瞬时值(可增可减,如当前 token 使用)

事件覆盖:
  - tool.* / llm.* / agent.* / command.* / session.* / app.*

导出格式:
  - metrics_text()  : Prometheus 风格(文本)
  - metrics_json()  : JSON 快照
  - metrics_summary(): 人类可读摘要

持久化(可选):
  - snapshot()/restore():把当前指标状态序列化到 JSON
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from fr_cli.v3.core.plugin import Plugin, hook


# Prometheus 直方图默认桶(秒)
DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, float("inf"))


class MetricsPlugin(Plugin):
    """生产级指标收集插件

    用法:
        from fr_cli.core.metrics import MetricsPlugin, install_metrics
        pm = install_metrics(bus)  # 一行启动
        # ... 业务代码 ...
        # pm.metrics_text() / metrics_json() / metrics_summary()

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
        super().__init__()
        self._buckets = buckets
        self._lock = threading.RLock()
        # Counter: (name, frozenset(labels)) -> int
        self._counters: Dict[Tuple[str, frozenset], int] = defaultdict(int)
        # Histogram: name -> {buckets: [(le, count)], sum, count, labels_variants}
        self._histograms: Dict[str, Dict[str, Any]] = {}
        # Timer: name -> {count, total, min, max, labels_variants}
        self._timers: Dict[str, Dict[str, Any]] = {}
        # Gauge: name -> value(单值)
        self._gauges: Dict[str, float] = {}
        # 元数据:started_at / total_events
        self._started_at = time.time()
        self._total_events = 0

    # ---------------- Counter ----------------

    def counter_inc(self, metric_name: str, value: int = 1, **labels):
        """增加计数器

        Args:
            metric_name: 指标名(如 "tool.invoked"),重命名避免与 event.data["name"] 冲突
            value: 增量(默认 1)
            **labels: 标签 key=value
        """
        key = (metric_name, self._freeze_labels(labels))
        with self._lock:
            self._counters[key] += value

    def counter_get(self, metric_name: str, **labels) -> int:
        """获取计数器当前值(没有时返回 0)"""
        key = (metric_name, self._freeze_labels(labels))
        with self._lock:
            return self._counters.get(key, 0)

    # ---------------- Histogram ----------------

    def histogram_observe(self, name: str, value: float, **labels):
        """记录一个直方图观察值

        Args:
            name: 指标名(如 "llm.response_time")
            value: 观察值(如 1.23 秒)
            **labels: 标签
        """
        label_key = self._freeze_labels(labels)
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = {
                    "buckets": defaultdict(int),
                    "sum": 0.0,
                    "count": 0,
                    "label_keys": set(),
                }
            h = self._histograms[name]
            for le in self._buckets:
                if value <= le:
                    h["buckets"][le] += 1
            h["sum"] += value
            h["count"] += 1
            h["label_keys"].add(label_key)

    def histogram_percentile(self, name: str, p: float) -> Optional[float]:
        """估算直方图分位数(用桶插值法)

        Args:
            p: 分位数 0~1(如 0.95)
        """
        with self._lock:
            h = self._histograms.get(name)
            if not h or h["count"] == 0:
                return None
            target = h["count"] * p
            for le in self._buckets:
                if h["buckets"][le] >= target:
                    return le
            return self._buckets[-2] if len(self._buckets) > 1 else self._buckets[0]

    # ---------------- Timer ----------------

    def timer_observe(self, name: str, duration: float, **labels):
        """记录一个耗时(秒)

        Args:
            name: 指标名(如 "tool.duration")
            duration: 耗时(秒)
            **labels: 标签
        """
        label_key = self._freeze_labels(labels)
        with self._lock:
            if name not in self._timers:
                self._timers[name] = {
                    "count": 0,
                    "total": 0.0,
                    "min": float("inf"),
                    "max": -float("inf"),
                    "label_keys": set(),
                }
            t = self._timers[name]
            t["count"] += 1
            t["total"] += duration
            t["min"] = min(t["min"], duration)
            t["max"] = max(t["max"], duration)
            t["label_keys"].add(label_key)

    def timer_summary(self, name: str) -> Optional[Dict[str, float]]:
        """获取 timer 摘要(count/total/min/max/avg)"""
        with self._lock:
            t = self._timers.get(name)
            if not t or t["count"] == 0:
                return None
            return {
                "count": t["count"],
                "total": round(t["total"], 6),
                "min": round(t["min"], 6) if t["min"] != float("inf") else 0,
                "max": round(t["max"], 6) if t["max"] != -float("inf") else 0,
                "avg": round(t["total"] / t["count"], 6),
            }

    # ---------------- Gauge ----------------

    def gauge_set(self, name: str, value: float):
        """设置仪表值"""
        with self._lock:
            self._gauges[name] = value

    def gauge_inc(self, name: str, value: float = 1.0):
        """增加仪表值"""
        with self._lock:
            self._gauges[name] = self._gauges.get(name, 0.0) + value

    def gauge_dec(self, name: str, value: float = 1.0):
        """减少仪表值"""
        with self._lock:
            self._gauges[name] = self._gauges.get(name, 0.0) - value

    def gauge_get(self, name: str) -> Optional[float]:
        with self._lock:
            return self._gauges.get(name)

    # ---------------- 事件钩子 ----------------

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

    # ---------------- 导出 ----------------

    def metrics_text(self) -> str:
        """Prometheus 风格文本导出"""
        lines = []
        with self._lock:
            # counters
            for (name, label_set), value in sorted(self._counters.items()):
                labels = self._label_set_to_str(label_set)
                lines.append(f"# TYPE {name} counter")
                lines.append(f"{name}{labels} {value}")

            # histograms
            for name, h in sorted(self._histograms.items()):
                lines.append(f"# TYPE {name} histogram")
                for le in self._buckets:
                    le_str = "+Inf" if le == float("inf") else str(le)
                    # 注意:Prometheus 桶是累积的
                    cumulative = sum(h["buckets"][b] for b in self._buckets if b <= le)
                    lines.append(f'{name}_bucket{{le="{le_str}"}} {cumulative}')
                lines.append(f'{name}_sum {round(h["sum"], 6)}')
                lines.append(f'{name}_count {h["count"]}')

            # timers
            for name, t in sorted(self._timers.items()):
                lines.append(f"# TYPE {name} summary")
                lines.append(f'{name}_count {t["count"]}')
                lines.append(f'{name}_sum {round(t["total"], 6)}')
                if t["min"] != float("inf"):
                    lines.append(f'{name}_min {round(t["min"], 6)}')
                if t["max"] != -float("inf"):
                    lines.append(f'{name}_max {round(t["max"], 6)}')
                avg = round(t["total"] / t["count"], 6) if t["count"] > 0 else 0
                lines.append(f'{name}_avg {avg}')

            # gauges
            for name, value in sorted(self._gauges.items()):
                lines.append(f"# TYPE {name} gauge")
                lines.append(f"{name} {value}")

            # meta
            lines.append("# meta")
            lines.append(f"# started_at: {self._started_at}")
            lines.append(f"# total_events: {self._total_events}")
            lines.append(f"# uptime_seconds: {round(time.time() - self._started_at, 2)}")

        return "\n".join(lines)

    def metrics_json(self) -> Dict[str, Any]:
        """JSON 快照"""
        with self._lock:
            result: Dict[str, Any] = {
                "counters": {},
                "histograms": {},
                "timers": {},
                "gauges": dict(self._gauges),
                "meta": {
                    "started_at": self._started_at,
                    "uptime_seconds": round(time.time() - self._started_at, 2),
                    "total_events": self._total_events,
                    "buckets": list(self._buckets),
                },
            }

            # counters 按 name 分组
            counters_by_name: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for (name, label_set), value in self._counters.items():
                counters_by_name[name].append({
                    "labels": self._label_set_to_dict(label_set),
                    "value": value,
                })
            result["counters"] = dict(counters_by_name)

            # histograms
            for name, h in self._histograms.items():
                # 计算分位数
                percentiles = {}
                for p in (0.5, 0.95, 0.99):
                    target = h["count"] * p
                    value = None
                    for le in self._buckets:
                        if h["buckets"][le] >= target:
                            value = le
                            break
                    percentiles[f"p{int(p*100)}"] = value

                result["histograms"][name] = {
                    "count": h["count"],
                    "sum": round(h["sum"], 6),
                    "avg": round(h["sum"] / h["count"], 6) if h["count"] > 0 else 0,
                    "percentiles": percentiles,
                    "buckets": {str(le): c for le, c in h["buckets"].items()},
                }

            # timers
            for name, t in self._timers.items():
                result["timers"][name] = self.timer_summary(name)

            return result

    def metrics_summary(self) -> str:
        """人类可读摘要"""
        with self._lock:
            lines = ["=" * 60]
            lines.append(f"📊 Metrics Summary (uptime: {round(time.time() - self._started_at, 1)}s)")
            lines.append(f"   Total events received: {self._total_events}")
            lines.append("=" * 60)

            # counters
            if self._counters:
                lines.append("\n🔢 Counters:")
                # 按 name 分组
                by_name: Dict[str, List[Tuple[frozenset, int]]] = defaultdict(list)
                for (name, label_set), value in self._counters.items():
                    by_name[name].append((label_set, value))
                for name in sorted(by_name.keys()):
                    items = by_name[name]
                    if len(items) == 1 and not items[0][0]:
                        # 没标签,直接显示
                        lines.append(f"   {name}: {items[0][1]}")
                    else:
                        total = sum(v for _, v in items)
                        lines.append(f"   {name}: {total} ({len(items)} variants)")

            # histograms
            if self._histograms:
                lines.append("\n📈 Histograms:")
                for name, h in sorted(self._histograms.items()):
                    if h["count"] == 0:
                        continue
                    p50 = self.histogram_percentile(name, 0.5)
                    p95 = self.histogram_percentile(name, 0.95)
                    p99 = self.histogram_percentile(name, 0.99)
                    avg = h["sum"] / h["count"]
                    lines.append(
                        f"   {name}: n={h['count']} avg={avg:.3f}s "
                        f"p50={p50}s p95={p95}s p99={p99}s"
                    )

            # timers
            if self._timers:
                lines.append("\n⏱️  Timers:")
                for name in sorted(self._timers.keys()):
                    s = self.timer_summary(name)
                    if s:
                        lines.append(
                            f"   {name}: n={s['count']} avg={s['avg']:.3f}s "
                            f"min={s['min']:.3f}s max={s['max']:.3f}s"
                        )

            # gauges
            if self._gauges:
                lines.append("\n📍 Gauges:")
                for name, value in sorted(self._gauges.items()):
                    lines.append(f"   {name}: {value}")

            if len(lines) == 4:  # 只有 header
                lines.append("\n(no metrics recorded yet)")

            return "\n".join(lines)

    def reset(self):
        """清空所有指标(测试用)"""
        with self._lock:
            self._counters.clear()
            self._histograms.clear()
            self._timers.clear()
            self._gauges.clear()
            self._total_events = 0
            self._started_at = time.time()

    # ---------------- 内部工具 ----------------

    # 排除的字段(不会当作 label,通常值很大或不标准化)
    _EXCLUDED_LABEL_KEYS = frozenset({
        "error", "message", "description", "result", "args",
        "_source", "_sub", "metadata", "kwargs", "prompt_preview",
        "tool_args", "output_len", "response_time",
    })

    def _labels_from_event(self, event) -> Dict[str, str]:
        """从 event.data 提取字符串标签"""
        labels = {}
        # source 优先作为 label
        if event.source:
            labels["source"] = event.source
        for k, v in (event.data or {}).items():
            if k in self._EXCLUDED_LABEL_KEYS:
                continue
            if isinstance(v, (str, int, float, bool)) and v is not None:
                # 转字符串(避免 unhashable)
                labels[k] = str(v)[:64]  # 限制 label 长度
        return labels

    def _freeze_labels(self, labels: Dict[str, Any]) -> frozenset:
        """把 dict 转 frozenset(便于做 dict key)"""
        return frozenset(
            (str(k), str(v)[:64])
            for k, v in labels.items()
        )

    def _label_set_to_str(self, label_set: frozenset) -> str:
        """frozenset 转 Prometheus label 字符串"""
        if not label_set:
            return ""
        items = sorted(label_set)
        # Prometheus label value 需要转义双引号和反斜杠
        parts = []
        for k, v in items:
            v_escaped = v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            parts.append(f'{k}="{v_escaped}"')
        return "{" + ",".join(parts) + "}"

    def _label_set_to_dict(self, label_set: frozenset) -> Dict[str, str]:
        return dict(label_set)


# ---------------- 单例与安装 ----------------

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

        try:
            from fr_cli.v3.core.events import EventBus
            from fr_cli.v3.core.plugin import PluginManager
        except Exception:
            # 没 v3 时退化:返回独立实例(不挂事件总线)
            _global_metrics = MetricsPlugin(buckets=buckets)
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
