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
from fr_cli.memory.history import save_sess, load_sess, del_sess, get_sessions
from fr_cli.memory.context import extract_recent_turns, build_context_summary, save_context, load_context
from fr_cli.memory.session import create_session, update_session, list_sessions as list_auto_sessions, load_session as load_auto_session, delete_session as delete_auto_session
from fr_cli.addon.plugin import extract_code, PLUGIN_DIR
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


def _print_help(state, topic):
    """打印修仙指南"""
    topic_map = {
        "config": "config",
        "fs": "fs", "file": "fs", "files": "fs",
        "session": "session", "sess": "session",
        "plugin": "plugin", "plugins": "plugin", "skill": "plugin", "skills": "plugin",
        "mail": "mail", "email": "mail",
        "cron": "cron", "timer": "cron", "schedule": "cron",
        "web": "web", "search": "web",
        "disk": "disk", "cloud": "disk",
        "vision": "vision", "image": "vision", "see": "vision", "img": "vision",
        "shell": "shell", "matrix": "shell", "cmd": "shell",
        "tools": "tools", "tool": "tools", "invoke": "tools",
        "security": "security", "safe": "security", "sec": "security",
        "app": "app", "launcher": "app", "launch": "app", "open": "app",
        "agent": "agent", "agents": "agent",
        "builtin": "builtin", "builtins": "builtin",
        "dataframe": "dataframe", "data": "dataframe",
        "gatekeeper": "gatekeeper",
        "all": "all",
    }
    mapped = topic_map.get(topic, "")
    lang = state.lang

    if not mapped:
        print(f"{CYAN}{T('help_title', lang)}{RESET}")
        print(f"  {T('help_cfg', lang)} /model /key /limit /alias /export /update")
        print(f"  {T('help_fs', lang)} /ls /cat /cd /write /append /delete")
        print(f"  {T('help_sess', lang)} /save /load /del /undo")
        print(f"  {DIM}  自动存档: /session_list | /session_load <编号> | /session_del <编号>{RESET}")
        print(f"  {T('help_plugin', lang)} /skills (自动进化)")
        print(f"  {DIM}  思维: /mode <direct|cot|tot|react> — 切换 AI 推理模式{RESET}")
        print(f"  {T('help_extra', lang)} /mail_* /cron_* /web /fetch /disk_* /see")
        print(f"  {DIM}  Agent: /agent_create /agent_forge /agent_list /agent_run /agent_show /agent_edit /agent_delete{RESET}")
        print(f"  {DIM}  Agent API: /agent_server start [port] | stop | status{RESET}")
        print(f"  {DIM}  Agent 定时: /agent_cron_add <agent> <秒> [输入] | /agent_cron_list | /agent_cron_del <ID>{RESET}")
        print(f"  {DIM}  本机应用: /open <路径/URL> | /launch <应用> [目标] | /apps{RESET}")
        print(f"  {DIM}  内置Agent: @local <需求> | @remote [IP] <需求> | @spider <URL> [深度] | @db <需求> | @RAG <问题>{RESET}")
        print(f"  {DIM}  知识库: /rag_dir <目录> | /rag_sync | /rag_watch start/stop/status/log{RESET}")
        print(f"  {DIM}  数据: /read_excel <文件> | /read_csv <文件>{RESET}")
        print(f"  {T('help_shell', lang)} {T('shell_tip', lang)}\n                {T('pipe_tip', lang)}")
        print(f"\n{T('help_usage', lang)}")
    elif mapped == "all":
        for t in ["config", "fs", "session", "plugin", "mail", "cron", "web", "disk", "vision", "shell", "tools", "security", "app", "agent", "builtin", "dataframe", "gatekeeper"]:
            print(T(f"help_detail_{t}", lang))
            print()
    else:
        detail = T(f"help_detail_{mapped}", lang)
        if detail:
            print(detail)
        else:
            print(T("help_not_found", lang, topic))


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

        updated_messages[-1]["content"] = clean_txt if clean_txt.strip() else "[已执行命令]"
        updated_messages.append({
            "role": "system",
            "content": f"命令执行结果:\n" + "\n".join(cmd_results)
        })

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

def _cmd_exit(state, parts):
    print_bye()
    return True


def _cmd_help(state, parts):
    arg1 = parts[1] if len(parts) > 1 else ""
    _print_help(state, arg1.lower())
    return False


