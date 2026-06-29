"""
pipeline.py —— 直接对话模式主流程(传统 ReAct/CoT/普通对话)

handle_ai_chat 编排:
  1. _route_mode        入口路由(plan / master / direct)
  2. _resolve_intent     工具加载 + 思维推演 + intent 判定
  3. _assemble_prompt    system prompt 组装 + 工具/Agent/MCP 注入
  4. _stream_and_respond 流式调用 + 错误处理 + 命令自动执行
  5. _multi_source_blend 多源信息汇总第二轮
  6. _post_process       统计 / 推荐 / 产物检测 / 记忆 / 存档
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

from fr_cli.lang.i18n import T
from fr_cli.ui.ui import CYAN, DIM, GREEN, RED, RESET, YELLOW
from fr_cli.core.stream import stream_cnt
from fr_cli.core.intent import (
    has_info_fetch_intent,
    has_save_intent,
    classify_intent,
    should_force_tool,
)
from fr_cli.core.sysmon import get_sys_stats
from fr_cli.memory.context import build_context_summary, extract_recent_turns, save_context
from fr_cli.memory.session import create_session, update_session
from fr_cli.ui.markdown import render_markdown
from fr_cli.weapon.loader import get_available_tools

from fr_cli.core.chat.helpers import (
    auto_compress_messages,
    record_usage,
    fetch_mcp_tools,
    fetch_mcp_desc,
    fold_result,
)


# ============================================================
# 路由
# ============================================================


def handle_ai_chat(state, u):
    """处理 AI 正常对话流程"""
    # 模型未配置时阻止调用
    if not state.model_name:
        print(
            f"{YELLOW}⚠️ 模型未配置,请使用 {CYAN}/model <模型名>{YELLOW} 或 {CYAN}/model config{YELLOW} 选择模型。{RESET}"
        )
        return

    return _route_mode(state, u)


def _route_mode(state, u):
    """根据 thinking_mode / master_agent 状态路由到不同模式"""
    # 计划模式:LLM 先制定结构化计划,用户确认后逐步执行
    if getattr(state, "thinking_mode", "direct") == "plan":
        from fr_cli.core.chat.plan_mode import handle_plan_mode
        return handle_plan_mode(state, u)

    # MasterAgent 自我进化主控模式接管(ReAct 循环 + 自主工具调用)
    if getattr(state, "master_agent", None) and state.master_agent.is_enabled():
        final_answer, _ = state.master_agent.handle(u)
        if final_answer:
            print(final_answer)
        return

    return _direct_chat(state, u)


# ============================================================
# 直接对话主流程
# ============================================================


def _direct_chat(state, u):
    """直接对话:工具加载 → system prompt → 流式调用 → 命令执行 → 多源汇总 → 收尾"""
    lang = state.lang
    prompt = u
    if state.vfs.cwd:
        prompt += T("ctx_dir", lang, state.vfs.cwd)

    intent, tools, reasoning_text = _resolve_intent(state, u, prompt, lang)
    system_content = _assemble_prompt(state, u, intent, tools, reasoning_text, lang)

    # 更新系统提示词
    updated_messages = copy.deepcopy(state.messages)
    if not updated_messages or updated_messages[0]["role"] != "system":
        updated_messages.insert(0, {"role": "system", "content": system_content})
    else:
        updated_messages[0]["content"] = system_content
    updated_messages.append({"role": "user", "content": prompt})

    # 长会话自动压缩
    auto_compress_messages(state, updated_messages)

    # 插件命令前置拦截(以 /plugin_name 开头的输入)
    triggered = _maybe_run_local_plugin(state, prompt, lang, updated_messages)
    if triggered:
        return

    # 流式调用 + 命令执行 + 多源汇总
    txt, usage, response_time = _stream_and_respond(state, updated_messages, u, lang)
    if txt is None:
        return  # 流式调用失败

    # 收尾:统计 / 推荐 / 产物检测 / 记忆 / 存档
    return _post_process(state, updated_messages, txt, usage, response_time, u, lang)


# ============================================================
# 阶段 1:intent + 工具 + 思维推演
# ============================================================


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


# ============================================================
# 阶段 2:system prompt 组装
# ============================================================


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


# ============================================================
# 阶段 3:插件前置拦截
# ============================================================


def _maybe_run_local_plugin(state, prompt, lang, updated_messages):
    """如果 prompt 以 /plugin_name 开头,直接执行本地插件(无 LLM 调用)"""
    for pk in state.plugins:
        if prompt.startswith(f"/{pk} "):
            p_args = prompt[len(f"/{pk} "):].strip()
            if state.security.check("sec_exec", f"/{pk}"):
                from fr_cli.addon.plugin import exec_plugin
                exec_plugin(pk, state.plugins[pk], p_args, lang)
            updated_messages.append({"role": "assistant", "content": f"[Executed /{pk}]"})
            state.messages = updated_messages
            return True
    return False


# ============================================================
# 阶段 4:流式调用 + 命令自动执行 + 多源汇总
# ============================================================


def _stream_and_respond(state, updated_messages, u, lang):
    """流式调用 AI,自动执行命令,必要时进入第二轮多源汇总"""
    # v3.0+:广播 llm.requested
    try:
        from fr_cli.core.events import V2Events, dispatch_event
        dispatch_event(
            V2Events.LLM_REQUESTED,
            data={
                "provider": getattr(state, "provider", None),
                "model": state.model_name,
                "messages_count": len(updated_messages),
                "prompt_preview": u[:200],
            },
            source="chat",
        )
    except Exception:
        pass

    try:
        txt, usage, response_time, _ = stream_cnt(
            state.client, state.model_name, updated_messages, lang,
            max_tokens=state.limit,
        )
    except Exception as e:
        try:
            from fr_cli.core.events import V2Events, dispatch_event
            dispatch_event(
                V2Events.LLM_FAILED,
                data={"model": state.model_name, "error": str(e)},
                source="chat",
            )
        except Exception:
            pass
        from fr_cli.core.errors import friendly_print
        print(f"{RED}{friendly_print(e)}{RESET}")
        return None, None, 0.0

    if usage:
        record_usage(state, usage)
    updated_messages.append({"role": "assistant", "content": txt})

    # v3.0+:广播 llm.responded
    try:
        from fr_cli.core.events import V2Events, dispatch_event
        dispatch_event(
            V2Events.LLM_RESPONDED,
            data={
                "model": state.model_name,
                "usage": usage,
                "response_time": response_time,
                "output_len": len(txt) if txt else 0,
            },
            source="chat",
        )
    except Exception:
        pass

    # 自动执行 AI 响应中的命令
    try:
        clean_txt, cmd_results = state.executor.process_ai_commands(txt, updated_messages)
    except Exception as e:
        from fr_cli.core.errors import friendly_print
        print(f"{RED}{friendly_print(e)}{RESET}")
        clean_txt, cmd_results = txt, []

    # 显示 AI 响应(去除命令标记后的内容,带 Markdown 渲染)
    if clean_txt.strip():
        print(render_markdown(clean_txt))

    # 显示命令执行结果,并再次调用 AI
    if cmd_results:
        print(f"\n{GREEN}▸ 自动执行命令{RESET}")
        for result in cmd_results:
            folded = fold_result(result)
            print(f"{DIM}{folded}{RESET}")

        # 多源汇总第二轮
        usage, response_time = _multi_source_blend(
            state, updated_messages, clean_txt, cmd_results, u, lang, usage, response_time,
        )

    return txt, usage, response_time


def _multi_source_blend(
    state, updated_messages, clean_txt, cmd_results, u, lang, usage, response_time,
):
    """将大模型初步回答与所有工具结果结构化合并,触发第二轮 AI 调用"""
    sources = []
    if clean_txt.strip():
        sources.append(f"【来源一:大模型初步回答】\n{clean_txt.strip()}")
    for idx, result in enumerate(cmd_results, start=2):
        sources.append(f"【来源{idx}:工具执行结果】\n{result}")

    blend_system_content = "=== 多源信息汇总 ===\n\n"
    blend_system_content += "\n\n---\n\n".join(sources)
    blend_system_content += (
        "\n\n=== 整理要求 ===\n"
        "请基于以上所有信息来源,整理成一份完整、准确、结构清晰的最终答案。\n"
        "- 不同来源的信息若存在冲突,请以最新/最权威来源为准,或明确标注不确定性。\n"
        "- 若大模型初步回答已较完整,但工具结果提供了更新/更详细的数据,请在初步回答基础上补充修正。\n"
        "- 若工具结果与初步回答完全一致,可精简输出,避免冗余。\n"
        "- 最终答案应自成一体,用户无需知道这是多源汇总的结果。"
    )

    updated_messages[-1]["content"] = clean_txt if clean_txt.strip() else "[已执行命令]"
    updated_messages.append({"role": "system", "content": blend_system_content})

    # 第二轮前再次压缩(工具结果可能很长)
    auto_compress_messages(state, updated_messages)

    # 检测保存意图,追加提示强制第二轮 AI 调用 write_file
    if has_save_intent(u):
        save_hint = (
            "\n[系统提示:用户原始请求中包含'保存到本地'的意图。"
            "请在给出最终整理后的回答后,使用 write_file 工具将完整内容保存到文件。"
            "如果用户未指定文件名,请使用一个能反映内容主题的简洁文件名(如 a2a_introduction.md)。]"
        )
        updated_messages.append({"role": "system", "content": save_hint})

    sys.stdout.write(f"{GREEN}{T('prompt_ai', lang)} ")
    sys.stdout.flush()
    final_txt, final_usage, final_response_time, _ = stream_cnt(
        state.client, state.model_name, updated_messages, lang,
        custom_prefix="", max_tokens=state.limit,
    )
    updated_messages.append({"role": "assistant", "content": final_txt})

    if final_usage:
        record_usage(state, final_usage)
        usage = final_usage
    response_time += final_response_time

    return usage, response_time


# ============================================================
# 阶段 5:收尾处理
# ============================================================


def _post_process(state, updated_messages, txt, usage, response_time, u, lang):
    """统计 / 推荐 / 产物检测 / 记忆 / 存档"""
    # 显示模型信息和 token 使用情况
    sys_stats = get_sys_stats(lang)
    stats_extra = f" | {sys_stats}" if sys_stats else ""
    if usage:
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)
        usage_pct = f" ({total_tokens / state.limit * 100:.0f}%)" if state.limit else ""
        print(
            f"{DIM}⏱ {response_time:.1f}s · {state.display_model} · "
            f"↓{input_tokens} ↑{output_tokens} Σ{total_tokens}{usage_pct}"
            f"{stats_extra}{RESET}"
        )
    else:
        print(f"{DIM}⏱ {response_time:.1f}s · {state.display_model}{stats_extra}{RESET}")

    # 智能功能推荐
    from fr_cli.core.recommender import recommend_features
    recommendations = recommend_features(u)
    if recommendations:
        print(f"{GREEN}推荐功能:{RESET}")
        for i, rec in enumerate(recommendations[:5], 1):
            print(f"  {DIM}[{i}]{RESET} {CYAN}{rec['cmd']}{RESET} - {rec['desc']}")

    # 智能插件进化检测 & Agent 分身检测(统一入口)
    from fr_cli.agent.artifact_detector import detect_plugin_artifact, detect_agent_artifact
    detect_plugin_artifact(txt, lang, state)
    detect_agent_artifact(txt, lang, state)

    # 更新记忆上下文
    recent = extract_recent_turns(updated_messages, 5)
    state.context_summary = build_context_summary(recent, lang)
    save_context(state.sn, state.context_summary)

    # 更新主消息列表
    state.messages = updated_messages

    # 自动按日期存档会话
    if not state.auto_session_path:
        path = create_session(state.messages, session_id=getattr(state, "session_id", None))
        if path:
            state.auto_session_path = path
            print(f"{DIM}💾 {Path(path).name}{RESET}")
    else:
        update_session(state.auto_session_path, state.messages)

    # 返回统计信息供底部状态栏使用
    return {
        "response_time": response_time,
        "input_tokens": usage.get("prompt_tokens", 0) if usage else 0,
        "output_tokens": usage.get("completion_tokens", 0) if usage else 0,
        "total_tokens": usage.get("total_tokens", 0) if usage else 0,
    }
