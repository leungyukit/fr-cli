"""
REPL 命令路由处理器
从 main.py 提取的所有 / 命令实现，减轻主模块负担。
"""
import sys

from fr_cli.lang.i18n import T
from fr_cli.ui.ui import (
    CYAN, RED, YELLOW, GREEN, DIM, RESET,
    print_bye
)
from fr_cli.memory.history import save_sess, load_sess, del_sess, get_sessions
from fr_cli.memory.context import load_context, extract_recent_turns, build_context_summary, save_context
from fr_cli.memory.session import (
    list_sessions as list_auto_sessions,
    load_session as load_auto_session,
    delete_session as delete_auto_session,
)
from fr_cli.addon.plugin import extract_code
from fr_cli.core.stream import stream_cnt
from fr_cli.core.sysmon import get_sys_stats
from fr_cli.agent.manager import (
    create_agent_dir, save_agent_code, save_persona, save_skills,
    save_memory, agent_exists, list_agents, delete_agent,
    load_persona, load_memory, load_skills,
)
from fr_cli.agent.executor import run_agent


def _provider_has_key(state, provider_id):
    """检查指定道统是否已配置 API Key（zhipu 向后兼容顶层 key）"""
    providers_cfg = state.cfg.get("providers", {})
    pcfg = providers_cfg.get(provider_id, {})
    has_key = bool(pcfg.get("key"))
    if not has_key and provider_id == "zhipu":
        has_key = bool(state.cfg.get("key", ""))
    return has_key


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
        print(f"  {DIM}  主控Agent: /master on|off|status — 启用自我进化型主Agent{RESET}")
        print(f"  {T('help_plugin', lang)} /skills (自动进化)")
        print(f"  {DIM}  思维: /mode <direct|cot|tot|react> — 切换 AI 推理模式{RESET}")
        print(f"  {T('help_extra', lang)} /mail_* /cron_* /web /fetch /disk_* /see")
        print(f"  {DIM}  Agent: /agent_create /agent_forge /agent_list /agent_run /agent_show /agent_edit /agent_delete{RESET}")
        print(f"  {DIM}  Agent API: /agent_server start [port] | stop | status{RESET}")
        print(f"  {DIM}  Agent 发布: /agent_publish — 生成对外连接信息{RESET}")
        print(f"  {DIM}  Agent 定时: /agent_cron_add <agent> <秒> [输入] | /agent_cron_list | /agent_cron_del <ID>{RESET}")
        print(f"  {DIM}  远程Agent: /remote_agent_add <name> <host> <port> <token> [desc] | /remote_agent_list | /remote_agent_del <name>{RESET}")
        print(f"  {DIM}  远程发现: /remote_agent_scan <host> <port> <token> | /remote_agent_import <host> <port> <token> [prefix]{RESET}")
        print(f"  {DIM}  本机应用: /open <路径/URL> | /launch <应用> [目标] | /apps{RESET}")
        print(f"  {DIM}  内置Agent: @local <需求> | @remote [IP] <需求> | @spider <URL> [深度] | @db <需求> | @RAG <问题>{RESET}")
        print(f"  {DIM}  知识库: /rag_dir <目录> | /rag_sync | /rag_watch start/stop/status/log{RESET}")
        print(f"  {DIM}  数据: /read_excel <文件> | /read_csv <文件>{RESET}")
        print(f"  {DIM}  MCP: /mcp_list | /mcp_add <名称> <命令> [参数...] | /mcp_del <名称> | /mcp_enable <名称> | /mcp_disable <名称> | /mcp_refresh{RESET}")
        print(f"  {T('help_shell', lang)} {T('shell_tip', lang)}\n                {T('pipe_tip', lang)}")
        print(f"\n{T('help_usage', lang)}")
    elif mapped == "all":
        for t in ["config", "fs", "session", "plugin", "mail", "cron", "web", "disk", "vision", "shell", "tools", "security", "app", "agent", "builtin", "dataframe", "gatekeeper", "mcp"]:
            print(T(f"help_detail_{t}", lang))
            print()
    else:
        detail = T(f"help_detail_{mapped}", lang)
        if detail:
            print(detail)
        else:
            print(T("help_not_found", lang, topic))


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
        ok = state.update_model(arg1)
        if ok:
            print(f"{GREEN}✅ 已切换: [{state.provider}] {state.model_name}{RESET}")
            # 检查新道统是否已配置 API Key，若未配置则引导输入
            if not _provider_has_key(state, state.provider):
                print(f"{YELLOW}⚠️ [{state.provider}] 尚未配置 API Key{RESET}")
                k = input(f"👉 请输入 [{state.provider}] 的 API Key: ").strip()
                if k:
                    state.update_key(k)
                    print(f"{GREEN}✅ [{state.provider}] API Key 已保存{RESET}")
                else:
                    print(f"{RED}❌ 未输入 Key，[{state.provider}] 可能无法正常使用{RESET}")
        else:
            print(f"{RED}❌ 无效的提供商或模型: {arg1}{RESET}")
    else:
        # 显示当前道统与可用模型及 key 配置状态
        from fr_cli.core.llm import list_providers
        print(f"{CYAN}🧠 当前道统: [{state.provider}] {state.model_name}{RESET}")
        print(f"\n{DIM}可用道统与默认模型:{RESET}")
        providers_cfg = state.cfg.get("providers", {})
        for p in list_providers():
            marker = " 👈 当前" if p["id"] == state.provider else ""
            has_key = _provider_has_key(state, p["id"])
            key_status = f"{GREEN}✅ 已配置{RESET}" if has_key else f"{RED}❌ 未配置{RESET}"
            print(f"  {CYAN}{p['id']}{RESET} — {p['name']}{DIM} (默认: {p['default_model']}){RESET} {key_status}{marker}")
        print(f"\n{DIM}用法:{RESET}")
        print(f"  /model <模型名>           — 切换当前道统下的模型")
        print(f"  /model <道统>:<模型名>    — 同时切换道统和模型")
        print(f"  示例: /model deepseek:deepseek-chat")
    return False


