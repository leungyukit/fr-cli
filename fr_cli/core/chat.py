"""
AI 对话处理核心

负责 system prompt 组装、流式调用、命令执行、
多源信息汇总与保存意图检测。
"""
import copy
import sys
from pathlib import Path

from fr_cli.lang.i18n import T
from fr_cli.ui.ui import CYAN, DIM, RESET, YELLOW, RED, GREEN
from fr_cli.core.stream import stream_cnt
from fr_cli.weapon.loader import get_available_tools
from fr_cli.addon.plugin import exec_plugin, extract_code, PLUGIN_DIR
from fr_cli.core.recommender import recommend_features
from fr_cli.core.sysmon import get_sys_stats
from fr_cli.memory.context import extract_recent_turns, build_context_summary, save_context
from fr_cli.memory.session import create_session, update_session
from fr_cli.core.intent import should_force_tool, classify_intent, has_info_fetch_intent, has_save_intent


def _fetch_mcp_tools(mcp_manager):
    """安全获取 MCP 工具列表"""
    if mcp_manager and hasattr(mcp_manager, "list_all_tools"):
        try:
            tools = mcp_manager.list_all_tools()
            return tools if isinstance(tools, list) else []
        except Exception:
            pass
    return []


def _fetch_mcp_desc(mcp_manager):
    """安全获取 MCP 工具描述文本"""
    if mcp_manager and hasattr(mcp_manager, "get_server_tools_desc"):
        try:
            desc = mcp_manager.get_server_tools_desc()
            return desc if isinstance(desc, str) and desc else ""
        except Exception:
            pass
    return ""