def _cmd_model(state, parts):
    arg1 = parts[1] if len(parts) > 1 else ""
    if arg1:
        state.update_model(arg1)
        print(f"{GREEN}{T('ok_model', state.lang, arg1)}{RESET}")
    return False


def _cmd_key(state, parts):
    arg1 = parts[1] if len(parts) > 1 else ""
    if arg1:
        state.update_key(arg1)
        print(f"{GREEN}{T('ok_key', state.lang)}{RESET}")
    return False


def _cmd_limit(state, parts):
    arg1 = parts[1] if len(parts) > 1 else ""
    if arg1:
        try:
            v = int(arg1)
            if v < 1000:
                raise ValueError
            state.update_limit(v)
            print(f"{GREEN}{T('ok_limit', state.lang, v)}{RESET}")
        except ValueError:
            print(f"{RED}{T('err_limit', state.lang)}{RESET}")
    return False


def _cmd_lang(state, parts):
    arg1 = parts[1] if len(parts) > 1 else ""
    if arg1:
        if arg1 in ["zh", "en"]:
            state.update_lang(arg1)
            print(f"{GREEN}语言已切换为: {'中文' if arg1 == 'zh' else 'English'}{RESET}")
        else:
            print(f"{RED}支持的语言: zh (中文), en (English){RESET}")
    return False


def _cmd_dir(state, parts):
    arg1 = parts[1] if len(parts) > 1 else ""
    if arg1:
        ok, m = state.vfs.add(arg1, state.lang)
        if ok:
            state.cfg["allowed_dirs"] = state.vfs.ds
            state.save_cfg()
        print(m)
    return False


def _cmd_dirs(state, parts):
    items, err = state.vfs.list_dirs(state.lang)
    if err:
        print(err)
    else:
        print(f"{CYAN}📂 已挂载的洞府:{RESET}")
        for item in items:
            print(item)
    return False


def _cmd_rmdir(state, parts):
    arg1 = parts[1] if len(parts) > 1 else ""
    if arg1:
        ok, m = state.vfs.remove_dir(arg1, state.lang)
        if ok:
            state.cfg["allowed_dirs"] = state.vfs.ds
            state.save_cfg()
        print(m)
    return False


def _cmd_save(state, parts):
    arg1 = parts[1] if len(parts) > 1 else ""
    if arg1:
        state.update_session_name(arg1)
        if save_sess(arg1, state.messages):
            print(f"{GREEN}{T('ok_sess_save', state.lang, arg1)}{RESET}")
            recent = extract_recent_turns(state.messages, 5)
            ctx = build_context_summary(recent, state.lang)
            save_context(arg1, ctx)
    return False


def _cmd_load(state, parts):
    ss = get_sessions()
    if not ss:
        print(T("no_sess", state.lang))
        return False
    for i, s in enumerate(ss):
        print(f"  [{i}] {s['name']}")
    idx = input(f"{YELLOW}ID: {RESET}").strip()
    if idx.isdigit():
        sp = T("sys_prompt", state.lang)
        ok, m, name = load_sess(int(idx), sp)
        if ok:
            state.messages = m
            state.update_session_name(name)
            state.context_summary = load_context(name)
            print(f"{GREEN}{T('ok_sess_load', state.lang, name)}{RESET}")
    return False


def _cmd_del(state, parts):
    ss = get_sessions()
    if not ss:
        print(T("no_sess", state.lang))
        return False
    for i, s in enumerate(ss):
        print(f"  [{i}] {s['name']}")
    idx = input(f"{YELLOW}ID: {RESET}").strip()
    if idx.isdigit() and del_sess(int(idx)):
        print(GREEN + T("ok_sess_del", state.lang) + RESET)
    return False


def _cmd_session_list(state, parts):
    """列出所有按日期自动保存的会话"""
    sessions = list_auto_sessions()
    if not sessions:
        print(f"{DIM}暂无自动会话存档。{RESET}")
        return False
    print(f"{CYAN}📁 自动会话列表:{RESET}")
    for s in sessions:
        print(f"  [{s['index']}] {CYAN}{s['filename']}{RESET} | 创建: {s['created_at']} | 消息: {s['msg_count']} 条")
    return False


