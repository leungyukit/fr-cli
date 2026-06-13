"""
计划模式 —— 运筹帷幄

让 LLM 先识别用户意图、自主生成结构化可执行计划，
经用户确认后按步骤调用现有工具（读/写文件、搜索、Agent 等）完成任务，
最后汇总执行结果。
"""
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fr_cli.core.stream import stream_cnt
from fr_cli.ui.ui import CYAN, DIM, GREEN, RED, RESET


PLAN_PROMPT_ZH = """你是一位任务规划专家。请根据用户的需求生成一个结构化、可执行的计划。

要求：
1. 计划必须严格按下方 JSON 格式返回，不要包含任何其他解释性文字。
2. 不要返回 Markdown 代码块标记，只返回纯 JSON 字符串。
3. 每一步应只调用一个工具或命令，避免一步做太多事。
4. 优先使用结构化工具（如 read_file / write_file / search_web 等）。
5. 如果某一步不需要调用工具（例如等待信息、自然语言总结），将 tool 设为 null，params 留空。
6. 如果上一步的输出需要作为下一步的输入，请在 params 中用 {{"依赖步骤": N}} 标注，后续执行引擎会尝试回填。

可用工具：
{tools}

JSON 格式：
{{
  "goal": "用一句话概括用户目标",
  "steps": [
    {{
      "description": "步骤简要描述",
      "tool": "工具名或 /命令名；不需要工具则为 null",
      "params": {{"参数名": "参数值"}},
      "reasoning": "为什么需要这一步"
    }}
  ],
  "summary": "整体执行策略概述"
}}

用户请求：{user_input}

请只返回 JSON："""


PLAN_PROMPT_EN = """You are a task planning expert. Please generate a structured, executable plan based on the user's request.

Requirements:
1. Return the plan strictly in the JSON format below, with no other explanatory text.
2. Do not include Markdown code block markers; return only a pure JSON string.
3. Each step should invoke only one tool or command; avoid doing too much in one step.
4. Prefer structured tools (read_file, write_file, search_web, etc.).
5. If a step does not need a tool (e.g., wait for info, natural-language summary), set tool to null and params to empty.
6. If the output of a previous step is needed as input for the next step, annotate it with {{"depends_on_step": N}} in params; the execution engine will attempt backfill.

Available tools:
{tools}

JSON format:
{{
  "goal": "Summarize the user's goal in one sentence",
  "steps": [
    {{
      "description": "Brief description of the step",
      "tool": "Tool name or /command name; null if no tool is needed",
      "params": {{"param_name": "param_value"}},
      "reasoning": "Why this step is needed"
    }}
  ],
  "summary": "Overall execution strategy overview"
}}

User request: {user_input}

Return only JSON:"""


SUMMARY_PROMPT_ZH = """你是一位结果汇总专家。用户原始请求、执行计划以及每一步的执行结果如下，请整理成一份完整、结构清晰的最终答复。

用户请求：{user_input}

执行计划：
{plan_text}

各步骤执行结果：
{results_text}

要求：
- 用中文回答。
- 突出关键结论，不要简单罗列每一步的原始输出。
- 如果某步骤失败，说明原因并给出建议。
- 若涉及文件，请给出文件路径。
- 回答应自成一体，用户无需了解底层执行细节。"""


SUMMARY_PROMPT_EN = """You are a result-summarization expert. The user's original request, the execution plan, and the result of each step are shown below. Please organize them into a complete, well-structured final response.

User request: {user_input}

Execution plan:
{plan_text}

Step results:
{results_text}

Requirements:
- Answer in English.
- Highlight key conclusions; do not simply list raw step outputs.
- If a step failed, explain why and provide suggestions.
- If files are involved, provide their paths.
- The response should be self-contained; the user does not need to know the underlying execution details."""


def _get_tools_text(state) -> str:
    """从当前状态生成可用工具描述文本"""
    lines = []
    for tool in getattr(state, "weapon_tools", []):
        name = tool.get("name", "")
        desc = tool.get("description", "")
        commands = tool.get("commands", [])
        if commands:
            lines.append(f"- {name}: {desc}  [命令: {', '.join(commands)}]")
        else:
            lines.append(f"- {name}: {desc}")

    # 插件作为命令型工具
    plugins = getattr(state, "plugins", {})
    if plugins:
        lines.append("\n自定义插件（命令方式）：")
        for pk in sorted(plugins.keys()):
            lines.append(f"- /{pk}: 用户插件")

    # MCP 工具
    mcp_manager = getattr(state, "mcp", None)
    if mcp_manager and hasattr(mcp_manager, "list_all_tools"):
        try:
            mcp_tools = mcp_manager.list_all_tools()
            if mcp_tools:
                lines.append("\nMCP 外部工具：")
                for t in mcp_tools:
                    lines.append(f"- mcp_call(server={t.get('server','')}, tool={t.get('name','')})")
        except Exception:
            pass

    return "\n".join(lines)


