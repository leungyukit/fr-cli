"""
Plan mode UI 增强 —— 彩色 + 进度条 + 步骤状态

相比之前纯文本展示,现在:
- ANSI 颜色高亮(标题/成功/失败/警告)
- 进度条:██████░░░░ 60%
- 步骤状态图标:✅ ❌ ⏳ 🏃 ⏭️
- 估算每步耗时(基于工具类型)
- 步骤依赖可视化(箭头)
- 实时执行进度

依赖:ANSI 颜色常量和 NO_COLOR 环境变量检查。
"""
import os
from typing import Dict, List, Any, Tuple

# ANSI 颜色(参考 fr_cli/ui/ui.py)
try:
    from fr_cli.ui.ui import (
        RESET, BOLD, DIM, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE,
    )
except ImportError:
    # fallback
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"


def _color(text: str, color: str) -> str:
    """应用颜色,尊重 NO_COLOR 环境变量"""
    if os.environ.get("NO_COLOR"):
        return text
    return f"{color}{text}{RESET}"


def _step_estimate(tool_name: str) -> int:
    """估算步骤耗时(秒)

    基于工具类型的经验值:
    - read/write/list: < 2s
    - search/fetch: 5-15s
    - shell/cmd: 5-30s
    - LLM 工具(ai_generate 等): 10-60s
    """
    if not tool_name:
        return 5
    tool_lower = tool_name.lower()
    fast = ["read_file", "read", "list_files", "list", "ls", "grep", "cat",
            "check", "verify", "validate", "describe"]
    medium = ["search", "fetch", "fetch_web", "git_status", "git_log",
              "git_diff", "replace_text", "multi_edit", "write_file",
              "append_file"]
    slow = ["shell", "exec", "install", "build", "compile", "test",
            "ai_generate", "agent_call", "send_mail"]
    very_slow = ["swarm_run", "spawn_agent", "mcp_call", "build_dynamic_tool",
                 "analyze_image", "generate_image", "deep_research"]

    if any(k in tool_lower for k in very_slow):
        return 30
    if any(k in tool_lower for k in slow):
        return 15
    if any(k in tool_lower for k in medium):
        return 5
    if any(k in tool_lower for k in fast):
        return 2
    return 5


def _total_estimate(steps: List[Dict[str, Any]]) -> int:
    """估算总耗时"""
    return sum(_step_estimate(s.get("tool", "")) for s in steps)


def _format_time(seconds: int) -> str:
    """格式化秒数"""
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    return f"{m}m{s}s"


def render_plan_beautiful(plan: Dict[str, Any], lang: str = "zh",
                          use_color: bool = True) -> str:
    """渲染计划(彩色版)

    Args:
        plan: {goal, steps, summary}
        lang: zh/en
        use_color: 是否用颜色

    Returns:
        彩色化的多行字符串
    """
    if not use_color:
        os.environ["NO_COLOR"] = "1"
        # 临时禁用颜色
        old_no_color = os.environ.get("NO_COLOR")
        os.environ["NO_COLOR"] = "1"

    try:
        goal = plan.get("goal", "")
        steps = plan.get("steps", [])
        summary = plan.get("summary", "")

        # 标题
        if lang == "zh":
            title = "📋 执行计划"
            goal_label = "目标"
            steps_label = "步骤"
            summary_label = "摘要"
            est_label = "预计耗时"
            action_label = "请审批"
        else:
            title = "📋 Execution Plan"
            goal_label = "Goal"
            steps_label = "Steps"
            summary_label = "Summary"
            est_label = "Estimated time"
            action_label = "Please approve"

        lines = []
        # Header
        sep = "═" * 60
        lines.append(_color(sep, CYAN + BOLD))
        lines.append(_color(f"  {title}", CYAN + BOLD))
        lines.append(_color(sep, CYAN + BOLD))
        lines.append("")

        # Goal
        if goal:
            lines.append(_color(f"{goal_label}: ", BOLD) + _color(goal, WHITE))

        # Summary
        if summary:
            lines.append(_color(f"{summary_label}: ", DIM) + _color(summary, DIM))

        lines.append("")

        # Steps
        if steps:
            total = _total_estimate(steps)
            lines.append(_color(f"{steps_label} ({len(steps)} 步,{est_label} ~{_format_time(total)}):", BOLD))
            lines.append("")

            for i, step in enumerate(steps, 1):
                tool = step.get("tool", "?")
                desc = step.get("description", step.get("desc", ""))
                params = step.get("params", {})

                # 步骤图标
                step_num = _color(f"[{i}/{len(steps)}]", YELLOW)
                tool_text = _color(tool, CYAN + BOLD)
                est = _format_time(_step_estimate(tool))

                lines.append(f"  {step_num} {tool_text} {_color(f'(~{est})', DIM)}")
                if desc:
                    lines.append(f"       {_color(desc, WHITE)}")
                if params:
                    # 显示关键参数
                    key_params = []
                    for k in ("path", "query", "prompt", "command", "message",
                              "branch", "ref", "text"):
                        if k in params:
                            v = str(params[k])
                            if len(v) > 60:
                                v = v[:57] + "..."
                            key_params.append(f"{k}={v}")
                    if key_params:
                        lines.append(f"       {_color('  '.join(key_params), DIM)}")

                # 步骤间箭头(连接)
                if i < len(steps):
                    lines.append(_color("       │", DIM))
                    lines.append(_color("       ▼", DIM))
            lines.append("")

        # Action prompt
        lines.append(_color(sep, CYAN))
        if lang == "zh":
            lines.append(f"  {action_label}:")
            lines.append(_color("    y", GREEN + BOLD) + " / " + _color("回车", DIM) + " = 批准并执行")
            lines.append(_color("    n", RED + BOLD) + "    = 拒绝,继续普通对话")
            lines.append(_color("    e", YELLOW + BOLD) + "    = 编辑计划(自然语言描述修改)")
            lines.append(_color("    s", BLUE + BOLD) + "    = 展示完整 JSON")
            lines.append(_color("    d", MAGENTA + BOLD) + "    = 步骤详情(查看每个步骤的参数)")
        else:
            lines.append(f"  {action_label}:")
            lines.append(_color("    y", GREEN + BOLD) + " / Enter = approve and execute")
            lines.append(_color("    n", RED + BOLD) + "     = reject")
            lines.append(_color("    e", YELLOW + BOLD) + "     = edit (natural language)")
            lines.append(_color("    s", BLUE + BOLD) + "     = show full JSON")
            lines.append(_color("    d", MAGENTA + BOLD) + "     = detailed step info")
        lines.append(_color(sep, CYAN))

        return "\n".join(lines)
    finally:
        if not use_color and old_no_color is None:
            os.environ.pop("NO_COLOR", None)
        elif not use_color:
            os.environ["NO_COLOR"] = old_no_color


