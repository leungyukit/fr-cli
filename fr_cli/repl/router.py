"""
命令路由
- 内置命令路由表（/exit, /help, /model, ...）
- Namespace 命令转换（/agent create → /agent_create）
- 智能命令提示与首字母补全
- 相似命令建议

将 main.py 中巨大的 if-elif 链提取为字典映射，
让 main.py 只剩主循环本身。
"""
from difflib import get_close_matches
from fr_cli.ui.ui import CYAN, RED, RESET, DIM, YELLOW


# 内置命令路由表（从 main.py 中抽离）
from fr_cli.repl.commands import (
    _cmd_exit,
    _cmd_shell,
    _cmd_hermes_daemon,
    _cmd_help,
    _cmd_model,
    _cmd_key,
    _cmd_limit,
    _cmd_lang,
    _cmd_usage,
    _cmd_dir,
    _cmd_dirs,
    _cmd_rmdir,
    _cmd_save,
    _cmd_load,
    _cmd_del,
    _cmd_session_list,
    _cmd_session_load,
    _cmd_session_del,
    _cmd_new,
    _cmd_see,
    _cmd_update,
    _cmd_agent_server,
    _cmd_mode,
    _cmd_gatekeeper,
    _cmd_open,
    _cmd_launch,
    _cmd_apps,
    _cmd_agent_create,
    _cmd_agent_list,
    _cmd_agent_delete,
    _cmd_agent_show,
    _cmd_agent_run,
    _cmd_agent_edit,
    _cmd_agent_forge,
    _cmd_agent_model,
    _cmd_remote_agent_add,
    _cmd_remote_agent_list,
    _cmd_remote_agent_del,
    _cmd_agent_publish,
    _cmd_remote_agent_scan,
    _cmd_remote_agent_import,
    _cmd_remote_setup,
    _cmd_db_setup,
    _cmd_agent_cron_add,
    _cmd_agent_cron_list,
    _cmd_agent_cron_del,
    _cmd_rag_dir,
    _cmd_rag_watch,
    _cmd_rag_sync,
    _cmd_read_excel,
    _cmd_read_csv,
    _cmd_master,
    _cmd_providers,
    _cmd_commit,
    _cmd_pr,
    _cmd_review,
    _cmd_mcp_list,
    _cmd_mcp_add,
    _cmd_mcp_del,
    _cmd_mcp_enable,
    _cmd_mcp_disable,
    _cmd_mcp_refresh,
    _cmd_tutorial,
    _cmd_ocr_config,
    _cmd_stock_config,
    _cmd_build,
)
from fr_cli.repl.queue import handle_queue_command


COMMAND_ROUTES = {
    "/exit": _cmd_exit,
    "/shell": _cmd_shell,
    "/hermes": _cmd_hermes_daemon,
    "/quit": _cmd_exit,
    "/help": _cmd_help,
    "/model": _cmd_model,
    "/key": _cmd_key,
    "/limit": _cmd_limit,
    "/lang": _cmd_lang,
    "/usage": _cmd_usage,
    "/mode": _cmd_mode,
    "/dir": _cmd_dir,
    "/dirs": _cmd_dirs,
    "/rmdir": _cmd_rmdir,
    "/save": _cmd_save,
    "/load": _cmd_load,
    "/del": _cmd_del,
    "/session_list": _cmd_session_list,
    "/session_load": _cmd_session_load,
    "/session_del": _cmd_session_del,
    "/new": _cmd_new,
    "/see": _cmd_see,
    "/update": _cmd_update,
    "/agent_server": _cmd_agent_server,
    "/gatekeeper": _cmd_gatekeeper,
    "/open": _cmd_open,
    "/launch": _cmd_launch,
    "/apps": _cmd_apps,
    "/agent_create": _cmd_agent_create,
    "/agent_list": _cmd_agent_list,
    "/agent_delete": _cmd_agent_delete,
    "/agent_show": _cmd_agent_show,
    "/agent_run": _cmd_agent_run,
    "/agent_edit": _cmd_agent_edit,
    "/agent_forge": _cmd_agent_forge,
    "/agent_model": _cmd_agent_model,
    "/remote_agent_add": _cmd_remote_agent_add,
    "/remote_agent_list": _cmd_remote_agent_list,
    "/remote_agent_del": _cmd_remote_agent_del,
    "/agent_publish": _cmd_agent_publish,
    "/remote_agent_scan": _cmd_remote_agent_scan,
    "/remote_agent_import": _cmd_remote_agent_import,
    "/remote_setup": _cmd_remote_setup,
    "/db_setup": _cmd_db_setup,
    "/agent_cron_add": _cmd_agent_cron_add,
    "/agent_cron_list": _cmd_agent_cron_list,
    "/agent_cron_del": _cmd_agent_cron_del,
    "/rag_dir": _cmd_rag_dir,
    "/rag_watch": _cmd_rag_watch,
    "/rag_sync": _cmd_rag_sync,
    "/read_excel": _cmd_read_excel,
    "/read_csv": _cmd_read_csv,
    "/master": _cmd_master,
    "/providers": _cmd_providers,
    "/mcp_list": _cmd_mcp_list,
    "/mcp_add": _cmd_mcp_add,
    "/mcp_del": _cmd_mcp_del,
    "/mcp_enable": _cmd_mcp_enable,
    "/mcp_disable": _cmd_mcp_disable,
    "/mcp_refresh": _cmd_mcp_refresh,
    "/commit": _cmd_commit,
    "/pr": _cmd_pr,
    "/review": _cmd_review,
    "/tutorial": _cmd_tutorial,
    "/ocr_config": _cmd_ocr_config,
    "/stock_config": _cmd_stock_config,
    "/build": _cmd_build,
    "/queue": handle_queue_command,
}


