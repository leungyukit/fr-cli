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