def _clean_json_text(text: str) -> str:
    """清理 LLM 返回的 JSON：去掉 Markdown 代码块标记、首尾空白等"""
    text = text.strip()
    # 去掉 ```json ... ``` 或 ``` ... ```
    if text.startswith("```"):
        text = text[text.find("\n") + 1:]
    if text.endswith("```"):
        text = text[:text.rfind("```")]
    return text.strip()


def _try_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """尝试解析 JSON，失败返回 None"""
    cleaned = _clean_json_text(text)
    try:
        return json.loads(cleaned)
    except Exception:
        return None


def generate_plan(state, user_input: str, lang: str = "zh") -> Optional[Dict[str, Any]]:
    """
    调用 LLM 生成结构化计划。

    Returns:
        plan dict with keys: goal, steps, summary
        or None if generation/parsing failed.
    """
    tools_text = _get_tools_text(state)
    prompt_template = PLAN_PROMPT_ZH if lang == "zh" else PLAN_PROMPT_EN
    prompt = prompt_template.format(tools=tools_text, user_input=user_input)

    messages = [{"role": "user", "content": prompt}]
    hint = "🗺️ 正在制定执行计划..." if lang == "zh" else "🗺️ Generating execution plan..."
    print(f"{DIM}{hint}{RESET}")

    txt, usage, response_time, interrupted = stream_cnt(
        state.client,
        state.model_name,
        messages,
        lang,
        custom_prefix="",
        max_tokens=2048,
        silent=False,
    )

    if interrupted or not txt:
        return None

    plan = _try_parse_json(txt)
    if not plan or not isinstance(plan.get("steps"), list):
        return None

    # 规范化每一步
    normalized_steps = []
    for step in plan["steps"]:
        if not isinstance(step, dict):
            continue
        tool = step.get("tool")
        # 统一 None / ""
        if tool == "" or tool == "null" or tool == "None":
            tool = None
        normalized_steps.append({
            "description": str(step.get("description", "")),
            "tool": tool,
            "params": step.get("params") or {},
            "reasoning": str(step.get("reasoning", "")),
        })

    plan["steps"] = normalized_steps
    return plan


def render_plan(plan: Dict[str, Any], lang: str = "zh") -> str:
    """将计划渲染为人类可读的文本"""
    lines = []
    goal = plan.get("goal", "")
    summary = plan.get("summary", "")
    steps = plan.get("steps", [])

    if lang == "zh":
        lines.append(f"{CYAN}🎯 目标：{goal}{RESET}")
        if summary:
            lines.append(f"{DIM}📝 策略：{summary}{RESET}")
        lines.append(f"{CYAN}📋 执行步骤：{RESET}")
        for i, step in enumerate(steps, 1):
            desc = step.get("description", "")
            tool = step.get("tool")
            params = step.get("params", {})
            reasoning = step.get("reasoning", "")
            tool_str = f"【调用：{tool}({json.dumps(params, ensure_ascii=False)})】" if tool else "（无需工具）"
            lines.append(f"  {i}. {desc}")
            lines.append(f"     {tool_str}")
            if reasoning:
                lines.append(f"     {DIM}理由：{reasoning}{RESET}")
    else:
        lines.append(f"{CYAN}🎯 Goal: {goal}{RESET}")
        if summary:
            lines.append(f"{DIM}📝 Strategy: {summary}{RESET}")
        lines.append(f"{CYAN}📋 Steps:{RESET}")
        for i, step in enumerate(steps, 1):
            desc = step.get("description", "")
            tool = step.get("tool")
            params = step.get("params", {})
            reasoning = step.get("reasoning", "")
            tool_str = f"[invoke {tool}({json.dumps(params, ensure_ascii=False)})]" if tool else "(no tool)"
            lines.append(f"  {i}. {desc}")
            lines.append(f"     {tool_str}")
            if reasoning:
                lines.append(f"     {DIM}Reason: {reasoning}{RESET}")

    return "\n".join(lines)


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


# ---------------------------------------------------------------------------
# 计划持久化（可选，便于后续 /plan resume 等扩展）
# ---------------------------------------------------------------------------

PLANS_DIR = Path.home() / ".fr_cli" / "plans"


def _plan_file_path(session_id: str) -> Path:
    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    return PLANS_DIR / f"{session_id}.json"


def save_plan(state, plan: Dict[str, Any], step_results: Optional[List[Tuple[bool, str]]] = None) -> Optional[Path]:
    """将当前计划持久化到磁盘"""
    session_id = getattr(state, "session_id", None)
    if not session_id or not plan:
        return None
    path = _plan_file_path(session_id)
    data = {
        "session_id": session_id,
        "timestamp": time.time(),
        "plan": plan,
        "step_results": step_results or [],
        "plan_step_idx": getattr(state, "plan_step_idx", 0),
    }
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
    except Exception:
        return None


def load_plan(state) -> Optional[Dict[str, Any]]:
    """从磁盘加载当前会话的计划"""
    session_id = getattr(state, "session_id", None)
    if not session_id:
        return None
    path = _plan_file_path(session_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("plan")
    except Exception:
        return None


def list_saved_plans() -> List[Path]:
    """列出已保存的所有计划文件"""
    if not PLANS_DIR.exists():
        return []
    return sorted(PLANS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