def _cmd_key(state, parts):
    """
    设置 API Key
    用法:
      /key <key>              — 为当前道统设置 key
      /key <道统> <key>       — 为指定道统设置 key
    """
    arg1 = parts[1] if len(parts) > 1 else ""
    arg2 = parts[2] if len(parts) > 2 else ""
    if arg1 and arg2:
        # /key <provider> <key>
        target_provider = arg1
        from fr_cli.core.llm import get_provider_info
        if not get_provider_info(target_provider):
            print(f"{RED}❌ 无效道统: {target_provider}{RESET}")
            return False
        # 临时切到目标道统设置 key，再切回来
        original_provider = state.provider
        state.update_provider(target_provider)
        state.update_key(arg2)
        # 如果原来不是目标道统，切回去
        if original_provider != target_provider:
            state.update_provider(original_provider)
        print(f"{GREEN}✅ [{target_provider}] API Key 已更新{RESET}")
    elif arg1:
        # /key <key>
        state.update_key(arg1)
        print(f"{GREEN}✅ [{state.provider}] API Key 已更新{RESET}")
    else:
        print(f"{YELLOW}⚠️ 用法:{RESET}")
        print(f"  /key <API密钥>              — 为当前道统 [{state.provider}] 设置密钥")
        print(f"  /key <道统> <API密钥>       — 为指定道统设置密钥")
    return False


