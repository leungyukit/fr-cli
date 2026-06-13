"""
REPL 命令路由处理器
从 main.py 提取的所有 / 命令实现，减轻主模块负担。
"""

from fr_cli.ui.ui import (
    CYAN, RED, YELLOW, GREEN, DIM, RESET
)



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



def _cmd_open(state, parts):
    from fr_cli.weapon.launcher import open_file
    arg1 = parts[1] if len(parts) > 1 else ""
    if arg1:
        msg, err = open_file(arg1, state.lang)
        if err:
            print(f"{RED}{err}{RESET}")
        else:
            print(f"{GREEN}{msg}{RESET}")
    return False



def _cmd_launch(state, parts):
    from fr_cli.weapon.launcher import launch_app
    arg1 = parts[1] if len(parts) > 1 else ""
    if arg1:
        target = parts[2] if len(parts) > 2 else None
        msg, err = launch_app(arg1, target, state.lang)
        if err:
            print(f"{RED}{err}{RESET}")
        else:
            print(f"{GREEN}{msg}{RESET}")
    return False



def _cmd_apps(state, parts):
    from fr_cli.weapon.launcher import list_apps
    res, err = list_apps(state.lang)
    if err:
        print(f"{RED}{err}{RESET}")
    else:
        print(f"{CYAN}{res}{RESET}")
    return False



def _cmd_hermes_daemon(state, parts):
    """Hermes 守护进程命令"""
    arg1 = parts[1] if len(parts) > 1 else ""

    if arg1 == "start":
        port = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 8765
        try:
            from fr_cli.agent.hermes_daemon import HermesDaemon
            import threading
            daemon = HermesDaemon(port=port)
            state.hermes_daemon = daemon
            t = threading.Thread(target=daemon.start, daemon=True)
            t.start()
            print(f"{GREEN}🧚 Hermes 守护进程已启动: http://127.0.0.1:{port}{RESET}")
        except Exception as e:
            print(f"{RED}启动失败: {e}{RESET}")

    elif arg1 == "stop":
        if hasattr(state, "hermes_daemon") and state.hermes_daemon:
            state.hermes_daemon.running = False
            print(f"{GREEN}🛑 守护进程已停止{RESET}")
        else:
            print(f"{YELLOW}守护进程未运行{RESET}")

    elif arg1 == "status":
        if hasattr(state, "hermes_daemon") and state.hermes_daemon:
            print(f"{CYAN}🧚 守护进程运行中{RESET}")
            print(f"   端口: {state.hermes_daemon.port}")
        else:
            print(f"{DIM}守护进程未运行{RESET}")

    else:
        print(f"{DIM}用法: /hermes start [port] | /hermes stop | /hermes status{RESET}")
        print(f"{DIM}示例: /hermes start 8765{RESET}")
    return False



def _cmd_remote_setup(state, parts):
    from fr_cli.agent.builtins.remote import _setup_wizard
    _setup_wizard(state.lang)
    return False



def _cmd_db_setup(state, parts):
    from fr_cli.agent.builtins.db import _setup_wizard as db_setup
    db_setup(state.lang)
    return False


