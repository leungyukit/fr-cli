"""
一键自动启动所有后台服务：/autostart
"""
from fr_cli.ui.ui import CYAN, RED, YELLOW, GREEN, DIM, RESET


def _cmd_autostart(state, parts):
    """一键自动启动所有后台服务

    用法:
      /autostart                              使用默认端口启动所有服务
      /autostart --agent-server 17890         指定 Agent HTTP 端口
      /autostart --hermes 8765                指定 Hermes 端口
    """
    ports = {}
    i = 1
    while i < len(parts):
        arg = parts[i]
        if arg in ("--agent-server", "-a") and i + 1 < len(parts):
            try:
                ports["agent_server"] = int(parts[i + 1])
            except ValueError:
                print(f"{YELLOW}⚠️  --agent-server 需要端口号{RESET}")
                return False
            i += 2
        elif arg in ("--hermes", "-h") and i + 1 < len(parts):
            try:
                ports["hermes"] = int(parts[i + 1])
            except ValueError:
                print(f"{YELLOW}⚠️  --hermes 需要端口号{RESET}")
                return False
            i += 2
        else:
            i += 1

    print(f"{CYAN}🚀 正在一键启动所有后台服务...{RESET}")
    results = state.start_all_services(ports=ports)

    for name, result in results.items():
        label = {
            "master_agent": "🧠 MasterAgent",
            "agent_server": "🌐 Agent HTTP 服务",
            "hermes_daemon": "🧚 Hermes 守护进程",
            "gatekeeper": "🛡️ Gatekeeper",
            "cron": "⏰ Cron 定时任务",
        }.get(name, name)
        if result.is_ok():
            print(f"{GREEN}✅ {label}: {result.unwrap_or('运行中')}{RESET}")
        else:
            print(f"{YELLOW}⚠️ {label}: {result.error}{RESET}")

    return False