def _cmd_providers(state, parts):
    """
    多模型道统配置管理
    用法:
      /providers                  — 查看所有道统配置
      /providers add <道统> <key> [模型] — 添加/更新道统配置
      /providers del <道统>       — 删除道统配置
      /providers use <道统>       — 切换到指定道统
    """
    sub = parts[1] if len(parts) > 1 else ""
    arg1 = parts[2] if len(parts) > 2 else ""
    arg2 = parts[3] if len(parts) > 3 else ""

    providers_cfg = state.cfg.setdefault("providers", {})

    if not sub or sub == "list":
        from fr_cli.core.llm import list_providers, get_provider_info
        print(f"{CYAN}📜 道统配置总览{RESET}")
        for p in list_providers():
            has_key = _provider_has_key(state, p["id"])
            key_status = f"{GREEN}✅{RESET}" if has_key else f"{RED}❌{RESET}"
            model = pcfg.get("model", p["default_model"])
            info = get_provider_info(p["id"])
            base_url = pcfg.get("base_url") or info.get("base_url", "默认")
            active = f" {YELLOW}👈 当前使用{RESET}" if p["id"] == state.provider else ""
            print(f"\n  {key_status} {CYAN}{p['id']}{RESET} — {p['name']}{active}")
            print(f"      模型: {DIM}{model}{RESET}")
            print(f"      接口: {DIM}{base_url}{RESET}")
            if has_key:
                raw_key = pcfg.get("key", state.cfg.get("key", ""))
                key_display = raw_key[:8] + "****" if len(raw_key) > 8 else raw_key
                print(f"      Key:  {DIM}{key_display}{RESET}")
        print(f"\n{DIM}用法:{RESET}")
        print(f"  /providers add <道统> <key> [模型] — 添加/更新道统配置")
        print(f"  /providers del <道统>              — 删除道统配置")
        print(f"  /providers use <道统>              — 切换到指定道统")
        return False

    if sub == "add":
        if not arg1 or not arg2:
            print(f"{RED}❌ 用法: /providers add <道统> <key> [模型]{RESET}")
            return False
        provider_id = arg1
        from fr_cli.core.llm import get_provider_info
        info = get_provider_info(provider_id)
        if not info:
            print(f"{RED}❌ 无效道统: {provider_id}{RESET}")
            return False
        pcfg = providers_cfg.setdefault(provider_id, {})
        pcfg["key"] = arg2
        model = parts[4] if len(parts) > 4 else info["default_model"]
        pcfg["model"] = model
        # 支持自定义 base_url: /providers add <provider> <key> [model] --base-url <url>
        for i, token in enumerate(parts):
            if token in ("--base-url", "--base_url") and i + 1 < len(parts):
                pcfg["base_url"] = parts[i + 1]
                break
        state.cfg["providers"] = providers_cfg
        state.save_cfg()
        extra = f" 自定义接口={pcfg.get('base_url')}" if pcfg.get("base_url") else ""
        print(f"{GREEN}✅ [{provider_id}] 配置已更新: 模型={model}{extra}{RESET}")
        return False

    if sub == "del":
        if not arg1:
            print(f"{RED}❌ 用法: /providers del <道统>{RESET}")
            return False
        if arg1 in providers_cfg:
            del providers_cfg[arg1]
            state.cfg["providers"] = providers_cfg
            state.save_cfg()
            print(f"{GREEN}✅ [{arg1}] 配置已删除{RESET}")
        else:
            print(f"{YELLOW}⚠️ [{arg1}] 无配置可删除{RESET}")
        return False

    if sub == "use":
        if not arg1:
            print(f"{RED}❌ 用法: /providers use <道统>{RESET}")
            return False
        ok = state.update_provider(arg1)
        if ok:
            print(f"{GREEN}✅ 已切换到: [{state.provider}] {state.model_name}{RESET}")
            # 检查新道统是否已配置 API Key
            if not _provider_has_key(state, state.provider):
                print(f"{YELLOW}⚠️ [{state.provider}] 尚未配置 API Key{RESET}")
                k = input(f"👉 请输入 [{state.provider}] 的 API Key: ").strip()
                if k:
                    state.update_key(k)
                    print(f"{GREEN}✅ [{state.provider}] API Key 已保存{RESET}")
        else:
            print(f"{RED}❌ 无效道统: {arg1}{RESET}")
        return False

    print(f"{RED}❌ 未知子命令: {sub}{RESET}")
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
    prep_see_msg(state.messages, arg1, parts[2] if len(parts) > 2 else "", vfs=state.vfs)
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
    # MasterAgent 模式下思维模式由其内部 ReAct 循环控制，/mode 无效
    if getattr(state, 'master_agent', None) and state.master_agent.is_enabled():
        print(f"{YELLOW}⚠️ MasterAgent 主控模式下，思维模式由其内部 ReAct 循环自主管理，/mode 命令无效。{RESET}")
        print(f"{DIM}  提示: 使用 /master off 关闭主控后可切换思维模式。{RESET}")
        return False

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