# Namespace 命令转换（/agent create → /agent_create）
NAMESPACED_COMMANDS = {
    ("agent", "create"): "/agent_create",
    ("agent", "list"): "/agent_list",
    ("agent", "delete"): "/agent_delete",
    ("agent", "show"): "/agent_show",
    ("agent", "edit"): "/agent_edit",
    ("agent", "forge"): "/agent_forge",
    ("agent", "run"): "/agent_run",
    ("agent", "model"): "/agent_model",
    ("agent", "server"): "/agent_server",
    ("agent", "publish"): "/agent_publish",
    ("agent", "cron"): {
        "add": "/agent_cron_add",
        "list": "/agent_cron_list",
        "delete": "/agent_cron_del",
    },
    ("session", "list"): "/session_list",
    ("session", "load"): "/session_load",
    ("session", "delete"): "/session_del",
    ("remote", "agent"): {
        "add": "/remote_agent_add",
        "list": "/remote_agent_list",
        "delete": "/remote_agent_del",
        "scan": "/remote_agent_scan",
        "import": "/remote_agent_import",
    },
    ("remote", "setup"): "/remote_setup",
    ("rag", "dir"): "/rag_dir",
    ("rag", "sync"): "/rag_sync",
    ("rag", "watch"): "/rag_watch",
    ("mcp", "list"): "/mcp_list",
    ("mcp", "add"): "/mcp_add",
    ("mcp", "delete"): "/mcp_del",
    ("mcp", "enable"): "/mcp_enable",
    ("mcp", "disable"): "/mcp_disable",
    ("mcp", "refresh"): "/mcp_refresh",
    ("mail", "setup"): "/mail_setup",
    ("mail", "inbox"): "/mail_inbox",
    ("mail", "read"): "/mail_read",
    ("mail", "send"): "/mail_send",
    ("disk", "setup"): "/disk_setup",
    ("disk", "ls"): "/disk_ls",
    ("disk", "cd"): "/disk_cd",
    ("disk", "up"): "/disk_up",
    ("disk", "down"): "/disk_down",
    ("cron", "add"): "/cron_add",
    ("cron", "list"): "/cron_list",
    ("cron", "delete"): "/cron_del",
    ("db", "setup"): "/db_setup",
    ("data", "excel"): "/read_excel",
    ("data", "csv"): "/read_csv",
    ("ocr", "config"): "/ocr_config",
    ("stock", "config"): "/stock_config",
    ("config", "server"): "/config_server",
    ("banner", "on"): "/banner_on",
    ("banner", "off"): "/banner_off",
    ("tutorial", ""): "/tutorial",
}


def normalize_namespaced_cmd(u: str) -> str:
    """将 /namespace action 格式转换为内部命令格式"""
    parts = u.split()
    if len(parts) < 2:
        return u
    ns = parts[0][1:]  # 去掉 /
    action = parts[1]
    if len(parts) >= 3:
        sub = parts[2]
        mapping = NAMESPACED_COMMANDS.get((ns, action))
        if isinstance(mapping, dict) and sub in mapping:
            return mapping[sub] + " " + " ".join(parts[3:])
    mapping = NAMESPACED_COMMANDS.get((ns, action))
    if isinstance(mapping, str):
        return mapping + " " + " ".join(parts[2:])
    return u


def _cmd_category(cmd: str) -> str:
    """给命令简单分类（用于 / 列表展示）—— 复用 FanRenCompleter 的 CATEGORY_HINTS

    单一真相源：所有命令分类都从 prompt.py 的 CATEGORY_HINTS 来，
    避免两套分类法不一致。
    """
    from fr_cli.ui.prompt import FanRenCompleter
    cmd_no_slash = cmd.lstrip("/")
    # 优先匹配完整命令名（去前缀斜杠）
    if cmd_no_slash in FanRenCompleter.CATEGORY_HINTS:
        return FanRenCompleter.CATEGORY_HINTS[cmd_no_slash]
    # 前缀匹配
    for prefix, cat in FanRenCompleter.CATEGORY_HINTS.items():
        if cmd.startswith("/" + prefix) or cmd_no_slash.startswith(prefix):
            return cat
    return "📦其他"