def _cmd_session_load(state, parts):
    """加载指定索引的自动会话并继续对话"""
    arg1 = parts[1] if len(parts) > 1 else ""
    if not arg1 or not arg1.isdigit():
        print(f"{YELLOW}用法: /session_load <编号>  (先用 /session_list 查看编号){RESET}")
        return False
    idx = int(arg1)
    sp = T("sys_prompt", state.lang)
    ok, msgs, fname = load_auto_session(idx, sp)
    if ok:
        state.messages = msgs
        print(f"{GREEN}✅ 已加载会话 [{fname}]，共 {len(msgs)} 条消息。{RESET}")
        print(f"{DIM}   后续对话将追加到当前自动会话存档中。{RESET}")
    else:
        print(f"{RED}❌ 加载失败，编号 {idx} 无效。{RESET}")
    return False


def _cmd_session_del(state, parts):
    """删除指定索引的自动会话"""
    arg1 = parts[1] if len(parts) > 1 else ""
    if not arg1 or not arg1.isdigit():
        print(f"{YELLOW}用法: /session_del <编号>{RESET}")
        return False
    idx = int(arg1)
    if delete_auto_session(idx):
        print(f"{GREEN}✅ 已删除编号 {idx} 的会话。{RESET}")
    else:
        print(f"{RED}❌ 删除失败，编号 {idx} 无效。{RESET}")
    return False


def _cmd_see(state, parts):
    from fr_cli.weapon.vision import prep_see_msg
    arg1 = parts[1] if len(parts) > 1 else ""
    if not arg1:
        return False
    if state.model_name != "glm-4v-plus":
        print(f"{YELLOW}{T('see_warn', state.lang)}{RESET}")
    print(f"{CYAN}{T('see_ing', state.lang)}{RESET}")
    prep_see_msg(state.messages, arg1, parts[2] if len(parts) > 2 else "")
    txt, _, response_time = stream_cnt(
        state.client, state.model_name, state.messages, state.lang,
        max_tokens=state.limit
    )
    state.messages.append({"role": "assistant", "content": txt})
    sys_stats = get_sys_stats(state.lang)
    stats_extra = f" | {sys_stats}" if sys_stats else ""
    print(f"{DIM}📊 {T('stats_model', state.lang)}: {state.model_name} | {T('stats_time', state.lang)}: {response_time:.2f}{T('stats_seconds', state.lang)}{stats_extra}{RESET}")
    return False


def _cmd_update(state, parts):
    from fr_cli.breakthrough.update import update_check, update_and_restart
    arg1 = parts[1] if len(parts) > 1 else ""
    if arg1 == "check":
        ok, info, err = update_check(verbose=False)
        if err:
            print(f"{RED}[更新] 检查失败: {err}{RESET}")
        elif not ok:
            print(f"{GREEN}[更新] 当前已是最新版本。{RESET}")
        else:
            ver = info.get("version", "?")
            note = info.get("release_note", "")
            print(f"{YELLOW}[更新] 发现新版本: {ver}{RESET}")
            if note:
                print(f"{DIM}更新说明:\n{note}{RESET}")
            print(f"{DIM}输入 /update run 执行更新{RESET}")
    elif arg1 == "run":
        print(f"{YELLOW}[更新] 正在连接天道获取最新法器...{RESET}")
        ok, msg = update_and_restart(verbose=True, allow_restart=True)
        if ok:
            print(f"{GREEN}{msg}{RESET}")
        else:
            print(f"{RED}{msg}{RESET}")
    else:
        print(f"{DIM}用法: /update check (检查) | /update run (执行更新){RESET}")
    return False


def _cmd_agent_server(state, parts):
    from fr_cli.agent.server import AgentHTTPServer
    arg1 = parts[1] if len(parts) > 1 else ""
    if arg1 == "start":
        port = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 17890
        if state.agent_server is None:
            state.agent_server = AgentHTTPServer(state, port=port)
        ok, msg = state.agent_server.start()
        color = GREEN if ok else YELLOW
        print(f"{color}{msg}{RESET}")
    elif arg1 == "stop":
        if state.agent_server is None:
            print(f"{YELLOW}服务未运行{RESET}")
        else:
            ok, msg = state.agent_server.stop()
            color = GREEN if ok else YELLOW
            print(f"{color}{msg}{RESET}")
    elif arg1 == "status":
        if state.agent_server is None:
            print(f"{DIM}未运行{RESET}")
        else:
            print(f"{CYAN}{state.agent_server.status()}{RESET}")
    else:
        print(f"{DIM}用法: /agent_server start [port] | /agent_server stop | /agent_server status{RESET}")
    return False