def _cmd_remote_agent_add(state, parts):
    """添加远程 Agent: /remote_agent_add <name> <host> <port> <token> [description]"""
    from fr_cli.agent.remote import add_remote_agent
    if len(parts) < 5:
        print(f"{YELLOW}用法: /remote_agent_add <name> <host> <port> <token> [description]{RESET}")
        return False
    name, host, port, token = parts[1], parts[2], parts[3], parts[4]
    desc = ' '.join(parts[5:]) if len(parts) > 5 else ""
    try:
        port = int(port)
    except ValueError:
        print(f"{RED}端口号必须是数字{RESET}")
        return False
    add_remote_agent(name, host, port, token, desc)
    print(f"{GREEN}✅ 远程 Agent [{name}] 已注册: {host}:{port}{RESET}")
    return False


def _cmd_remote_agent_list(state, parts):
    """列出所有远程 Agent"""
    from fr_cli.agent.remote import list_remote_agents
    agents = list_remote_agents()
    if not agents:
        print(f"{DIM}暂无远程 Agent。使用 /remote_agent_add 添加。{RESET}")
        return False
    print(f"{CYAN}🌐 远程 Agent 列表:{RESET}")
    for name, cfg in agents.items():
        print(f"  [{name}] {cfg['host']}:{cfg['port']} — {cfg.get('description', '')}")
    return False


def _cmd_remote_agent_del(state, parts):
    """删除远程 Agent: /remote_agent_del <name>"""
    from fr_cli.agent.remote import remove_remote_agent
    arg1 = parts[1] if len(parts) > 1 else ""
    if not arg1:
        print(f"{YELLOW}用法: /remote_agent_del <name>{RESET}")
        return False
    if remove_remote_agent(arg1):
        print(f"{GREEN}✅ 远程 Agent [{arg1}] 已删除。{RESET}")
    else:
        print(f"{RED}远程 Agent [{arg1}] 不存在。{RESET}")
    return False


def _cmd_agent_publish(state, parts):
    """发布当前Agent服务，生成对外连接信息"""
    if not state.agent_server or not state.agent_server.is_running():
        print(f"{YELLOW}⚠️ Agent HTTP 服务未运行。请先启动服务：{RESET}")
        print(f"{DIM}  /agent_server start [port]{RESET}")
        return False

    info = state.agent_server.get_publish_info()
    if not info:
        print(f"{RED}无法获取发布信息。{RESET}")
        return False

    print(f"{CYAN}═══ Agent 服务发布信息 ═══{RESET}")
    print(f"  服务地址: {info['url']}")
    print(f"  认证Token: {info['token']}")
    print(f"  主机名: {info['hostname']}")
    print(f"  本地IP: {info['local_ip']}")
    print(f"\n{DIM}分享以下信息给其他fr-cli用户，对方可用 /remote_agent_add 或 /remote_agent_import 添加：{RESET}")
    print(f"  Host: {info['host']}")
    print(f"  Port: {state.agent_server.port}")
    print(f"  Token: {info['token']}")
    print(f"\n{DIM}快速扫描命令（对方执行）：{RESET}")
    print(f"  /remote_agent_scan {info['host']} {state.agent_server.port} {info['token']}")
    print(f"\n{YELLOW}⚠️ 安全提示：{RESET}")
    print(f"  - 当前绑定: {state.agent_server.host}")
    if state.agent_server.host == "127.0.0.1":
        print(f"  - 仅本地可访问。如需公网暴露，请使用 ngrok / cloudflared / frp 等内网穿透工具")
    return False


