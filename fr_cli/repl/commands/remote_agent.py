"""
REPL 命令路由处理器
从 main.py 提取的所有 / 命令实现，减轻主模块负担。
"""

from fr_cli.ui.ui import (
    CYAN, RED, YELLOW, GREEN, DIM, RESET
)



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
        print("  - 仅本地可访问。如需公网暴露，请使用 ngrok / cloudflared / frp 等内网穿透工具")
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
    result = scan_remote_host(host, port, token)
    if result.is_fail():
        print(f"{RED}{result.error}{RESET}")
        return False

    info = result.unwrap()
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