def _cmd_mode(state, parts):
    """切换思维模式：direct / cot / tot / react"""
    from fr_cli.core.thinking import ThinkingEngine
    arg1 = parts[1] if len(parts) > 1 else ""
    if not arg1:
        print(f"{CYAN}当前思维模式: {state.thinking_mode}{RESET}")
        print(f"{DIM}可用模式: direct（直接回答）| cot（思维链）| tot（思维树）| react（推理+行动）{RESET}")
        return False
    mode = arg1.lower()
    if not ThinkingEngine.is_valid_mode(mode):
        print(f"{RED}无效模式: {mode}{RESET}")
        print(f"{DIM}可用模式: direct | cot | tot | react{RESET}")
        return False
    state.update_thinking_mode(mode)
    mode_desc = {
        "direct": "直接回答（默认）",
        "cot": "思维链 — 先进行问题拆解和自我验证，再回答",
        "tot": "思维树 — 生成多分支策略树，评估后选择最优路径",
        "react": "ReAct — 每一步先思考再行动，循环直到问题解决",
    }
    print(f"{GREEN}✅ 思维模式已切换: {mode_desc.get(mode, mode)}{RESET}")
    return False


def _cmd_gatekeeper(state, parts):
    arg1 = parts[1] if len(parts) > 1 else ""
    if arg1 == "start":
        from fr_cli.weapon.cron import _default_manager as _cron_mgr
        from fr_cli.gatekeeper.manager import read_daemon_config
        # 保留已有的 agent_crons 配置（如果存在）
        existing_cfg = read_daemon_config()
        daemon_cfg = {
            "agent_server_port": state.agent_server.port if (state.agent_server and state.agent_server.is_running()) else None,
            "cron_jobs": _cron_mgr.export_jobs(),
            "agent_crons": existing_cfg.get("agent_crons", []),
            "lang": state.lang,
        }
        ok, msg = state.gatekeeper.save_daemon_config(daemon_cfg)
        if not ok:
            print(f"{YELLOW}{msg}{RESET}")
        ok, msg = state.gatekeeper.start()
        color = GREEN if ok else YELLOW
        print(f"{color}{msg}{RESET}")
    elif arg1 == "stop":
        ok, msg = state.gatekeeper.stop()
        color = GREEN if ok else YELLOW
        print(f"{color}{msg}{RESET}")
    elif arg1 == "status":
        print(f"{CYAN}{state.gatekeeper.status()}{RESET}")
    else:
        print(f"{DIM}用法: /gatekeeper start | /gatekeeper stop | /gatekeeper status{RESET}")
    return False


def _cmd_open(state, parts):
    from fr_cli.weapon.launcher import open_file
    arg1 = parts[1] if len(parts) > 1 else ""
    if arg1:
        ok, msg = open_file(arg1, state.lang)
        color = GREEN if ok else RED
        print(f"{color}{msg}{RESET}")
    return False


def _cmd_launch(state, parts):
    from fr_cli.weapon.launcher import launch_app
    arg1 = parts[1] if len(parts) > 1 else ""
    if arg1:
        target = parts[2] if len(parts) > 2 else None
        ok, msg = launch_app(arg1, target, state.lang)
        color = GREEN if ok else RED
        print(f"{color}{msg}{RESET}")
    return False


def _cmd_apps(state, parts):
    from fr_cli.weapon.launcher import list_apps
    res, err = list_apps(state.lang)
    if err:
        print(f"{RED}{err}{RESET}")
    else:
        print(f"{CYAN}{res}{RESET}")
    return False


