"""
Agent HTTP 服务与 Gatekeeper 守护进程命令
"""
from fr_cli.ui.ui import CYAN, RED, YELLOW, GREEN, DIM, RESET


def _cmd_agent_server(state, parts):
    from fr_cli.agent.server import AgentHTTPServer
    arg1 = parts[1] if len(parts) > 1 else ""
    if arg1 == "start":
        port = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 17890
        if state.agent_server is None:
            state.agent_server = AgentHTTPServer(state, port=port)
        result = state.agent_server.start()
        color = GREEN if result.is_ok() else YELLOW
        print(f"{color}{result.unwrap_or(result.error)}{RESET}")
    elif arg1 == "stop":
        if state.agent_server is None:
            print(f"{YELLOW}服务未运行{RESET}")
        else:
            result = state.agent_server.stop()
            color = GREEN if result.is_ok() else YELLOW
            print(f"{color}{result.unwrap_or(result.error)}{RESET}")
    elif arg1 == "status":
        if state.agent_server is None:
            print(f"{DIM}未运行{RESET}")
        else:
            print(f"{CYAN}{state.agent_server.status()}{RESET}")
    else:
        print(f"{DIM}用法: /agent_server start [port] | /agent_server stop | /agent_server status{RESET}")
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
        cfg_result = state.gatekeeper.save_daemon_config(daemon_cfg)
        if cfg_result.is_fail():
            print(f"{YELLOW}{cfg_result.error}{RESET}")
        start_result = state.gatekeeper.start()
        color = GREEN if start_result.is_ok() else YELLOW
        print(f"{color}{start_result.unwrap_or(start_result.error)}{RESET}")
    elif arg1 == "stop":
        stop_result = state.gatekeeper.stop()
        color = GREEN if stop_result.is_ok() else YELLOW
        print(f"{color}{stop_result.unwrap_or(stop_result.error)}{RESET}")
    elif arg1 == "status":
        print(f"{CYAN}{state.gatekeeper.status()}{RESET}")
    else:
        print(f"{DIM}用法: /gatekeeper start | /gatekeeper stop | /gatekeeper status{RESET}")
    return False