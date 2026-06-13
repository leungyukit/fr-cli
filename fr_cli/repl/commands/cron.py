"""
REPL 命令路由处理器
从 main.py 提取的所有 / 命令实现，减轻主模块负担。
"""

from fr_cli.ui.ui import (
    CYAN, RED, YELLOW, GREEN, DIM, RESET
)
from fr_cli.agent.manager import (
    agent_exists,
)



def _cmd_agent_cron_add(state, parts):
    """为 Agent 分身添加定时任务"""
    from fr_cli.gatekeeper.manager import read_daemon_config, sync_gatekeeper_cron_jobs
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


