"""
MetricsPlugin 导出 —— Prometheus 文本 / JSON / 人类可读摘要 / reset

从 fr_cli.core.metrics.plugin 拆出。三种导出格式 + 清空。
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Dict, List, Tuple


class MetricsRenderMixin:
    """指标导出与重置"""

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
            lines.append(f"Metrics Summary (uptime: {round(time.time() - self._started_at, 1)}s)")
            lines.append(f"   Total events received: {self._total_events}")
            lines.append("=" * 60)

            # counters
            if self._counters:
                lines.append("\nCounters:")
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
                lines.append("\nHistograms:")
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
                lines.append("\nTimers:")
                for name in sorted(self._timers.keys()):
                    s = self.timer_summary(name)
                    if s:
                        lines.append(
                            f"   {name}: n={s['count']} avg={s['avg']:.3f}s "
                            f"min={s['min']:.3f}s max={s['max']:.3f}s"
                        )

            # gauges
            if self._gauges:
                lines.append("\nGauges:")
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