def _cmd_remote_agent_scan(state, parts):
    """扫描远程主机的Agent服务: /remote_agent_scan <host> <port> <token>"""
    from fr_cli.agent.client import scan_remote_host
    if len(parts) < 4:
        print(f"{YELLOW}用法: /remote_agent_scan <host> <port> <token>{RESET}")
        return False
    host, port, token = parts[1], parts[2], parts[3]
    try:
        port = int(port)
    except ValueError:
        print(f"{RED}端口号必须是数字{RESET}")
        return False

    print(f"{CYAN}🔍 正在扫描 {host}:{port} ...{RESET}")
    info, err = scan_remote_host(host, port, token)
    if err:
        print(f"{RED}{err}{RESET}")
        return False

    print(f"{GREEN}✅ 发现服务: {info['service']} v{info['version']}{RESET}")
    agents = info.get("agents", [])
    if not agents:
        print(f"{DIM}  该主机暂无可用Agent。{RESET}")
    else:
        print(f"{CYAN}  可用Agent ({len(agents)}个):{RESET}")
        for a in agents:
            badges = []
            if a.get("has_persona"): badges.append("人设")
            if a.get("has_memory"): badges.append("记忆")
            if a.get("has_skills"): badges.append("技能")
            badge_str = f" [{', '.join(badges)}]" if badges else ""
            print(f"    - {a['name']}{badge_str}")
    print(f"\n{DIM}使用 /remote_agent_import {host} {port} {token} 一键导入所有Agent{RESET}")
    return False


def _cmd_remote_agent_import(state, parts):
    """一键导入远程主机的所有Agent: /remote_agent_import <host> <port> <token> [prefix]"""
    from fr_cli.agent.client import import_remote_agents
    if len(parts) < 4:
        print(f"{YELLOW}用法: /remote_agent_import <host> <port> <token> [prefix]{RESET}")
        return False
    host, port, token = parts[1], parts[2], parts[3]
    prefix = parts[4] if len(parts) > 4 else ""
    try:
        port = int(port)
    except ValueError:
        print(f"{RED}端口号必须是数字{RESET}")
        return False

    print(f"{CYAN}📥 正在从 {host}:{port} 导入 Agent ...{RESET}")
    imported, errors = import_remote_agents(host, port, token, prefix)
    if imported:
        print(f"{GREEN}✅ 成功导入 {imported} 个Agent。{RESET}")
    if errors:
        print(f"{YELLOW}⚠️ 导入过程中出现 {len(errors)} 个错误:{RESET}")
        for e in errors:
            print(f"  {RED}{e}{RESET}")
    if not imported and not errors:
        print(f"{DIM}远程主机暂无Agent。{RESET}")
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


def _cmd_master(state, parts):
    """切换或查看主控 Agent（MasterAgent）状态"""
    arg1 = parts[1] if len(parts) > 1 else ""
    if arg1.lower() in ("on", "enable", "1"):
        state.master_agent.toggle(True)
        print(f"{GREEN}✅ 主控 Agent 已启用。所有对话将由 MasterAgent 接管处理。{RESET}")
    elif arg1.lower() in ("off", "disable", "0"):
        state.master_agent.toggle(False)
        print(f"{GREEN}✅ 主控 Agent 已禁用。恢复为普通 AI 对话模式。{RESET}")
    elif arg1.lower() == "status":
        st = state.master_agent.status()
        print(f"{CYAN}🧠 主控 Agent 状态:{RESET}")
        print(f"  {'启用' if st['enabled'] else '禁用'}")
        print(f"  总交互: {st['total_interactions']} | 成功: {st['success']} | 失败: {st['failure']}")
        if st['evolution_addon']:
            print(f"  进化追加: {st['evolution_addon']}")
    else:
        enabled = state.master_agent.toggle()
        status = "已启用" if enabled else "已禁用"
        print(f"{GREEN}✅ 主控 Agent {status}。{RESET}")
        print(f"{DIM}  用法: /master on | /master off | /master status{RESET}")
    return False




