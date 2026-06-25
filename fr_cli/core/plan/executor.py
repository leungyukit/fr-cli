"""
计划执行与结果汇总：execute_step / execute_plan / summarize_execution
"""
from typing import Any, Dict, List, Optional, Tuple

from fr_cli.core.stream import stream_cnt
from fr_cli.ui.ui import DIM, GREEN, RED, RESET

from fr_cli.core.plan.generator import render_plan
from fr_cli.core.plan.prompts import SUMMARY_PROMPT_EN, SUMMARY_PROMPT_ZH


def _resolve_step_params(step: Dict[str, Any], step_results: List[Tuple[bool, str]]) -> Dict[str, Any]:
    """
    回填步骤参数中的依赖引用。
    支持 {{stepN.result}} 或 depends_on_step 标记。
    """
    params = dict(step.get("params", {}))
    if not params:
        return params

    # 处理 depends_on_step
    dep_idx = params.pop("depends_on_step", None)
    if dep_idx is not None:
        try:
            dep_idx = int(dep_idx) - 1  # 1-based -> 0-based
            if 0 <= dep_idx < len(step_results):
                success, result = step_results[dep_idx]
                if success:
                    # 如果步骤本身有明确的输入参数名，回填其值
                    # 否则把 result 作为通用 content/query
                    if "content" not in params and "query" not in params:
                        # 启发式：若结果不太长，作为 content；否则作为 query 摘要
                        params["content"] = result[:2000]
        except (ValueError, TypeError):
            pass

    # 处理模板变量 {{stepN.result}}
    resolved = {}
    for k, v in params.items():
        if isinstance(v, str):
            for i in range(len(step_results), 0, -1):
                placeholder = f"{{{{step{i}.result}}}}"
                if placeholder in v:
                    success, result = step_results[i - 1]
                    v = v.replace(placeholder, result[:2000] if success else "")
            resolved[k] = v
        else:
            resolved[k] = v
    return resolved


def _fold_text(text: str, max_lines: int = 30, head: int = 15, tail: int = 5) -> str:
    """长结果自动折叠"""
    lines = str(text).splitlines()
    if len(lines) <= max_lines:
        return str(text)
    head_lines = lines[:head]
    tail_lines = lines[-tail:]
    omitted = len(lines) - head - tail
    return "\n".join(head_lines) + f"\n{DIM}  ... ({omitted} lines omitted, use /cat to view full content) ...{RESET}\n" + "\n".join(tail_lines)


def execute_step(state, step: Dict[str, Any], step_idx: int,
                 step_results: List[Tuple[bool, str]], lang: str = "zh") -> Tuple[bool, str]:
    """
    执行单个计划步骤。

    Returns:
        (success, result_text)
    """
    tool = step.get("tool")
    description = step.get("description", "")

    if not tool:
        # 无需工具，直接记录描述
        return True, f"(info) {description}"

    params = _resolve_step_params(step, step_results)

    status_label = f"[{step_idx + 1}/{getattr(state, 'active_plan_total_steps', '?')}]"
    if lang == "zh":
        print(f"{GREEN}▸ 执行步骤 {status_label} {description}{RESET}")
    else:
        print(f"{GREEN}▸ Step {status_label} {description}{RESET}")

    try:
        if isinstance(tool, str) and tool.startswith("/"):
            # 命令形式，如 /write a.md 内容
            cmd_str = tool.lstrip("/")
            # 尝试把 params 合并成命令参数
            if params:
                # 取第一个非依赖参数作为值
                values = [str(v) for v in params.values() if isinstance(v, (str, int, float, bool))]
                if values:
                    cmd_str += " " + " ".join(f'"{v}"' if " " in str(v) else str(v) for v in values)
            exec_result = state.executor.execute(cmd_str)
            result, error = exec_result.to_tuple()
        else:
            exec_result = state.executor.invoke_tool(tool, params)
            result, error = exec_result.to_tuple()

        if error:
            err_text = str(error)
            print(f"{RED}  ❌ {err_text}{RESET}")
            return False, err_text

        result_text = str(result) if result is not None else ""
        folded = _fold_text(result_text)
        print(f"{DIM}{folded}{RESET}")
        return True, result_text

    except Exception as e:
        err_text = str(e)
        print(f"{RED}  ❌ {err_text}{RESET}")
        return False, err_text


def execute_plan(state, plan: Dict[str, Any], lang: str = "zh") -> List[Tuple[bool, str]]:
    """
    顺序执行计划中的所有步骤。

    Returns:
        step_results: list of (success, result_text)
    """
    steps = plan.get("steps", [])
    state.active_plan_total_steps = len(steps)
    step_results: List[Tuple[bool, str]] = []

    for idx, step in enumerate(steps):
        state.plan_step_idx = idx
        success, result = execute_step(state, step, idx, step_results, lang)
        step_results.append((success, result))

    state.plan_step_idx = len(steps)
    return step_results


def summarize_execution(state, user_input: str, plan: Dict[str, Any],
                        step_results: List[Tuple[bool, str]], lang: str = "zh") -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    调用 LLM 对计划执行结果进行最终汇总。

    Returns:
        (summary_text, usage_dict)
    """
    plan_text = render_plan(plan, lang)

    result_lines = []
    for i, (success, result) in enumerate(step_results, 1):
        status = "成功" if success else "失败" if lang == "zh" else "success" if success else "failed"
        result_lines.append(f"步骤 {i}: [{status}]\n{result[:1500]}")
    results_text = "\n\n".join(result_lines)

    prompt_template = SUMMARY_PROMPT_ZH if lang == "zh" else SUMMARY_PROMPT_EN
    prompt = prompt_template.format(
        user_input=user_input,
        plan_text=plan_text,
        results_text=results_text,
    )

    messages = [
        {"role": "system", "content": "You are a helpful assistant that summarizes task execution results."},
        {"role": "user", "content": prompt},
    ]

    if lang == "zh":
        print(f"{DIM}📝 正在汇总执行结果...{RESET}")
    else:
        print(f"{DIM}📝 Summarizing results...{RESET}")

    summary, usage, response_time, interrupted = stream_cnt(
        state.client,
        state.model_name,
        messages,
        lang,
        custom_prefix="",
        max_tokens=state.limit,
        silent=False,
    )

    return summary, usage
