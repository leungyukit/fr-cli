"""
计划生成与渲染：generate_plan / render_plan / 工具描述生成 / JSON 清理
"""
import json
from typing import Any, Dict, Optional

from fr_cli.core.stream import stream_cnt
from fr_cli.ui.ui import CYAN, DIM, RESET

from fr_cli.core.plan.prompts import PLAN_PROMPT_EN, PLAN_PROMPT_ZH


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
