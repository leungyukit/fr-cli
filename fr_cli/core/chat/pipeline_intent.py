"""
pipeline 阶段 1+2:intent 判定 + system prompt 组装

从 fr_cli.core.chat.pipeline 拆出(原文件 488 行)。
- _resolve_intent:    UI 模式 → 工具加载(含 MCP) → intent 判定 → 思维推演
- _assemble_prompt:   sys_prompt + 工具信息 + 项目上下文 + react 推演结果
- _build_tools_info:  工具/Agent/MCP 注入文本 + 双源回答规范
"""
from __future__ import annotations

from fr_cli.lang.i18n import T
from fr_cli.core.intent import has_info_fetch_intent, classify_intent, should_force_tool
from fr_cli.weapon.loader import get_available_tools

from fr_cli.core.chat.helpers import fetch_mcp_desc, fetch_mcp_tools


def _resolve_intent(state, u, prompt, lang):
    """根据 UI 模式决定是否注入工具 + 判定 intent + 思维推演"""
    if getattr(state, "ui_mode", "dev") == "chat":
        # 纯对话模式:不注入任何工具
        return "CHAT", [], None

    # 开发模式:正常注入工具
    tools = get_available_tools(state.weapon_tools, state.plugins)

    # 将 MCP 外部工具纳入意图判定视野
    mcp_manager = getattr(state, "mcp", None)
    mcp_tools_summary = fetch_mcp_tools(mcp_manager)
    if mcp_tools_summary:
        tools.append(
            {
                "name": "mcp_tools",
                "description": "MCP 外部工具: " + ", ".join(
                    t["name"] for t in mcp_tools_summary
                ),
                "commands": ["mcp_call"],
            }
        )

    if should_force_tool(u):
        intent = "TOOL"
    else:
        intent = classify_intent(state, u, tools, lang)

    # ---------- 思维推演(CoT / ToT / ReAct)----------
    reasoning_text = None
    if state.thinking_mode != "direct":
        from fr_cli.core.thinking import ThinkingEngine
        engine = ThinkingEngine()
        if engine.is_valid_mode(state.thinking_mode):
            # CoT / ToT 需要额外一次流式调用(思维过程已展示给用户)
            if state.thinking_mode in ("cot", "tot"):
                reasoning_text = engine.analyze(state, u, state.thinking_mode, intent, lang)
            elif state.thinking_mode == "react":
                reasoning_text = engine.analyze(state, u, "react", intent, lang)

    return intent, tools, reasoning_text


def _assemble_prompt(state, u, intent, tools, reasoning_text, lang):
    """根据 intent 组装 system prompt + 工具/Agent/MCP 信息注入"""
    sp = T("sys_prompt", lang)

    if intent == "TOOL":
        tools_info = _build_tools_info(state, u, tools, lang)
    else:
        tools_info = ""

    # 注入项目级上下文(persona.md / agents/ / config.json)
    from fr_cli.core.project import build_project_context_injection
    project_ctx = build_project_context_injection(state)

    system_content = sp + tools_info + state.context_summary + project_ctx

    # 注入思维推演结果(只有 react 模式需要注入 system prompt,CoT/ToT 已经流式展示)
    if reasoning_text and state.thinking_mode == "react":
        system_content += reasoning_text

    return system_content


def _build_tools_info(state, u, tools, lang):
    """构造工具/Agent/MCP 注入文本"""
    is_en = lang == "en"
    title = "\n\nAvailable tools:\n" if is_en else "\n\n当前可用的工具列表:\n"
    cmd_label = "Commands" if is_en else "可用命令"
    param_label = "Parameters" if is_en else "参数"
    none_label = "none" if is_en else "无参数"
    important = (
        "\n[Important] When the user's request requires a tool, you MUST output the invocation marker directly; the system will execute it automatically. Do not only provide a natural-language explanation. Format: 【调用:tool_name({\"parameter\": \"value\"})】\n"
        if is_en else
        "\n【重要】当用户请求需要工具才能完成时,你必须直接输出调用标记,系统会自动执行。不要只给出自然语言说明。调用格式:【调用:tool_name({\"参数\": \"值\"})】\n"
    )
    tools_info = title
    for i, tool in enumerate(tools, 1):
        params = tool.get("params", {})
        params_desc = ", ".join(f"{k}: {v}" for k, v in params.items()) if params else none_label
        tools_info += (
            f"{i}. {tool['name']}: {tool['description']}\n"
            f"   {cmd_label}: {', '.join(tool['commands'])}\n"
            f"   {param_label}: {params_desc}\n"
        )
    tools_info += important

    # 注入 MCP 描述
    mcp_desc = fetch_mcp_desc(getattr(state, "mcp", None))
    if mcp_desc:
        tools_info += mcp_desc + "\n"
        if is_en:
            tools_info += (
                "\nTo call an MCP tool, use: 【调用:mcp_call({\"server\": \"server_name\", "
                "\"tool\": \"tool_name\", \"arguments\": {...}})】\n"
            )
        else:
            tools_info += (
                "\n调用 MCP 工具时,请使用格式:【调用:mcp_call({\"server\": \"服务器名\", "
                "\"tool\": \"工具名\", \"arguments\": {...}})】\n"
            )

    # 注入本地/远程 Agent 分身
    try:
        from fr_cli.agent.client import discover_all_agents
        agents = discover_all_agents()
        if agents:
            if is_en:
                tools_info += "\n=== Available Agents ===\n"
                for a in agents:
                    tools_info += f"- [{a['type']}] {a['name']}: {a['description']}\n"
                tools_info += "\nInvocation: 【调用:agent_call({\"name\": \"AgentName\", \"user_input\": \"task description\"})】\n"
            else:
                tools_info += "\n=== 可协作的独立Agent ===\n"
                for a in agents:
                    tools_info += f"- [{a['type']}] {a['name']}: {a['description']}\n"
                tools_info += "\n调用方式: 【调用:agent_call({\"name\": \"Agent名\", \"user_input\": \"任务描述\"})】\n"
    except Exception:
        pass

    # 信息获取规范:双源回答
    if has_info_fetch_intent(u):
        tools_info += """\n
【信息获取规范 —— 双源回答与汇总】
用户的问题涉及信息获取(如搜索、查询、读取远程内容、调用Agent/MCP工具等)。请严格按以下步骤执行:

1. 初步回答(必须):
   先基于你的内部知识给出一个初步回答或分析框架,直接输出在回复文本中。
   禁止只写"让我查一下"而不给实质内容。

2. 工具补充:
   然后调用相应的工具(search_web、mcp_call、agent_call、read_file 等)获取补充信息。

3. 汇总整理(第二轮自动执行):
   所有工具结果返回后,我将你的初步回答与所有工具返回结果一起提交给你。
   请基于多源信息整理成一份完整、准确、结构清晰的最终答案。
   若不同来源存在冲突,请以最新/最权威来源为准,或明确标注不确定性。
"""

    return tools_info