def handle_ai_chat(state, u):
    """处理 AI 正常对话流程"""
    # MasterAgent 自我进化主控模式接管（ReAct 循环 + 自主工具调用）
    if getattr(state, 'master_agent', None) and state.master_agent.is_enabled():
        final_answer, _ = state.master_agent.handle(u)
        if final_answer:
            print(final_answer)
        return

    lang = state.lang
    prompt = u
    if state.vfs.cwd:
        prompt += T("ctx_dir", lang, state.vfs.cwd)

    # 根据 UI 模式决定是否注入工具
    if getattr(state, 'ui_mode', 'dev') == 'chat':
        # 纯对话模式：不注入任何工具
        intent = "CHAT"
        tools = []
    else:
        # 开发模式：正常注入工具
        tools = get_available_tools(state.weapon_tools, state.plugins)
        # 将 MCP 外部工具纳入意图判定视野
        mcp_manager = getattr(state, "mcp", None)
        mcp_tools_summary = _fetch_mcp_tools(mcp_manager)
        if mcp_tools_summary:
            tools.append({
                "name": "mcp_tools",
                "description": "MCP 外部工具: " + ", ".join([t["name"] for t in mcp_tools_summary]),
                "commands": ["mcp_call"],
            })
        if should_force_tool(u):
            intent = "TOOL"
        else:
            intent = classify_intent(state, u, tools, lang)

    # ---------- 思维推演（CoT / ToT / ReAct）----------
    reasoning_text = None
    if state.thinking_mode != "direct":
        from fr_cli.core.thinking import ThinkingEngine
        engine = ThinkingEngine()
        if engine.is_valid_mode(state.thinking_mode):
            # CoT / ToT 需要额外一次流式调用（思维过程已展示给用户）
            if state.thinking_mode in ("cot", "tot"):
                reasoning_text = engine.analyze(state, u, state.thinking_mode, intent, lang)
            elif state.thinking_mode == "react":
                reasoning_text = engine.analyze(state, u, "react", intent, lang)

    if intent == "TOOL":
        tools_info = "\n\n当前可用的工具列表：\n"
        for i, tool in enumerate(tools, 1):
            tools_info += f"{i}. {tool['name']}: {tool['description']}\n   可用命令: {', '.join(tool['commands'])}\n"
        # 注入 MCP 外部工具
        mcp_manager = getattr(state, "mcp", None)
        mcp_desc = _fetch_mcp_desc(mcp_manager)
        if mcp_desc:
            tools_info += mcp_desc + "\n"
            tools_info += "\n调用 MCP 工具时，请使用格式：【调用：mcp_call({\"server\": \"服务器名\", \"tool\": \"工具名\", \"arguments\": {...}})】\n"
        # 信息获取规范：当用户需要调用外部信息源时，采用双源回答模式
        if has_info_fetch_intent(u):
            tools_info += """\n
【信息获取规范 —— 双源回答与汇总】
用户的问题涉及信息获取（如搜索、查询、读取远程内容、调用Agent/MCP工具等）。请严格按以下步骤执行：

1. 初步回答（必须）：
   先基于你的内部知识给出一个初步回答或分析框架，直接输出在回复文本中。
   禁止只写"让我查一下"而不给实质内容。

2. 工具补充：
   然后调用相应的工具（search_web、mcp_call、agent_call、read_file 等）获取补充信息。

3. 汇总整理（第二轮自动执行）：
   所有工具结果返回后，我会将你的初步回答与所有工具返回结果一起提交给你。
   请基于多源信息整理成一份完整、准确、结构清晰的最终答案。
   若不同来源存在冲突，请以最新/最权威来源为准，或明确标注不确定性。
"""
        sp = T("sys_prompt", lang)

        # 注入项目级上下文（persona.md / agents/ / config.json）
        from fr_cli.core.project import build_project_context_injection
        project_ctx = build_project_context_injection(state)

        system_content = sp + tools_info + state.context_summary + project_ctx
    else:
        sp = T("sys_prompt", lang)
        system_content = sp + state.context_summary

    # 注入思维推演结果
    if reasoning_text and state.thinking_mode == "react":
        # 只有 react 模式需要注入 system prompt（因为用户看不到）
        system_content += reasoning_text
    # cot/tot 的 reasoning_text 已经流式展示给用户，不需要再注入

    # 更新系统提示词
    updated_messages = copy.deepcopy(state.messages)
    if not updated_messages or updated_messages[0]["role"] != "system":
        updated_messages.insert(0, {"role": "system", "content": system_content})
    else:
        updated_messages[0]["content"] = system_content

    updated_messages.append({"role": "user", "content": prompt})

    # 检测是否调用了本地技能
    triggered_plugin = None
    for pk in state.plugins:
        if prompt.startswith(f"/{pk} "):
            triggered_plugin = pk
            p_args = prompt[len(f"/{pk} "):].strip()
            break

    if triggered_plugin:
        if state.security.check("sec_exec", f"/{triggered_plugin}"):
            exec_plugin(triggered_plugin, state.plugins[triggered_plugin], p_args, lang)
        updated_messages.append({"role": "assistant", "content": f"[Executed /{triggered_plugin}]"})
        state.messages = updated_messages
        return

    # 流式调用 AI
    from fr_cli.core.errors import friendly_print
    try:
        txt, usage, response_time, _ = stream_cnt(
            state.client, state.model_name, updated_messages, lang,
            max_tokens=state.limit
        )
    except Exception as e:
        print(f"{RED}{friendly_print(e)}{RESET}")
        return
    updated_messages.append({"role": "assistant", "content": txt})

    # 自动执行 AI 响应中的命令
    try:
        clean_txt, cmd_results = state.executor.process_ai_commands(txt, updated_messages)
    except Exception as e:
        print(f"{RED}{friendly_print(e)}{RESET}")
        clean_txt, cmd_results = txt, []

    # 显示 AI 响应（去除命令标记后的内容）
    if clean_txt.strip():
        print(clean_txt)

    # 显示命令执行结果，并再次调用 AI
    if cmd_results:
        print(f"\n{GREEN}自动执行命令:{RESET}")
        for result in cmd_results:
            print(f"{DIM}{result}{RESET}")

        # 重构为【多源信息汇总】模式：将 AI 初步回答与所有工具结果结构化合并
        sources = []
        if clean_txt.strip():
            sources.append(f"【来源一：大模型初步回答】\n{clean_txt.strip()}")
        for idx, result in enumerate(cmd_results, start=2):
            sources.append(f"【来源{idx}：工具执行结果】\n{result}")

        blend_system_content = "=== 多源信息汇总 ===\n\n"
        blend_system_content += "\n\n---\n\n".join(sources)
        blend_system_content += (
            "\n\n=== 整理要求 ===\n"
            "请基于以上所有信息来源，整理成一份完整、准确、结构清晰的最终答案。\n"
            "- 不同来源的信息若存在冲突，请以最新/最权威来源为准，或明确标注不确定性。\n"
            "- 若大模型初步回答已较完整，但工具结果提供了更新/更详细的数据，请在初步回答基础上补充修正。\n"
            "- 若工具结果与初步回答完全一致，可精简输出，避免冗余。\n"
            "- 最终答案应自成一体，用户无需知道这是多源汇总的结果。"
        )

        updated_messages[-1]["content"] = clean_txt if clean_txt.strip() else "[已执行命令]"
        updated_messages.append({"role": "system", "content": blend_system_content})

        # 方案二：检测保存意图，追加提示强制第二轮 AI 调用 write_file
        if has_save_intent(u):
            save_hint = (
                "\n[系统提示：用户原始请求中包含'保存到本地'的意图。"
                "请在给出最终整理后的回答后，使用 write_file 工具将完整内容保存到文件。"
                "如果用户未指定文件名，请使用一个能反映内容主题的简洁文件名（如 a2a_introduction.md）。]"
            )
            updated_messages.append({"role": "system", "content": save_hint})

        sys.stdout.write(f"{GREEN}{T('prompt_ai', lang)} ")
        sys.stdout.flush()
        final_txt, final_usage, final_response_time, _ = stream_cnt(
            state.client, state.model_name, updated_messages, lang,
            custom_prefix="", max_tokens=state.limit
        )
        updated_messages.append({"role": "assistant", "content": final_txt})

        if final_usage:
            usage = final_usage
        response_time += final_response_time

    # 显示模型信息和 token 使用情况
    sys_stats = get_sys_stats(lang)
    stats_extra = f" | {sys_stats}" if sys_stats else ""
    if usage:
        input_tokens = usage.get('prompt_tokens', 0)
        output_tokens = usage.get('completion_tokens', 0)
        total_tokens = usage.get('total_tokens', 0)
        print(f"{GREEN}模型: {state.model_name} | 输入: {input_tokens} tokens | 输出: {output_tokens} tokens | 总计: {total_tokens} tokens | 耗时: {response_time:.2f}秒{stats_extra}{RESET}")
    else:
        print(f"{GREEN}模型: {state.model_name} | 耗时: {response_time:.2f}秒{stats_extra}{RESET}")

    # 智能功能推荐
    recommendations = recommend_features(u)
    if recommendations:
        print(f"{GREEN}推荐功能:{RESET}")
        for i, rec in enumerate(recommendations[:5], 1):
            print(f"  {DIM}[{i}]{RESET} {CYAN}{rec['cmd']}{RESET} - {rec['desc']}")

    # 智能插件进化检测 & Agent 分身检测（统一入口）
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
        path = create_session(state.messages)
        if path:
            state.auto_session_path = path
            print(f"{DIM}自动会话已创建: {Path(path).name}{RESET}")
    else:
        update_session(state.auto_session_path, state.messages)

    # 返回统计信息供底部状态栏使用
    return {
        "response_time": response_time,
        "input_tokens": usage.get('prompt_tokens', 0) if usage else 0,
        "output_tokens": usage.get('completion_tokens', 0) if usage else 0,
        "total_tokens": usage.get('total_tokens', 0) if usage else 0,
    }
