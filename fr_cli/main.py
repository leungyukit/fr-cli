"""
凡人打字机 - 主脑控制台
负责状态初始化、命令路由与 AI 交互循环
"""
import sys, os, subprocess, platform, shutil
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from fr_cli.conf.config import init_config, ConfigError
from fr_cli.lang.i18n import T
from fr_cli.ui.ui import enable_win_ansi, print_banner, print_bye, CYAN, RED, YELLOW, GREEN, DIM, RESET
from fr_cli.core.stream import stream_cnt
from fr_cli.memory.history import load_sess
from fr_cli.memory.context import extract_recent_turns, build_context_summary, save_context, load_context
from fr_cli.memory.session import create_session, update_session
from fr_cli.addon.plugin import extract_code
from fr_cli.core.recommender import recommend_features
from fr_cli.core.sysmon import get_sys_stats
from fr_cli.core.core import AppState


def _sync_manual_to_workspace(vfs):
    """将项目根目录的 MANUAL.md 复制到工作空间，使 AI 可通过 read_file 读取"""
    if not vfs.cwd:
        return
    try:
        manual_src = Path(__file__).parent.parent / "MANUAL.md"
        if not manual_src.exists():
            return
        manual_dst = Path(vfs.cwd) / "MANUAL.md"
        if not manual_dst.exists():
            import shutil
            shutil.copy2(manual_src, manual_dst)
    except Exception:
        pass


# 明确的工具操作关键词（兜底规则，避免大模型漏判）
# 同时包含中英文，覆盖用户在任何语言界面下输入任意语言的场景
_FORCE_TOOL_KEYWORDS = [
    # 中文关键词
    "保存", "保存到", "保存文件", "写入", "写到", "写入文件", "写到文件",
    "创建文件", "生成文件", "输出到文件", "导出到", "导出文件",
    "搜索", "查找", "查一下", "搜一下",
    "发送邮件", "发邮件", "发信", "发邮件给", "发信给",
    "查看目录", "列出文件", "查看文件", "打开文件",
    "画图", "生成图片", "画一张", "画个", "生成图像",
    "运行代码", "执行代码", "执行脚本", "运行脚本",
    "定时任务", "定时执行", "循环任务",
    "上传", "上传到", "下载", "下载到",
    "保存会话", "导出会话", "切换模型", "设置密钥",
    # 英文关键词
    "save", "save to", "save file", "write", "write to", "write file",
    "create file", "generate file", "output to file", "export", "export to",
    "search", "look up", "look for", "find", "google", "bing",
    "send email", "send mail", "send an email", "email to", "mail to",
    "list files", "list directory", "show files", "show directory", "open file",
    "draw", "generate image", "create image", "paint", "image of",
    "run code", "execute code", "run script", "execute script",
    "schedule", "scheduled task", "cron job", "timer",
    "upload", "upload to", "download", "download to",
    "save session", "export session", "switch model", "set key", "set api key",
    # MCP 外部神通关键词
    "mcp", "外部工具", "外部神通", "调用工具", "use tool", "invoke tool",
]

# 保存意图关键词（用于第二轮强制保存检测）
_SAVE_KEYWORDS = [
    "保存", "保存到", "保存文件", "写入", "写到", "写入文件", "写到文件",
    "存储", "存到", "存为", "导出到", "导出文件",
    "save", "save to", "save file", "save as", "write", "write to", "write file",
    "store", "store to", "export to", "export file",
]

# 信息获取关键词（触发"先回答再调用工具"双源模式）
_INFO_FETCH_KEYWORDS = [
    # 搜索/查询
    "搜索", "查询", "查一下", "搜一下", "什么是", "是什么", "介绍", "了解一下",
    "最新", "新闻", "资讯", "百科", "定义", "概念", "解释",
    "search", "look up", "what is", "what are", "introduction to", "latest",
    "news", "wikipedia", "who is", "how to", "define", "explain",
    # 远程/RAG/Agent
    "远程", "rag", "知识库", "agent", "mcp", "外部工具", "外部神通",
    "remote", "knowledge base", "external tool",
    # 文件/数据读取
    "读取", "查看内容", "分析文件", "总结", "提取",
    "read", "analyze file", "summarize", "extract",
]


def _should_force_tool(user_input):
    """快速关键词预检：如果包含明确的工具操作关键词，直接判定为需要工具。
    同时检测中英文关键词，不依赖当前界面语言。"""
    u = user_input.lower()
    for kw in _FORCE_TOOL_KEYWORDS:
        if kw.lower() in u:
            return True
    return False


