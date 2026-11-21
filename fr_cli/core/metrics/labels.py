"""
MetricsPlugin 标签工具 —— event.data → label / frozenset 双向转换

从 fr_cli.core.metrics.plugin 拆出。包含排除字段表与四个私有辅助方法。
"""
from __future__ import annotations

from typing import Any, Dict


class MetricsLabelsMixin:
    """标签提取与序列化(被 primitives / hooks / render 共用)"""

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
