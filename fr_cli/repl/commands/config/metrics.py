"""
REPL 指标命令 —— /metrics [json|prom]

展示 MetricsPlugin 采集到的运行时指标:
- /metrics        人类可读摘要(默认)
- /metrics json   JSON 快照(便于脚本消费)
- /metrics prom   Prometheus 文本格式(便于抓取)

数据源:state.metrics(AppState 初始化时安装 MetricsPlugin,失败为 None)。
指标模块不可用时给友好提示,不抛异常。
"""
from __future__ import annotations

import json
from typing import Any, Dict

from fr_cli.ui.ui import DIM, RED, RESET, YELLOW

# 子命令 → MetricsPlugin 渲染方法名
_FORMAT_METHODS: Dict[str, str] = {
    "": "metrics_summary",   # 人类可读摘要
    "json": "metrics_json",  # JSON 快照
    "prom": "metrics_text",  # Prometheus 文本
}


def _cmd_metrics(state, parts):
    """查看运行时指标：/metrics [json|prom]"""
    fmt = (parts[1] if len(parts) > 1 else "").strip().lower()
    if fmt not in _FORMAT_METHODS:
        print(f"{RED}[x] 未知格式: {fmt}{RESET}")
        print(f"{DIM}用法: /metrics [json|prom]{RESET}")
        return False

    metrics = getattr(state, "metrics", None)
    if metrics is None:
        # 指标模块未安装 / 初始化失败 —— 给友好提示,不抛异常
        print(f"{YELLOW}[!] 指标模块未初始化{RESET}")
        print(f"{DIM}提示: metrics 插件未安装或初始化失败,可用 /status 查看系统状态{RESET}")
        return False

    method_name = _FORMAT_METHODS[fmt]
    if not hasattr(metrics, method_name):
        print(f"{YELLOW}[!] 指标模块未初始化{RESET}")
        print(f"{DIM}提示: 当前指标模块不支持 {method_name} 渲染{RESET}")
        return False

    try:
        if fmt == "json":
            payload: Any = metrics.metrics_json()
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        elif fmt == "prom":
            print(metrics.metrics_text())
        else:
            print(metrics.metrics_summary())
    except Exception as e:
        print(f"{RED}[x] 读取指标失败: {e}{RESET}")

    return False