def _cmd_agent_create(state, parts):
    from fr_cli.agent.generator import generate_agent
    from fr_cli.agent.manager import save_persona, save_skills, save_agent_code, create_agent_dir
    arg1 = parts[1] if len(parts) > 1 else ""
    desc = parts[2] if len(parts) > 2 else ""
    if not arg1 or not desc:
        print(f"{YELLOW}用法: /agent_create <名称> <需求描述>{RESET}")
        return False
    d = create_agent_dir(arg1)
    result = generate_agent(state.client, state.model_name, arg1, desc, state.lang)
    if result["persona"]:
        save_persona(arg1, result["persona"])
    if result["skills"]:
        save_skills(arg1, result["skills"])
    if result["code"]:
        save_agent_code(arg1, result["code"])
    print(f"{GREEN}✅ Agent [{arg1}] 铸造完成！{RESET}")
    print(f"{DIM}  人设: {'已生成' if result['persona'] else '未生成'}{RESET}")
    print(f"{DIM}  技能: {'已生成' if result['skills'] else '未生成'}{RESET}")
    print(f"{DIM}  代码: {'已生成' if result['code'] else '未生成'}{RESET}")
    print(f"{DIM}  路径: {d}{RESET}")
    return False


def _cmd_agent_list(state, parts):
    from fr_cli.agent.manager import list_agents
    agents = list_agents()
    if not agents:
        print(f"{YELLOW}暂无 Agent 分身。使用 /agent_create <名称> <描述> 创建。{RESET}")
    else:
        print(f"{CYAN}已创建的 Agent 分身:{RESET}")
        for a in agents:
            flags = []
            if a["has_persona"]: flags.append("人设")
            if a["has_memory"]: flags.append("记忆")
            if a["has_skills"]: flags.append("技能")
            flag_str = f" ({', '.join(flags)})" if flags else ""
            print(f"  {a['name']}{flag_str}")
    return False


def _cmd_agent_delete(state, parts):
    from fr_cli.agent.manager import delete_agent
    arg1 = parts[1] if len(parts) > 1 else ""
    if arg1:
        if delete_agent(arg1):
            print(f"{GREEN}✅ Agent [{arg1}] 已抹除。{RESET}")
        else:
            print(f"{RED}Agent [{arg1}] 不存在。{RESET}")
    return False


def _cmd_agent_show(state, parts):
    from fr_cli.agent.manager import agent_exists, load_persona, load_memory, load_skills, load_agent_code
    from fr_cli.agent.workflow import load_workflow
    arg1 = parts[1] if len(parts) > 1 else ""
    if not arg1:
        return False
    if not agent_exists(arg1):
        print(f"{RED}Agent [{arg1}] 不存在。{RESET}")
    else:
        print(f"{CYAN}═══ Agent: {arg1} ═══{RESET}")
        p = load_persona(arg1)
        m = load_memory(arg1)
        s = load_skills(arg1)
        c = load_agent_code(arg1)
        w = load_workflow(arg1)
        if p: print(f"\n{DIM}[人设]{RESET}\n{p[:500]}{'...' if len(p) > 500 else ''}")
        if s: print(f"\n{DIM}[技能]{RESET}\n{s[:500]}{'...' if len(s) > 500 else ''}")
        if m: print(f"\n{DIM}[记忆]{RESET}\n{m[:300]}{'...' if len(m) > 300 else ''}")
        if c: print(f"\n{DIM}[代码]{RESET}\n{c[:300]}{'...' if len(c) > 300 else ''}")
        if w: print(f"\n{DIM}[工作流]{RESET}\n{w[:300]}{'...' if len(w) > 300 else ''}")
    return False


def _cmd_agent_run(state, parts):
    from fr_cli.agent.executor import run_agent
    arg1 = parts[1] if len(parts) > 1 else ""
    if not arg1:
        return False
    run_args = parts[2] if len(parts) > 2 else ""
    kwargs = {"user_input": run_args} if run_args else {}
    result, err = run_agent(arg1, state, **kwargs)
    if err:
        print(f"{RED}{err}{RESET}")
    else:
        print(f"{GREEN}{result}{RESET}")
    return False


