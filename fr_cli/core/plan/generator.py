"""
计划生成与渲染：generate_plan / render_plan / 工具描述生成 / JSON 清理
"""
import json
import re
from typing import Any, Dict, Optional

from fr_cli.core.stream import stream_cnt
from fr_cli.ui.ui import CYAN, DIM, RESET, print_styled

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


def _iter_json_objects(text: str):
    """按出现顺序 yield 每个字符串感知匹配的顶层 {...} 候选子串。

    字符串感知: 花括号在 JSON 字符串字面量内部不算结构括号。
    模型输出里常有 "{...}" 这类占位碎片(live 实测的 CoT 形态),
    所以逐个 yield 候选, 由调用方挑第一个真正解析成功的。
    """
    if not text:
        return
    t = text.strip()
    # 剥代码块围栏(```json / ``` ), 围栏可有可无
    t = re.sub(r"^```(?:json|JSON)?\s*\n?", "", t)
    t = re.sub(r"\n?```\s*$", "", t)
    n = len(t)
    for start in range(n):
        if t[start] != "{":
            continue
        depth = 0
        in_str = False
        esc = False
        for i in range(start, n):
            ch = t[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    yield t[start:i + 1]
                    break


def _extract_json_object(text: str) -> Optional[str]:
    """提取第一个能解析成 dict 的 JSON 对象子串; 找不到返回 None。

    容忍三类脏输出(live 冒烟都见过):
    1. JSON 前后带思维链/解释性散文(step-5-preview 规划时的典型形态)
    2. ```json ... ``` 代码块围栏
    3. JSON 字符串字面量内部的花括号(不会被误判为结构括号)
    """
    for cand in _iter_json_objects(text):
        try:
            obj = json.loads(cand)
        except Exception:
            continue
        if isinstance(obj, dict):
            return cand
    return None


def _try_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """尝试解析 JSON，失败返回 None"""
    cleaned = _clean_json_text(text)
    try:
        return json.loads(cleaned)
    except Exception:
        return None


def parse_plan_json(text: str) -> Optional[Dict[str, Any]]:
    """容错解析计划 JSON: 容忍 CoT 前后文/代码块; 规范化 steps。失败返回 None。

    plan_mode 的 generate_plan 与 MasterAgent 的强制规划步共用:
    旧实现只认"纯 JSON 或 ``` 开头", 模型一讲废话就解析失败
    (live 实测: [x] 计划生成失败), 现在逐个候选对象挑第一个
    解析成功且带 steps 列表的。
    """
    for cand in _iter_json_objects(text):
        try:
            plan = json.loads(cand)
        except Exception:
            continue
        if isinstance(plan, dict) and isinstance(plan.get("steps"), list):
            break
    else:
        return None

    # 规范化每一步(与旧 generate_plan 内联逻辑一致, 抽出来共用)
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


def _normalize_tool_call(obj):
    """把各种形态的工具调用对象规范化成 {"tool": name, "params": dict}。

    接受的键位(live 实测 step-5-preview 会混用):
      {"tool","params"} / {"tool","arguments"} / {"name","arguments"}
      {"tool"} / {"function":{"name","arguments"}} (OpenAI 风格)
    不是工具调用(没有工具名字符串)时返回 None。
    """
    if not isinstance(obj, dict):
        return None
    fn = obj.get("function")
    if isinstance(fn, dict):
        obj = fn
    name = obj.get("tool") or obj.get("name") or obj.get("tool_name")
    if not isinstance(name, str) or not name.strip():
        return None
    params = None
    for key in ("params", "arguments", "parameters"):
        val = obj.get(key)
        if isinstance(val, dict):
            params = val
            break
    return {"tool": name.strip(), "params": params or {}}


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
    hint = "正在制定执行计划..." if lang == "zh" else "Generating execution plan..."
    # 计划模式跑在 REPL 的 patch_stdout 代理期, 裸打 DIM 会被 Vt100_Output
    # 把 ESC 换成字面 '?', 用户看到 ?[2m正在制定执行计划...?[0m 乱码
    # (live 冒烟复现过); 与 chat/plan_mode 的 render_plan 打印同一出口。
    print_styled(f"{DIM}{hint}{RESET}")

    # silent=True: 模型的思维链/JSON 原文不刷屏, 解析成功后由 render_plan
    # 统一渲染(live 实测: 非静默时 step-5-preview 先吐一大段 CoT 再给 JSON,
    # 用户被原始思考过程淹没; 计划展示走 render_plan 足够)。
    txt, usage, response_time, interrupted = stream_cnt(
        state.client,
        state.model_name,
        messages,
        lang,
        custom_prefix="",
        max_tokens=2048,
        silent=True,
    )

    if interrupted or not txt:
        return None

    # 容错解析: 容忍 CoT 前后文/代码块围栏, 不再一讲废话就失败
    plan = parse_plan_json(txt)
    if not plan:
        return None

    return plan


def render_plan(plan: Dict[str, Any], lang: str = "zh") -> str:
    """将计划渲染为人类可读的文本"""
    lines = []
    goal = plan.get("goal", "")
    summary = plan.get("summary", "")
    steps = plan.get("steps", [])

    if lang == "zh":
        lines.append(f"{CYAN}目标：{goal}{RESET}")
        if summary:
            lines.append(f"{DIM}策略：{summary}{RESET}")
        lines.append(f"{CYAN}执行步骤：{RESET}")
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
        lines.append(f"{CYAN}Goal: {goal}{RESET}")
        if summary:
            lines.append(f"{DIM}Strategy: {summary}{RESET}")
        lines.append(f"{CYAN}Steps:{RESET}")
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
