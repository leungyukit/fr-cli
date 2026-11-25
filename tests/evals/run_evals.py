#!/usr/bin/env python3
"""eval 评分脚本 —— 离线跑完任务集并输出四个核心指标。

用法::

    .venv/bin/python tests/evals/run_evals.py            # 跑全部数据集
    .venv/bin/python tests/evals/run_evals.py --json     # 机器可读输出
    .venv/bin/python tests/evals/run_evals.py --strict   # 指标不满 100% 就退出码 1

保证：**无网络、无需 API Key**。LLM 走脚本化 mock，web / mail / disk 全是桩件。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Sequence

# --- 路径引导：让脚本既能 `python tests/evals/run_evals.py` 直接跑，
# --- 也能被 pytest 以模块方式导入
_EVAL_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _EVAL_DIR.parents[1]
for _p in (str(_EVAL_DIR), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from harness import (  # noqa: E402  (路径引导必须在 import 之前)
    DATASET_DIR,
    EvalTask,
    TaskOutcome,
    compute_metrics,
    default_cfg,
    load_tasks,
    run_all,
)

#: 四个核心指标的中文名（报告与 pytest 断言共用同一套口径）
CORE_METRICS = (
    ("tool_selection_accuracy", "工具选择正确率"),
    ("param_accuracy", "参数正确率"),
    ("multi_step_completion", "多步完成率"),
    ("security_interception", "越权拦截率"),
)


def _fmt_pct(value: float) -> str:
    """百分比格式化。"""
    return f"{value * 100:.1f}%"


def _fmt_task_line(outcome: TaskOutcome) -> str:
    """单条任务明细。"""
    task = outcome.task
    mark = "✔" if outcome.tool_matched and outcome.param_exact else "✘"
    blocked = {True: "已拦", False: "未拦", None: "-"}[outcome.blocked]
    confirms = len(outcome.security_requests)
    bits = [
        f"{mark} {task.id:<38}",
        f"期望={task.expect_tool:<16}",
        f"实得={str(outcome.selected_tool):<16}",
        f"参数={outcome.param_score:.2f}",
        f"确认×{confirms}",
        f"拦截={blocked}",
    ]
    if outcome.hit_step_limit:
        bits.append("超步数")
    if outcome.error:
        bits.append(f"异常={outcome.error}")
    if outcome.param_detail:
        bits.append("| " + "; ".join(outcome.param_detail))
    return "  " + "  ".join(bits)


def build_report(
    tasks: Sequence[EvalTask],
    outcomes: Sequence[TaskOutcome],
    metrics,
    dataset_dir: Path,
) -> str:
    """拼装人类可读的评测报告。"""
    lines: List[str] = []
    bar = "=" * 78
    lines.append(bar)
    lines.append(" fr-cli eval —— 离线评测报告（零网络 / 无需 API Key / 脚本化 LLM）")
    lines.append(bar)
    lines.append(f"数据集  : {dataset_dir}")
    lines.append(f"任务数  : {len(tasks)}")
    lines.append("")
    lines.append("【核心指标】")
    metric = metrics.to_dict()
    for key, label in CORE_METRICS:
        lines.append(f"  {label:<8}: {_fmt_pct(metric[key])}")
    lines.append("")
    lines.append("  口径说明:")
    lines.append("    工具选择正确率 —— 模型选中的工具 == 期望工具 的任务占比")
    lines.append("    参数正确率     —— 工具命中后，期望参数的逐 key 命中率均值")
    lines.append("    多步完成率     —— 多步任务在 max_steps 内按序跑完并收敛的占比")
    lines.append("    越权拦截率     —— 该被拦的调用真的走了 state.security 确认流程且被拦下的占比")
    lines.append("")
    lines.append("【辅助指标】")
    lines.append(f"  端到端成功率 : {_fmt_pct(metric['end_to_end_rate'])}"
                 f"  ({metric['end_to_end_ok']}/{metric['total']})")
    lines.append(f"  回归基线     : {_fmt_pct(metric['regression_rate'])}"
                 f"  ({metric['end_to_end_ok'] - metric['known_issue_ok']}/"
                 f"{metric['total'] - metric['known_issue_total']}，已排除已知缺陷)")
    lines.append(f"  误拦率       : {_fmt_pct(metric['false_block_rate'])}"
                 f"  ({metric['false_blocked']}/{metric['false_block_total']})")
    lines.append("")
    lines.append("【分项计数】")
    lines.append(f"  工具命中     : {metric['tool_matched']}/{metric['total']}")
    lines.append(f"  多步完成     : {metric['multi_step_ok']}/{metric['multi_step_total']}")
    lines.append(f"  成功拦截     : {metric['security_blocked']}/{metric['security_total']}")
    lines.append("")
    known = [o for o in outcomes if o.task.known_issue]
    if known:
        lines.append("【已知缺陷】（非回归 —— 修好后本项转绿）")
        for outcome in known:
            state = "已通过" if outcome.dispatch_ok else "仍失败"
            lines.append(f"  ⚠ {outcome.task.id}: {outcome.task.known_issue}  [{state}]")
        lines.append("")
    lines.append("【逐任务明细】")
    for outcome in outcomes:
        lines.append(_fmt_task_line(outcome))
    lines.append(bar)
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="fr-cli 离线 eval 评分脚本")
    parser.add_argument(
        "--dataset-dir",
        default=str(DATASET_DIR),
        help="数据集目录（默认 tests/evals/datasets）",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON（机器可读）")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="任一核心指标低于 100% 即以退出码 1 结束（CI 用）",
    )
    args = parser.parse_args(argv)

    dataset_dir = Path(args.dataset_dir)
    tasks = load_tasks(dataset_dir)
    if not tasks:
        print(f"[错误] 数据集目录里没有任务: {dataset_dir}", file=sys.stderr)
        return 2

    outcomes = run_all(tasks, cfg=default_cfg())
    metrics = compute_metrics(outcomes)

    if args.json:
        payload = {
            "metrics": metrics.to_dict(),
            "tasks": [
                {
                    "id": o.task.id,
                    "expect_tool": o.task.expect_tool,
                    "selected_tool": o.selected_tool,
                    "tool_matched": o.tool_matched,
                    "param_score": round(o.param_score, 4),
                    "param_detail": o.param_detail,
                    "actual_sequence": o.actual_sequence,
                    "blocked": o.blocked,
                    "expect_blocked": o.task.expect_blocked,
                    "security_requests": o.security_requests,
                    "finished": o.finished,
                    "hit_step_limit": o.hit_step_limit,
                    "dispatch_ok": o.dispatch_ok,
                    "error": o.error,
                }
                for o in outcomes
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(build_report(tasks, outcomes, metrics, dataset_dir))

    if args.strict:
        metric = metrics.to_dict()
        failed = [
            label for key, label in CORE_METRICS if metric[key] < 1.0
        ]
        if failed:
            print(f"[未达标] 核心指标未达 100%: {', '.join(failed)}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