def _classify_intent(state, user_input, tools, lang):
    """
    意图判定：让大模型判定用户提问是直接查询还是需要调用工具。
    将用户提问内容和 fr-cli 功能列表发给大模型，由大模型做判定。
    返回 "DIRECT"（直接回答）或 "TOOL"（需要调用工具）。
    根据 lang 自动切换中英文 prompt。
    """
    tools_desc = "\n".join([
        f"- {t['name']}: {t['description']} (commands: {', '.join(t['commands'])}"
        for t in tools
    ])

    if lang == "en":
        classify_prompt = f"""You are an intent classifier. Based on the user's question, determine whether they need a direct answer or need to use the following tools to complete their task.

Available tools:
{tools_desc}

Rules (strict):
- DIRECT: The user is only asking for information, concepts, advice, or chatting. No action is required.
- TOOL: The user requests any specific action, including but not limited to saving files, searching the web, sending emails, listing directories, running code, generating images, etc. If the user mentions any action word like "save", "write", "search", "send", "look up", "list", etc., even if the first half is a question, it MUST be classified as TOOL.

User question: {user_input}

Output only one word: DIRECT or TOOL. No explanation."""
    else:
        classify_prompt = f"""你是一个意图分类器。请根据用户的提问，判定用户是需要直接获得回答，还是需要调用以下工具来完成任务。

可用工具列表：
{tools_desc}

判定规则（请严格遵守）：
- DIRECT：用户只是单纯询问信息、概念、建议、闲聊，没有任何操作要求。
- TOOL：用户要求执行任何具体操作，包括但不限于保存文件、搜索网页、发送邮件、查看目录、运行代码、画图等。只要用户提到了"保存"、"写入"、"搜索"、"发送"、"查看"等操作性词汇，即使前半句是询问信息，也必须判定为 TOOL。

用户提问：{user_input}

请只输出一个单词：DIRECT 或 TOOL。不要输出任何解释。"""

    messages = [{"role": "user", "content": classify_prompt}]
    txt, _, _ = stream_cnt(
        state.client, state.model_name, messages, lang,
        custom_prefix="", max_tokens=10, silent=True
    )

    return "TOOL" if "TOOL" in txt.upper() else "DIRECT"