def _cmd_agent_edit(state, parts):
    from fr_cli.agent.manager import agent_exists, save_persona, save_memory, save_skills, save_agent_code
    from fr_cli.agent.workflow import save_workflow
    arg1 = parts[1] if len(parts) > 1 else ""
    if not arg1:
        return False
    if not agent_exists(arg1):
        print(f"{RED}Agent [{arg1}] 不存在。{RESET}")
        return False
    file_type = parts[2] if len(parts) > 2 else ""
    valid_types = {"persona", "memory", "skills", "agent", "workflow"}
    if file_type not in valid_types:
        print(f"{YELLOW}用法: /agent_edit <名称> <类型>，类型: persona/memory/skills/agent/workflow{RESET}")
        return False
    print(f"{CYAN}请输入新的 {file_type} 内容（Ctrl+D 结束）:{RESET}")
    try:
        new_content = sys.stdin.read().strip()
    except (EOFError, KeyboardInterrupt):
        new_content = ""
    if not new_content:
        print(f"{YELLOW}内容为空，未保存。{RESET}")
        return False
    if file_type == "persona":
        save_persona(arg1, new_content)
    elif file_type == "memory":
        save_memory(arg1, new_content)
    elif file_type == "skills":
        save_skills(arg1, new_content)
    elif file_type == "agent":
        save_agent_code(arg1, new_content)
    elif file_type == "workflow":
        save_workflow(arg1, new_content)
    print(f"{GREEN}✅ {file_type} 已更新。{RESET}")
    return False


def _cmd_agent_forge(state, parts):
    """从最近一次 AI 回复中提取 Python 代码块，铸造为 Agent 分身。"""
    from fr_cli.agent.manager import create_agent_dir, save_agent_code, save_persona, save_skills, agent_exists
    from fr_cli.addon.plugin import extract_code
    arg1 = parts[1] if len(parts) > 1 else ""
    if not arg1:
        print(f"{YELLOW}用法: /agent_forge <名称>{RESET}")
        print(f"{DIM}  从最近一次 AI 回复中提取 Python 代码块，创建 Agent 分身。{RESET}")
        return False

    safe_name = "".join(c for c in arg1 if c.isalnum() or c == '_')
    if not safe_name:
        print(f"{RED}名称无效，仅允许字母/数字/下划线{RESET}")
        return False

    # 从历史消息中倒序查找最近包含 def run 的 Python 代码块
    code = ""
    for msg in reversed(state.messages):
        if msg.get("role") == "assistant":
            c = extract_code(msg.get("content", ""))
            if c and "def run" in c:
                code = c
                break

    if not code:
        print(f"{YELLOW}未在最近 AI 回复中找到包含 def run 的 Python 代码块。{RESET}")
        print(f"{DIM}提示：先让 AI 生成一段包含 def run(context, **kwargs) 的代码，再执行此命令。{RESET}")
        return False

    if agent_exists(safe_name):
        confirm = input(f"{YELLOW}Agent [{safe_name}] 已存在，是否覆盖? [y/N]: {RESET}").strip().lower()
        if confirm not in ("y", "yes"):
            print(f"{DIM}已取消。{RESET}")
            return False

    d = create_agent_dir(safe_name)
    save_agent_code(safe_name, code)

    # 自动生成简单人设和技能（如果尚不存在）
    from fr_cli.agent.manager import load_persona, load_skills
    if not load_persona(safe_name):
        save_persona(safe_name, f"#{safe_name}\n\n由 AI 对话铸造的 Agent 分身。")
    if not load_skills(safe_name):
        save_skills(safe_name, "## 技能\n\n- 执行自定义 Python 逻辑\n- 入口: run(context, **kwargs)")

    print(f"{GREEN}✅ Agent [{safe_name}] 铸造完成！{RESET}")
    print(f"{DIM}  路径: {d}{RESET}")
    print(f"{DIM}  运行: /agent_run {safe_name} [参数]{RESET}")
    return False


def _cmd_remote_setup(state, parts):
    from fr_cli.agent.builtins.remote import _setup_wizard
    _setup_wizard(state.lang)
    return False


def _cmd_db_setup(state, parts):
    from fr_cli.agent.builtins.db import _setup_wizard as db_setup
    db_setup(state.lang)
    return False


