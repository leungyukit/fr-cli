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





def _cmd_commit(state, parts):
    """/commit 快捷场景"""
    from fr_cli.repl.scenarios import scenario_commit
    prompt = getattr(state, "_prompt", None)
    return scenario_commit(state, parts[1:], prompt)



def _cmd_pr(state, parts):
    """/pr 快捷场景"""
    from fr_cli.repl.scenarios import scenario_pr
    prompt = getattr(state, "_prompt", None)
    return scenario_pr(state, parts[1:], prompt)



def _cmd_review(state, parts):
    """/review 快捷场景"""
    from fr_cli.repl.scenarios import scenario_review
    prompt = getattr(state, "_prompt", None)
    return scenario_review(state, parts[1:], prompt)