def render_execution_progress(step_idx: int, total_steps: int,
                              tool: str, status: str,
                              result_text: str = "",
                              use_color: bool = True) -> str:
    """渲染执行进度(单步骤)

    Args:
        step_idx: 当前步骤 (1-indexed)
        total_steps: 总步骤数
        tool: 当前工具名
        status: pending / running / completed / failed
        result_text: 步骤结果(可空)
    """
    if not use_color:
        old_no_color = os.environ.get("NO_COLOR")
        os.environ["NO_COLOR"] = "1"

    try:
        percent = (step_idx / total_steps) * 100 if total_steps > 0 else 0
        bar_len = 30
        filled = int(bar_len * percent / 100)
        bar = "█" * filled + "░" * (bar_len - filled)

        status_icons = {
            "pending": ("⏳", YELLOW, "等待"),
            "running": ("🏃", CYAN, "执行中"),
            "completed": ("✅", GREEN, "完成"),
            "failed": ("❌", RED, "失败"),
            "skipped": ("⏭️", DIM, "跳过"),
        }
        icon, color, label = status_icons.get(status, ("?", WHITE, status))

        lines = []
        lines.append(_color(f"[{step_idx}/{total_steps}]", BOLD) +
                     f" {_color(icon, color)} {_color(tool, CYAN + BOLD)}"
                     f" {_color(f'({label})', color)}")
        lines.append(_color(f"  [{bar}] {percent:.0f}%", color))

        if result_text:
            # 截断显示
            preview = result_text.strip().split("\n")[0][:120]
            lines.append(f"  {_color(preview, DIM)}")

        return "\n".join(lines)
    finally:
        if not use_color and old_no_color is None:
            os.environ.pop("NO_COLOR", None)
        elif not use_color:
            os.environ["NO_COLOR"] = old_no_color


def render_execution_summary(results: List[Tuple[bool, str]],
                             plan: Dict[str, Any],
                             lang: str = "zh") -> str:
    """渲染执行总结

    Args:
        results: [(success, text), ...]
        plan: 原始 plan
        lang: zh/en
    """
    total = len(results)
    success = sum(1 for ok, _ in results if ok)
    failed = total - success

    if lang == "zh":
        header = "执行完成"
        success_label = "成功"
        failed_label = "失败"
        details_label = "步骤详情"
        next_label = "下一步"
    else:
        header = "Execution Complete"
        success_label = "Success"
        failed_label = "Failed"
        details_label = "Step details"
        next_label = "Next"

    lines = []
    lines.append(_color("═" * 60, CYAN + BOLD))
    lines.append(_color(f"  📊 {header}", CYAN + BOLD))
    lines.append(_color("═" * 60, CYAN + BOLD))
    lines.append("")

    # 总览
    success_color = GREEN if success == total else YELLOW if success > 0 else RED
    lines.append(f"  {_color('●', success_color)} {success_label}: "
                 f"{_color(str(success), success_color + BOLD)} / {total}")
    if failed > 0:
        lines.append(f"  {_color('●', RED)} {failed_label}: "
                     f"{_color(str(failed), RED + BOLD)}")

    # 进度条
    percent = (success / total * 100) if total > 0 else 0
    bar_len = 30
    filled = int(bar_len * percent / 100)
    bar = "█" * filled + "░" * (bar_len - filled)
    bar_color = GREEN if percent == 100 else YELLOW if percent >= 50 else RED
    lines.append(f"  [{_color(bar, bar_color)}] {percent:.0f}%")
    lines.append("")

    # 步骤详情
    if results:
        lines.append(_color(f"  {details_label}:", BOLD))
        steps = plan.get("steps", [])
        for i, (ok, text) in enumerate(results, 1):
            tool = steps[i-1].get("tool", "?") if i-1 < len(steps) else "?"
            icon = "✅" if ok else "❌"
            color = GREEN if ok else RED
            lines.append(f"    {_color(icon, color)} "
                        f"{_color(f'[{i}/{total}]', BOLD)} "
                        f"{_color(tool, CYAN)}")
            preview = text.strip().split("\n")[0][:100] if text else ""
            if preview:
                lines.append(f"        {_color(preview, DIM)}")
        lines.append("")

    # 下一步建议
    if failed == 0:
        lines.append(_color(f"  🎉 {next_label}: 计划完美执行!", GREEN))
    else:
        lines.append(_color(f"  ⚠️ {next_label}: 有 {failed} 步失败,建议 /context compress 后重试,"
                            f"或重新进入 plan mode", YELLOW))

    lines.append("")
    lines.append(_color("═" * 60, CYAN))
    return "\n".join(lines)