def _cmd_agent_cron_add(state, parts):
    """为 Agent 分身添加定时任务"""
    from fr_cli.gatekeeper.manager import read_daemon_config, sync_gatekeeper_cron_jobs
    from fr_cli.agent.manager import agent_exists
    arg1 = parts[1] if len(parts) > 1 else ""  # agent_name
    arg2 = parts[2] if len(parts) > 2 else ""  # interval
    arg3 = parts[3] if len(parts) > 3 else ""  # input
    if not arg1 or not arg2:
        print(f"{YELLOW}用法: /agent_cron_add <agent名称> <间隔秒> [输入内容]{RESET}")
        return False
    if not agent_exists(arg1):
        print(f"{RED}Agent [{arg1}] 不存在。{RESET}")
        return False
    try:
        interval = float(arg2)
        if interval < 5:
            raise ValueError
    except ValueError:
        print(f"{RED}间隔秒数需为 >= 5 的数字{RESET}")
        return False

    cfg = read_daemon_config()
    agent_crons = cfg.get("agent_crons", [])
    # 分配新 ID
    max_id = max([j.get("id", 0) for j in agent_crons] + [0])
    new_job = {
        "id": max_id + 1,
        "agent_name": arg1,
        "interval": interval,
        "agent_input": arg3,
        "cmd": arg1,  # 兼容字段
    }
    agent_crons.append(new_job)
    sync_gatekeeper_cron_jobs(agent_crons=agent_crons)
    print(f"{GREEN}✅ Agent 定时任务已添加 (ID: {new_job['id']}){RESET}")
    print(f"{DIM}  Agent: {arg1} | 间隔: {interval}秒 | 输入: {arg3 or '(无)'}{RESET}")

    # 如果 gatekeeper 正在运行，提示热重载将自动生效
    if state.gatekeeper.is_running():
        print(f"{DIM}  Gatekeeper 运行中，新任务将在约30秒内自动生效。{RESET}")
    else:
        print(f"{DIM}  提示: Gatekeeper 未运行，任务将在下次 /gatekeeper start 时生效。{RESET}")
    return False


def _cmd_agent_cron_list(state, parts):
    """列出 Agent 分身定时任务"""
    from fr_cli.gatekeeper.manager import read_daemon_config
    cfg = read_daemon_config()
    agent_crons = cfg.get("agent_crons", [])
    if not agent_crons:
        print(f"{YELLOW}暂无 Agent 定时任务。{RESET}")
        print(f"{DIM}用法: /agent_cron_add <agent名称> <间隔秒> [输入内容]{RESET}")
        return False
    print(f"{CYAN}Agent 定时任务列表:{RESET}")
    for j in agent_crons:
        print(f"  {GREEN}ID:{j['id']}{RESET} | Agent: {j.get('agent_name', '?')} | {YELLOW}{j['interval']}s{RESET} | 输入: {j.get('agent_input', '') or '(无)'}")
    return False


def _cmd_agent_cron_del(state, parts):
    """删除 Agent 分身定时任务"""
    from fr_cli.gatekeeper.manager import read_daemon_config, sync_gatekeeper_cron_jobs
    arg1 = parts[1] if len(parts) > 1 else ""
    if not arg1 or not arg1.isdigit():
        print(f"{YELLOW}用法: /agent_cron_del <ID>{RESET}")
        return False
    job_id = int(arg1)
    cfg = read_daemon_config()
    agent_crons = cfg.get("agent_crons", [])
    new_crons = [j for j in agent_crons if j.get("id") != job_id]
    if len(new_crons) == len(agent_crons):
        print(f"{RED}未找到 ID 为 {job_id} 的 Agent 定时任务。{RESET}")
        return False
    sync_gatekeeper_cron_jobs(agent_crons=new_crons)
    print(f"{GREEN}✅ Agent 定时任务 ID:{job_id} 已删除。{RESET}")
    if state.gatekeeper.is_running():
        print(f"{DIM}  Gatekeeper 运行中，变更将在约30秒内自动生效。{RESET}")
    return False


def _cmd_rag_dir(state, parts):
    arg1 = parts[1] if len(parts) > 1 else ""
    if not arg1:
        return False
    from pathlib import Path as _Path
    p = _Path(arg1)
    if not p.exists():
        print(f"{RED}目录不存在: {arg1}{RESET}")
    else:
        state.cfg["rag_dir"] = str(p.resolve())
        state.save_cfg()
        print(f"{GREEN}✅ 知识库目录已设置: {p.resolve()}{RESET}")
        from fr_cli.agent.builtins.rag import get_rag_manager, RAGWatcherManager
        mgr = get_rag_manager(str(p.resolve()))
        ok, msg = mgr.sync_directory()
        print(f"{GREEN if ok else YELLOW}{msg}{RESET}")
        # 如果独立守护进程未运行，才启动内置 watcher
        watcher = RAGWatcherManager()
        if ok and not watcher.is_running():
            mgr.start_watcher()
            print(f"{DIM}内置后台监控已启动（如需持久化守护，请使用 /rag_watch start）{RESET}")
    return False


