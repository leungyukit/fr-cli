"""
MetricsPlugin 指标原语 —— counter / histogram / timer / gauge

从 fr_cli.core.metrics.plugin 拆出(原文件 485 行,单类承担太多职责)。
本 mixin 只负责四类指标的存取,线程安全(RLock)。

注意:本文件是被 MetricsPlugin 继承的 mixin,不是独立类——
公开 API 仍是 `fr_cli.core.metrics.plugin.MetricsPlugin`。
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Any, Dict, FrozenSet, Optional, Tuple


class MetricsPrimitivesMixin:
    """四类指标原语(状态存储 + 线程安全操作)"""

    def __init__(self, buckets: Tuple[float, ...]):
        # 注意:不调用 super().__init__() —— Plugin 基链由 MetricsPlugin 组装,
        # 各 mixin 只初始化自己那部分状态,避免多继承下重复初始化。
        self._buckets = buckets
        self._lock = threading.RLock()
        # Counter: (name, frozenset(labels)) -> int
        self._counters: Dict[Tuple[str, FrozenSet], int] = defaultdict(int)
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
