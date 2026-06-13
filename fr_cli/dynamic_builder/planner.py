"""
动态构建 —— 规划器

分析用户需求，判断应该构建什么工具、需要什么依赖、参数是什么。
"""
import json
from fr_cli.core.stream import stream_cnt


PLANNER_PROMPT_ZH = """你是一位 fr-cli 动态构建规划专家。请根据用户需求，输出一个 JSON 格式的构建计划。

用户需求：{requirement}

当前已具备的能力包括：文件读写、网页搜索、邮件、定时任务、云盘、OCR、图表生成、数据库查询、RAG、MCP、Agent、蜂群、股票数据等。

请判断用户需要的功能是否已经由现有能力覆盖：
- 如果已覆盖，请输出一个使用现有工具/命令的计划。
- 如果未覆盖，请输出构建新动态工具的计划。

输出必须严格是以下 JSON 格式（不要包含任何其他文字）：
{{
  "need_build": true 或 false,
  "tool_name": "工具名（合法的 Python 标识符）",
  "description": "一句话描述工具用途",
  "dependencies": ["需要的 pip 包名，如 pillow"],
  "params": {{"参数名": "str/int/float/bool/list/dict"}},
  "aliases": ["/简写命令"],
  "triggers": ["触发关键词"],
  "reasoning": "为什么需要构建这个工具或如何使用现有工具"
}}

注意：
- need_build 为 false 时，tool_name 和 dependencies 可为空。
- params 中的参数类型只支持 str/int/float/bool/list/dict。
- 不要输出 Markdown 代码块。"""


PLANNER_PROMPT_EN = """You are an fr-cli dynamic build planning expert. Based on the user's requirement, output a JSON build plan.

User requirement: {requirement}

Existing capabilities include: file I/O, web search, email, cron jobs, cloud disk, OCR, charts, database queries, RAG, MCP, Agent, Swarm, stock data, etc.

Please determine whether the required functionality is already covered by existing capabilities:
- If covered, output a plan using existing tools/commands.
- If not covered, output a plan to build a new dynamic tool.

Output must strictly follow this JSON format (no other text):
{{
  "need_build": true or false,
  "tool_name": "Tool name (valid Python identifier)",
  "description": "One-sentence description of the tool",
  "dependencies": ["Required pip package names, e.g., pillow"],
  "params": {{"param_name": "str/int/float/bool/list/dict"}},
  "aliases": ["/short_command"],
  "triggers": ["Trigger keywords"],
  "reasoning": "Why build this tool or how to use existing tools"
}}

Notes:
- When need_build is false, tool_name and dependencies can be empty.
- Param types in params only support str/int/float/bool/list/dict.
- Do not output Markdown code blocks."""


def _clean_json(text: str) -> str:
    """清理 JSON 文本"""
    text = text.strip()
    if text.startswith("```"):
        text = text[text.find("\n") + 1:]
    if text.endswith("```"):
        text = text[:text.rfind("```")]
    return text.strip()


def plan_build(requirement: str, state, lang: str = "zh") -> dict:
    """
    调用 LLM 生成构建计划。

    Returns:
        plan dict 或 {"error": ...}
    """
    prompt_template = PLANNER_PROMPT_ZH if lang == "zh" else PLANNER_PROMPT_EN
    prompt = prompt_template.format(requirement=requirement)

    messages = [{"role": "user", "content": prompt}]
    txt, _, _, _ = stream_cnt(
        state.client,
        state.model_name,
        messages,
        lang,
        custom_prefix="",
        max_tokens=1024,
        silent=False,
    )

    cleaned = _clean_json(txt)
    try:
        plan = json.loads(cleaned)
        if not isinstance(plan, dict):
            return {"error": "LLM 返回的计划不是 JSON 对象"}
        return plan
    except json.JSONDecodeError as e:
        return {"error": f"计划解析失败: {e}", "raw": cleaned}
