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
from fr_cli.agent.shell_mode import ShellMode
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