def _print_similar_cmds(cmd, all_cmds):
    """打印相似命令建议（编辑距离 ≤ 2）"""
    similars = get_close_matches(cmd, all_cmds, n=3, cutoff=0.3)
    if similars:
        print(f"{DIM}你是不是想:{RESET}")
        for c in similars:
            print(f"  {CYAN}{c}{RESET}")


def handle_smart_cmd(state, cmd, u, parts):
    """智能命令提示与首字母补全

    - 输入 `/` → 显示所有命令分类列表
    - 输入 `/a` → 查找以 'a' 开头的命令，唯一则自动执行，多个则提示选择
    - 输入其他不存在的命令 → 显示错误和相似命令建议

    Returns:
        bool: True 表示应退出主循环（如 /exit 被触发）
    """
    all_cmds = sorted(COMMAND_ROUTES.keys())

    # 1. 只有 `/` → 打印命令列表
    if cmd == "/":
        print(f"{CYAN}命令列表（按 Tab 补全 或 直接输入）{RESET}")
        categories = {}
        for c in all_cmds:
            cat = _cmd_category(c)
            categories.setdefault(cat, []).append(c)
        for cat in sorted(categories.keys()):
            print(f"\n  [{cat}]")
            for c in categories[cat]:
                from fr_cli.command.registry import get_registry
                from fr_cli.ui.prompt import FanRenCompleter
                reg = get_registry()
                tool = reg._tools.get(c.lstrip("/"))
                desc = tool.get("description", "") if tool else ""
                example = FanRenCompleter.COMMAND_EXAMPLES.get(c.lstrip("/"), "")
                print(f"    {c} | {desc} | {example}")
        print(f"\n{DIM}提示: /a 首字母匹配  |  /model 直接切换  |  方向键/Tab 浏览  |  回车执行{RESET}")
        return False

    # 2. 单字母匹配（如 /a）→ 首字母补全
    if len(cmd) == 2 and cmd[1].isalpha():
        letter = cmd[1].lower()
        matches = [c for c in all_cmds if len(c) > 1 and c[1].lower() == letter]
        if len(matches) == 0:
            print(f"{RED}未知命令: {cmd}{RESET}")
            print(f"{DIM}没有以 '{letter}' 开头的命令。{RESET}")
            _print_similar_cmds(cmd, all_cmds)
            return False
        if len(matches) == 1:
            auto_cmd = matches[0]
            print(f"{DIM}自动补全: {cmd} → {auto_cmd}{RESET}")
            from fr_cli.core.recommender import record_command_usage
            record_command_usage(auto_cmd)
            return COMMAND_ROUTES[auto_cmd](state, [auto_cmd] + parts[1:])
        print(f"{YELLOW}多个命令以 '{letter}' 开头，请选择:{RESET}")
        for i, c in enumerate(matches, 1):
            print(f"  [{i}] {CYAN}{c}{RESET}")
        try:
            choice = input(f"{YELLOW}编号 (回车取消): {RESET}").strip()
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(matches):
                    selected = matches[idx]
                    from fr_cli.core.recommender import record_command_usage
                    record_command_usage(selected)
                    return COMMAND_ROUTES[selected](state, [selected] + parts[1:])
        except (EOFError, KeyboardInterrupt):
            print(f"{DIM}已取消。{RESET}")
        return False

    # 3. 其他未知命令 → 先尝试执行引擎
    exec_result = state.executor.execute(u, state.messages)
    if exec_result.is_fail():
        print(f"{RED}未知命令: {cmd}{RESET}")
        _print_similar_cmds(cmd, all_cmds)
    elif exec_result.unwrap() is not None:
        result = exec_result.unwrap()
        arg1 = parts[1] if len(parts) > 1 else ""
        if cmd == "/cat" and arg1:
            print(f"\n{DIM}--- {arg1} ---{RESET}\n{result}\n{DIM}--- EOF ---{RESET}")
        elif cmd == "/fetch" and arg1:
            print(f"{DIM}--- Fetch ---{RESET}\n{result}\n{DIM}--- EOF ---{RESET}")
        elif cmd == "/skills":
            print("\n".join([f"{CYAN}{line}{RESET}" for line in result.split("\n")]))
        else:
            print(result)
    return False


def dispatch(state, u: str) -> bool:
    """统一命令分发入口：返回 True 表示应退出主循环"""
    from datetime import datetime
    u = normalize_namespaced_cmd(u)
    parts = u.split()
    cmd = parts[0].lower()

    cmd_start = datetime.now()
    if cmd in COMMAND_ROUTES:
        try:
            should_break = COMMAND_ROUTES[cmd](state, parts)
            if should_break:
                return True
        except (EOFError, KeyboardInterrupt):
            print(f"{DIM}已取消。{RESET}")
        except Exception as e:
            import traceback
            print(f"{RED}命令执行出错: {e}{RESET}")
            traceback.print_exc()
        # 记录耗时
        elapsed = (datetime.now() - cmd_start).total_seconds()
        if elapsed > 1.0:
            from fr_cli.core.recommender import record_command_usage
            record_command_usage(cmd)
        return False

    # 未注册命令 → 走智能路由
    return handle_smart_cmd(state, cmd, u, parts)