def _handle_ai_chat(state, u):
    """处理 AI 正常对话流程"""
    from fr_cli.weapon.loader import get_available_tools
    from fr_cli.addon.plugin import exec_plugin

    lang = state.lang
    prompt = u
    if state.vfs.cwd:
        prompt += T("ctx_dir", lang, state.vfs.cwd)

    # 意图判定：先快速关键词预检，未命中再让大模型判定
    tools = get_available_tools(state.weapon_tools, state.plugins)
    # 将 MCP 外部神通纳入意图判定视野
    mcp_manager = getattr(state, "mcp", None)
    mcp_tools_summary = []
    if mcp_manager and hasattr(mcp_manager, "list_all_tools"):
        try:
            _mcp_tools = mcp_manager.list_all_tools()
            if isinstance(_mcp_tools, list):
                mcp_tools_summary = _mcp_tools
        except Exception:
            pass
    if mcp_tools_summary:
        tools.append({
            "name": "mcp_tools",
            "description": "MCP 外部神通: " + ", ".join([t["name"] for t in mcp_tools_summary]),
            "commands": ["mcp_call"],
        })
    if _should_force_tool(u):
        intent = "TOOL"
    else:
        intent = _classify_intent(state, u, tools, lang)

    # ---------- 思维推演（CoT / ToT / ReAct）----------
    reasoning_text = None
    if state.thinking_mode != "direct":
        from fr_cli.core.thinking import ThinkingEngine
        engine = ThinkingEngine()
        if engine.is_valid_mode(state.thinking_mode):
            # CoT / ToT 需要额外一次非流式调用
            if state.thinking_mode in ("cot", "tot"):
                mode_label = "思维链" if state.thinking_mode == "cot" else "思维树"
                print(f"{DIM}🧠 启用 {mode_label} 推演...{RESET}")
                reasoning_text = engine.analyze(state, u, state.thinking_mode, intent, lang)
                if reasoning_text:
                    # 打印推理摘要（前200字符）
                    preview = reasoning_text[:200].replace('\n', ' ')
                    print(f"{DIM}   推演完成: {preview}...{RESET}")
            elif state.thinking_mode == "react":
                reasoning_text = engine.analyze(state, u, "react", intent, lang)

    if intent == "TOOL":
        tools_info = "\n\n当前可用的工具列表：\n"
        for i, tool in enumerate(tools, 1):
            tools_info += f"{i}. {tool['name']}: {tool['description']}\n   可用命令: {', '.join(tool['commands'])}\n"
        # 注入 MCP 外部神通
        mcp_manager = getattr(state, "mcp", None)
        if mcp_manager and hasattr(mcp_manager, "get_server_tools_desc"):
            try:
                mcp_desc = mcp_manager.get_server_tools_desc()
                if isinstance(mcp_desc, str) and mcp_desc:
                    tools_info += mcp_desc + "\n"
                    tools_info += "\n调用 MCP 工具时，请使用格式：【调用：mcp_call({\"server\": \"服务器名\", \"tool\": \"工具名\", \"arguments\": {...}})】\n"
            except Exception:
                pass
        # 信息获取规范：当用户需要调用外部信息源时，采用双源回答模式
        has_info_fetch = any(kw in u.lower() for kw in _INFO_FETCH_KEYWORDS)
        if has_info_fetch:
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
        system_content = sp + tools_info + state.context_summary
    else:
        sp = T("sys_prompt", lang)
        system_content = sp + state.context_summary

    # 注入思维推演结果
    if reasoning_text:
        if state.thinking_mode in ("cot", "tot"):
            system_content += f"\n\n[系统提示：以下是你之前的深度推演结果，请在最终回答中参考这些分析]\n\n{reasoning_text}\n"
        elif state.thinking_mode == "react":
            system_content += reasoning_text

    # 更新系统提示词
    import copy
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
    txt, usage, response_time = stream_cnt(
        state.client, state.model_name, updated_messages, lang,
        max_tokens=state.limit
    )
    updated_messages.append({"role": "assistant", "content": txt})

    # 自动执行 AI 响应中的命令
    clean_txt, cmd_results = state.executor.process_ai_commands(txt, updated_messages)

    # 显示 AI 响应（去除命令标记后的内容）
    if clean_txt.strip():
        print(clean_txt)

    # 显示命令执行结果，并再次调用 AI
    if cmd_results:
        print(f"\n{CYAN}🤖 自动执行命令:{RESET}")
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
        has_save_intent = any(kw in u.lower() for kw in _SAVE_KEYWORDS)
        if has_save_intent:
            save_hint = (
                "\n[系统提示：用户原始请求中包含'保存到本地'的意图。"
                "请在给出最终整理后的回答后，使用 write_file 工具将完整内容保存到文件。"
                "如果用户未指定文件名，请使用一个能反映内容主题的简洁文件名（如 a2a_introduction.md）。]"
            )
            updated_messages.append({"role": "system", "content": save_hint})

        sys.stdout.write(f"{CYAN}{T('prompt_ai', lang)}{RESET} ")
        sys.stdout.flush()
        final_txt, final_usage, final_response_time = stream_cnt(
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
        print(f"{DIM}📊 模型: {state.model_name} | 输入: {input_tokens} tokens | 输出: {output_tokens} tokens | 总计: {total_tokens} tokens | 耗时: {response_time:.2f}秒{stats_extra}{RESET}")
    else:
        print(f"{DIM}📊 模型: {state.model_name} | 耗时: {response_time:.2f}秒{stats_extra}{RESET}")

    # 智能功能推荐
    recommendations = recommend_features(u)
    if recommendations:
        print(f"{CYAN}💡 推荐功能:{RESET}")
        for i, rec in enumerate(recommendations[:5], 1):
            print(f"  {DIM}[{i}]{RESET} {CYAN}{rec['cmd']}{RESET} - {rec['desc']}")

    # 智能法宝进化检测（插件）
    if "def run(args='')" in txt and "```python" in txt:
        code = extract_code(txt)
        if code and "def run" in code and len(code) > 50:
            pname = input(f"{YELLOW}{T('artifact_detect', lang)}{RESET}").strip()
            if pname:
                safe_name = "".join(c for c in pname if c.isalnum() or c == '_')
                if not safe_name:
                    print(f"{RED}名称无效，仅允许字母/数字/下划线{RESET}")
                elif state.security.check("sec_write", f"/{safe_name}"):
                    PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
                    p_path = PLUGIN_DIR / f"{safe_name}.py"
                    p_path.write_text(code, encoding='utf-8')
                    state.plugins[safe_name] = str(p_path)
                    print(f"{GREEN}{T('ok_forged', lang, safe_name)}{RESET}")

    # 智能 Agent 分身检测
    if "def run(context," in txt and "```python" in txt:
        code = extract_code(txt)
        if code and "def run(context," in code and len(code) > 50:
            aname = input(f"{YELLOW}⚡ 检测到 Agent 分身结构，赐名 (回车放弃): {RESET}").strip()
            if aname:
                safe_name = "".join(c for c in aname if c.isalnum() or c == '_')
                if not safe_name:
                    print(f"{RED}名称无效，仅允许字母/数字/下划线{RESET}")
                else:
                    from fr_cli.agent.manager import create_agent_dir, save_agent_code, save_persona, save_skills, agent_exists
                    if agent_exists(safe_name):
                        confirm = input(f"{YELLOW}Agent [{safe_name}] 已存在，是否覆盖? [y/N]: {RESET}").strip().lower()
                        if confirm not in ("y", "yes"):
                            print(f"{DIM}已取消。{RESET}")
                        else:
                            d = create_agent_dir(safe_name)
                            save_agent_code(safe_name, code)
                            print(f"{GREEN}✅ Agent [{safe_name}] 已覆盖更新。{RESET}")
                            print(f"{DIM}  路径: {d}{RESET}")
                    else:
                        d = create_agent_dir(safe_name)
                        save_agent_code(safe_name, code)
                        save_persona(safe_name, f"#{safe_name}\n\n由 AI 对话铸造的 Agent 分身。")
                        save_skills(safe_name, "## 技能\n\n- 执行自定义 Python 逻辑\n- 入口: run(context, **kwargs)")
                        print(f"{GREEN}✅ Agent [{safe_name}] 铸造完成！{RESET}")
                        print(f"{DIM}  路径: {d}{RESET}")
                        print(f"{DIM}  运行: /agent_run {safe_name} [参数]{RESET}")

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
            print(f"{DIM}📁 自动会话已创建: {Path(path).name}{RESET}")
    else:
        update_session(state.auto_session_path, state.messages)


# ------------------------------------------------------------------
# 命令路由函数（将 main() 中巨大的 if-elif 链提取为字典映射）
# 返回 True 表示应退出主循环
# ------------------------------------------------------------------

from fr_cli.repl.commands import (
    _cmd_exit,
    _cmd_help,
    _cmd_model,
    _cmd_key,
    _cmd_limit,
    _cmd_lang,
    _cmd_dir,
    _cmd_dirs,
    _cmd_rmdir,
    _cmd_save,
    _cmd_load,
    _cmd_del,
    _cmd_session_list,
    _cmd_session_load,
    _cmd_session_del,
    _cmd_see,
    _cmd_update,
    _cmd_agent_server,
    _cmd_mode,
    _cmd_gatekeeper,
    _cmd_open,
    _cmd_launch,
    _cmd_apps,
    _cmd_agent_create,
    _cmd_agent_list,
    _cmd_agent_delete,
    _cmd_agent_show,
    _cmd_agent_run,
    _cmd_agent_edit,
    _cmd_agent_forge,
    _cmd_remote_agent_add,
    _cmd_remote_agent_list,
    _cmd_remote_agent_del,
    _cmd_agent_publish,
    _cmd_remote_agent_scan,
    _cmd_remote_agent_import,
    _cmd_remote_setup,
    _cmd_db_setup,
    _cmd_agent_cron_add,
    _cmd_agent_cron_list,
    _cmd_agent_cron_del,
    _cmd_rag_dir,
    _cmd_rag_watch,
    _cmd_rag_sync,
    _cmd_read_excel,
    _cmd_read_csv,
    _cmd_master,
    _cmd_mcp_list,
    _cmd_mcp_add,
    _cmd_mcp_del,
    _cmd_mcp_enable,
    _cmd_mcp_disable,
    _cmd_mcp_refresh,
)


_COMMAND_ROUTES = {
    "/exit": _cmd_exit,
    "/quit": _cmd_exit,
    "/help": _cmd_help,
    "/model": _cmd_model,
    "/key": _cmd_key,
    "/limit": _cmd_limit,
    "/lang": _cmd_lang,
    "/mode": _cmd_mode,
    "/dir": _cmd_dir,
    "/dirs": _cmd_dirs,
    "/rmdir": _cmd_rmdir,
    "/save": _cmd_save,
    "/load": _cmd_load,
    "/del": _cmd_del,
    "/session_list": _cmd_session_list,
    "/session_load": _cmd_session_load,
    "/session_del": _cmd_session_del,
    "/see": _cmd_see,
    "/update": _cmd_update,
    "/agent_server": _cmd_agent_server,
    "/gatekeeper": _cmd_gatekeeper,
    "/open": _cmd_open,
    "/launch": _cmd_launch,
    "/apps": _cmd_apps,
    "/agent_create": _cmd_agent_create,
    "/agent_list": _cmd_agent_list,
    "/agent_delete": _cmd_agent_delete,
    "/agent_show": _cmd_agent_show,
    "/agent_run": _cmd_agent_run,
    "/agent_edit": _cmd_agent_edit,
    "/agent_forge": _cmd_agent_forge,
    "/remote_agent_add": _cmd_remote_agent_add,
    "/remote_agent_list": _cmd_remote_agent_list,
    "/remote_agent_del": _cmd_remote_agent_del,
    "/agent_publish": _cmd_agent_publish,
    "/remote_agent_scan": _cmd_remote_agent_scan,
    "/remote_agent_import": _cmd_remote_agent_import,
    "/remote_setup": _cmd_remote_setup,
    "/db_setup": _cmd_db_setup,
    "/agent_cron_add": _cmd_agent_cron_add,
    "/agent_cron_list": _cmd_agent_cron_list,
    "/agent_cron_del": _cmd_agent_cron_del,
    "/rag_dir": _cmd_rag_dir,
    "/rag_watch": _cmd_rag_watch,
    "/rag_sync": _cmd_rag_sync,
    "/read_excel": _cmd_read_excel,
    "/read_csv": _cmd_read_csv,
    "/master": _cmd_master,
    "/mcp_list": _cmd_mcp_list,
    "/mcp_add": _cmd_mcp_add,
    "/mcp_del": _cmd_mcp_del,
    "/mcp_enable": _cmd_mcp_enable,
    "/mcp_disable": _cmd_mcp_disable,
    "/mcp_refresh": _cmd_mcp_refresh,
}


def main():
    enable_win_ansi()
    try:
        cfg = init_config()
    except ConfigError:
        print(f"{RED}配置初始化失败，退出。{RESET}")
        return
    state = AppState(cfg)

    # 将 MANUAL.md 同步到工作空间
    _sync_manual_to_workspace(state.vfs)

    # 加载历史会话或初始化系统提示词
    sp = T("sys_prompt", state.lang)
    if state.sn:
        ok, m, _ = load_sess(0, sp)
        if ok:
            state.messages = m
    if not state.messages:
        state.messages = [{"role": "system", "content": sp}]

    # 加载当前会话的记忆上下文
    state.context_summary = load_context(state.sn)

    # 启动动画
    print_banner(state.model_name, state.limit, cfg.get("allowed_dirs", [""]), state.sn, state.lang)

    # ================= 主循环 =================
    while True:
        try:
            u = input(f"{CYAN}>>> {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print_bye()
            break

        if not u:
            continue

        # 替换别名
        if u in state.aliases:
            u = state.aliases[u]

        # ----------------- 内置指令路由 -----------------
        if u.startswith("/"):
            parts = u.split()
            cmd = parts[0].lower()
            arg1 = parts[1] if len(parts) > 1 else ""

            if cmd in _COMMAND_ROUTES:
                if _COMMAND_ROUTES[cmd](state, parts):
                    break
            else:
                # 其余命令统一委托给执行引擎
                result, error = state.executor.execute(u, state.messages)
                if error:
                    print(f"{RED}{error}{RESET}")
                elif result is not None:
                    # 根据命令类型做简单格式化
                    if cmd == "/cat" and arg1:
                        print(f"\n{DIM}--- {arg1} ---{RESET}\n{result}\n{DIM}--- EOF ---{RESET}")
                    elif cmd == "/fetch" and arg1:
                        print(f"{DIM}--- Fetch ---{RESET}\n{result}\n{DIM}--- EOF ---{RESET}")
                    elif cmd == "/skills":
                        print("\n".join([f"{CYAN}{line}{RESET}" for line in result.split("\n")]))
                    else:
                        print(result)

        # ----------------- 破壁指令 -----------------
        elif u.startswith("!"):
            is_pipe = "|" in u
            shell_cmd = u[1:].split("|")[0].strip()

            if state.security.check("sec_shell", shell_cmd):
                try:
                    if platform.system() == "Windows":
                        ps_exe = shutil.which("pwsh") or shutil.which("powershell")
                        if ps_exe:
                            res = subprocess.run([ps_exe, "-Command", shell_cmd], capture_output=True, text=True, timeout=15)
                        else:
                            res = subprocess.run(shell_cmd, shell=True, capture_output=True, text=True, timeout=15)
                    else:
                        res = subprocess.run(shell_cmd, shell=True, capture_output=True, text=True, timeout=15)
                    out = res.stdout + res.stderr
                    if is_pipe:
                        pipe_prompt = u.split("|", 1)[1].strip()
                        final_prompt = f"{T('pipe_prefix', state.lang)}{out}\n\n{pipe_prompt}"
                        if state.vfs.cwd:
                            final_prompt += T("ctx_dir", state.lang, state.vfs.cwd)
                        state.messages.append({"role": "user", "content": final_prompt})
                        txt, _, response_time = stream_cnt(
                            state.client, state.model_name, state.messages, state.lang,
                            max_tokens=state.limit
                        )
                        state.messages.append({"role": "assistant", "content": txt})

                        # 自动执行 AI 响应中的命令（与 _handle_ai_chat 保持一致）
                        clean_txt, cmd_results = state.executor.process_ai_commands(txt, state.messages)
                        if cmd_results:
                            print(f"\n{CYAN}🤖 自动执行命令:{RESET}")
                            for result in cmd_results:
                                print(f"{DIM}{result}{RESET}")
                            state.messages[-1]["content"] = clean_txt if clean_txt.strip() else "[已执行命令]"
                            state.messages.append({
                                "role": "system",
                                "content": f"命令执行结果:\n" + "\n".join(cmd_results)
                            })
                            sys.stdout.write(f"{CYAN}{T('prompt_ai', state.lang)}{RESET} ")
                            sys.stdout.flush()
                            final_txt, _, final_response_time = stream_cnt(
                                state.client, state.model_name, state.messages, state.lang,
                                custom_prefix="", max_tokens=state.limit
                            )
                            state.messages.append({"role": "assistant", "content": final_txt})
                            response_time += final_response_time

                        print(f"{DIM}📊 {T('stats_model', state.lang)}: {state.model_name} | {T('stats_time', state.lang)}: {response_time:.2f}{T('stats_seconds', state.lang)}{RESET}")
                    else:
                        if out.strip():
                            print(out.strip()[:2000])
                except subprocess.TimeoutExpired:
                    print(f"{RED}Timeout{RESET}")
                except Exception as e:
                    print(f"{RED}{e}{RESET}")

        # ----------------- 内置 Agent 前缀拦截 -----------------
        elif u.startswith("@local "):
            try:
                from fr_cli.agent.builtins.local import handle_local
                handle_local(u, state)
            except Exception as e:
                print(f"{RED}@local Agent 执行失败: {e}{RESET}")

        elif u.startswith("@remote "):
            try:
                from fr_cli.agent.builtins.remote import handle_remote
                handle_remote(u, state)
            except Exception as e:
                print(f"{RED}@remote Agent 执行失败: {e}{RESET}")

        elif u.startswith("@spider "):
            try:
                from fr_cli.agent.builtins.spider import handle_spider
                handle_spider(u, state)
            except Exception as e:
                print(f"{RED}@spider Agent 执行失败: {e}{RESET}")

        elif u.startswith("@db "):
            try:
                from fr_cli.agent.builtins.db import handle_db
                handle_db(u, state)
            except Exception as e:
                print(f"{RED}@db Agent 执行失败: {e}{RESET}")

        elif u.startswith("@RAG ") or u.startswith("@rag "):
            try:
                from fr_cli.agent.builtins.rag import handle_rag
                handle_rag(u, state)
            except Exception as e:
                print(f"{RED}@RAG Agent 执行失败: {e}{RESET}")

        # ----------------- AI 正常对话 -----------------
        else:
            if state.master_agent.is_enabled():
                reply, _ = state.master_agent.handle(u)
                print(f"\n{CYAN}{reply}{RESET}")
            else:
                _handle_ai_chat(state, u)


if __name__ == "__main__":
    main()
