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
    print(f"\n{CYAN}🔧 可用工具:{RESET}")
    tools = state.mcp.list_all_tools()
    if not tools:
        print(f"  {DIM}暂无可用工具（服务器可能未连接或已禁用）{RESET}")
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
    # 注意：add_server 第二个位置参数是 transport（必需），不是 command
    # 走 quick_add 走 stdio 快捷路径，避免参数错位
    try:
        state.mcp.quick_add(name, command, args)
        print(f"{GREEN}✅ MCP 服务器 [{name}] 已添加。{RESET}")
        print(f"{DIM}  命令: {command} {' '.join(args)}{RESET}")
        print(f"{DIM}  使用 /mcp_refresh 或重新启动以加载其工具。{RESET}")
    except Exception as e:
        print(f"{RED}❌ 添加失败: {e}{RESET}")
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
    """刷新 MCP 服务器工具列表"""
    print(f"{CYAN}🔄 正在刷新 MCP 工具列表...{RESET}")
    tools = state.mcp.list_all_tools()
    if tools:
        print(f"{GREEN}✅ 发现 {len(tools)} 个工具:{RESET}")
        for t in tools:
            print(f"  - {t['name']} ({t['server']}): {t['description']}")
    else:
        print(f"{YELLOW}⚠️ 未发现可用工具。请检查服务器配置和连接状态。{RESET}")
    return False