def _cmd_mcp_list(state, parts):
    """列出 MCP 服务器和可用工具"""
    servers = state.mcp.list_servers()
    if not servers:
        print(f"{YELLOW}暂无 MCP 服务器配置。{RESET}")
        print(f"{DIM}用法: /mcp_add <名称> <命令> [参数...]{RESET}")
        return False

    print(f"{CYAN}📡 MCP 服务器配置 ({len(servers)} 个):{RESET}")
    for s in servers:
        status = f"{GREEN}● 启用{RESET}" if s.get("enabled", True) else f"{RED}● 禁用{RESET}"
        print(f"\n  {CYAN}[{s['name']}]{RESET} {status}")
        print(f"    传输: {s.get('transport', 'stdio')}")
        print(f"    命令: {s.get('command', 'N/A')} {' '.join(s.get('args', []))}")
        if s.get('cwd'):
            print(f"    工作目录: {s['cwd']}")

    # 尝试获取工具列表
    print(f"\n{CYAN}🔧 可用法宝:{RESET}")
    tools = state.mcp.list_all_tools()
    if not tools:
        print(f"  {DIM}暂无可用法宝（服务器可能未连接或已禁用）{RESET}")
    else:
        for t in tools:
            print(f"  - {GREEN}{t['name']}{RESET}: {t['description']}")
            print(f"    所属服务器: {t['server']}")
    return False


def _cmd_mcp_add(state, parts):
    """添加 MCP 服务器: /mcp_add <名称> <命令> [参数...]"""
    if len(parts) < 3:
        print(f"{YELLOW}用法: /mcp_add <名称> <命令> [参数...]{RESET}")
        print(f"{DIM}示例: /mcp_add filesystem npx -y @modelcontextprotocol/server-filesystem /tmp{RESET}")
        return False
    name = parts[1]
    command = parts[2]
    args = parts[3:] if len(parts) > 3 else []
    ok, err = state.mcp.add_server(name, command, args)
    if ok:
        print(f"{GREEN}✅ MCP 服务器 [{name}] 已添加。{RESET}")
        print(f"{DIM}  命令: {command} {' '.join(args)}{RESET}")
        print(f"{DIM}  使用 /mcp_refresh 或重新启动以加载其法宝。{RESET}")
    else:
        print(f"{RED}❌ 添加失败: {err}{RESET}")
    return False


def _cmd_mcp_del(state, parts):
    """删除 MCP 服务器: /mcp_del <名称>"""
    if len(parts) < 2:
        print(f"{YELLOW}用法: /mcp_del <名称>{RESET}")
        return False
    name = parts[1]
    ok, err = state.mcp.remove_server(name)
    if ok:
        print(f"{GREEN}✅ MCP 服务器 [{name}] 已删除。{RESET}")
    else:
        print(f"{RED}❌ 删除失败: {err}{RESET}")
    return False


def _cmd_mcp_enable(state, parts):
    """启用 MCP 服务器: /mcp_enable <名称>"""
    if len(parts) < 2:
        print(f"{YELLOW}用法: /mcp_enable <名称>{RESET}")
        return False
    name = parts[1]
    ok, err = state.mcp.toggle_server(name, True)
    if ok:
        print(f"{GREEN}✅ MCP 服务器 [{name}] 已启用。{RESET}")
    else:
        print(f"{RED}❌ 操作失败: {err}{RESET}")
    return False


def _cmd_mcp_disable(state, parts):
    """禁用 MCP 服务器: /mcp_disable <名称>"""
    if len(parts) < 2:
        print(f"{YELLOW}用法: /mcp_disable <名称>{RESET}")
        return False
    name = parts[1]
    ok, err = state.mcp.toggle_server(name, False)
    if ok:
        print(f"{GREEN}✅ MCP 服务器 [{name}] 已禁用。{RESET}")
    else:
        print(f"{RED}❌ 操作失败: {err}{RESET}")
    return False


def _cmd_mcp_refresh(state, parts):
    """刷新 MCP 服务器法宝列表"""
    print(f"{CYAN}🔄 正在刷新 MCP 法宝列表...{RESET}")
    tools = state.mcp.list_all_tools()
    if tools:
        print(f"{GREEN}✅ 发现 {len(tools)} 个法宝:{RESET}")
        for t in tools:
            print(f"  - {t['name']} ({t['server']}): {t['description']}")
    else:
        print(f"{YELLOW}⚠️ 未发现可用法宝。请检查服务器配置和连接状态。{RESET}")
    return False
