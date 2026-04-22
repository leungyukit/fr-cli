"""
REPL 命令路由处理器
从 main.py 提取的所有 / 命令实现，减轻主模块负担。
"""
import sys
import os
import subprocess
import platform
import shutil
from pathlib import Path

from fr_cli.lang.i18n import T
from fr_cli.ui.ui import (
    CYAN, RED, YELLOW, GREEN, DIM, RESET,
    print_bye
)
from fr_cli.memory.history import save_sess, load_sess, del_sess, get_sessions
from fr_cli.memory.context import load_context
from fr_cli.memory.session import (
    list_sessions as list_auto_sessions,
    load_session as load_auto_session,
    delete_session as delete_auto_session,
)
from fr_cli.addon.plugin import extract_code, PLUGIN_DIR
from fr_cli.core.stream import stream_cnt
from fr_cli.core.recommender import recommend_features
from fr_cli.agent.manager import (
    create_agent_dir, save_agent_code, save_persona, save_skills,
    save_memory, agent_exists, list_agents, delete_agent,
    load_persona, load_memory, load_skills, load_agent_module,
)
from fr_cli.agent.executor import run_agent
from fr_cli.agent.builtins.local import handle_local
from fr_cli.agent.builtins.remote import handle_remote
from fr_cli.agent.builtins.spider import handle_spider
from fr_cli.agent.builtins.db import handle_db
from fr_cli.agent.builtins.rag import handle_rag


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