def _cmd_rag_watch(state, parts):
    """管理 RAG 知识库独立守护进程"""
    from fr_cli.agent.builtins.rag import RAGWatcherManager
    arg1 = parts[1] if len(parts) > 1 else ""
    watcher = RAGWatcherManager()

    if arg1 == "start":
        kb_dir = parts[2] if len(parts) > 2 else state.cfg.get("rag_dir", "")
        if not kb_dir:
            print(f"{YELLOW}未设置知识库目录，请先使用 /rag_dir <目录> 设置。{RESET}")
            return False
        # 解析可选参数 --interval
        interval = 30
        for i, part in enumerate(parts):
            if part == "--interval" and i + 1 < len(parts):
                try:
                    interval = int(parts[i + 1])
                except ValueError:
                    pass
        ok, msg = watcher.start(kb_dir, interval=interval)
        color = GREEN if ok else YELLOW
        print(f"{color}{msg}{RESET}")
        if ok:
            print(f"{DIM}日志文件: ~/.fr_cli_rag_watcher.log{RESET}")
            print(f"{DIM}停止命令: /rag_watch stop{RESET}")

    elif arg1 == "stop":
        ok, msg = watcher.stop()
        color = GREEN if ok else YELLOW
        print(f"{color}{msg}{RESET}")

    elif arg1 == "status":
        print(f"{CYAN}{watcher.status()}{RESET}")

    elif arg1 == "log":
        lines = 50
        for i, part in enumerate(parts):
            if part == "--lines" and i + 1 < len(parts):
                try:
                    lines = int(parts[i + 1])
                except ValueError:
                    pass
        log = watcher.get_log(lines=lines)
        print(f"{DIM}--- RAG 守护进程日志（最后 {lines} 行）---{RESET}")
        print(log)
        print(f"{DIM}--- EOF ---{RESET}")

    else:
        print(f"{DIM}用法: /rag_watch start [目录] [--interval N] | /rag_watch stop | /rag_watch status | /rag_watch log [--lines N]{RESET}")
    return False


def _cmd_rag_sync(state, parts):
    """手动同步知识库"""
    from fr_cli.agent.builtins.rag import get_rag_manager, RAGWatcherManager
    kb_dir = state.cfg.get("rag_dir", "")
    if not kb_dir:
        print(f"{YELLOW}未设置知识库目录。{RESET}")
        arg1 = parts[1] if len(parts) > 1 else ""
        if arg1:
            from pathlib import Path as _Path
            p = _Path(arg1)
            if p.exists():
                state.cfg["rag_dir"] = str(p.resolve())
                state.save_cfg()
                kb_dir = str(p.resolve())
            else:
                print(f"{RED}目录不存在: {arg1}{RESET}")
                return False
        else:
            return False

    mgr = get_rag_manager(kb_dir)
    print(f"{CYAN}📚 正在同步知识库...{RESET}")
    ok, msg = mgr.sync_directory()
    color = GREEN if ok else YELLOW
    print(f"{color}{msg}{RESET}")

    watcher = RAGWatcherManager()
    if watcher.is_running():
        print(f"{DIM}ℹ️ 独立守护进程正在运行，知识库将自动保持同步。{RESET}")
    return False


def _cmd_read_excel(state, parts):
    from fr_cli.weapon.dataframe import read_excel
    arg1 = parts[1] if len(parts) > 1 else ""
    if arg1:
        res, err = read_excel(arg1, lang=state.lang)
        if err:
            print(f"{RED}{err}{RESET}")
        else:
            print(f"{CYAN}{res[:2000]}{RESET}")
            if len(res) > 2000:
                print(f"{DIM}... (共 {len(res)} 字符，使用 AI 对话进行分析){RESET}")
    return False


def _cmd_read_csv(state, parts):
    from fr_cli.weapon.dataframe import read_csv
    arg1 = parts[1] if len(parts) > 1 else ""
    if arg1:
        res, err = read_csv(arg1, lang=state.lang)
        if err:
            print(f"{RED}{err}{RESET}")
        else:
            print(f"{CYAN}{res[:2000]}{RESET}")
            if len(res) > 2000:
                print(f"{DIM}... (共 {len(res)} 字符，使用 AI 对话进行分析){RESET}")
    return False


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
            _handle_ai_chat(state, u)


if __name__ == "__main__":
    main()
