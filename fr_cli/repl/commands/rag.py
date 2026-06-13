"""
REPL 命令路由处理器
从 main.py 提取的所有 / 命令实现，减轻主模块负担。
"""

from fr_cli.ui.ui import (
    CYAN, RED, YELLOW, GREEN, DIM, RESET
)



def _cmd_rag_dir(state, parts):
    arg1 = parts[1] if len(parts) > 1 else ""
    if not arg1:
        return False
    from pathlib import Path as _Path
    p = _Path(arg1)
    if not p.exists():
        print(f"{RED}目录不存在: {arg1}{RESET}")
    else:
        state.cfg["rag_dir"] = str(p.resolve())
        state.save_cfg()
        print(f"{GREEN}✅ 知识库目录已设置: {p.resolve()}{RESET}")
        from fr_cli.agent.builtins.rag import get_rag_manager, RAGWatcherManager
        mgr = get_rag_manager(str(p.resolve()))
        ok, msg = mgr.sync_directory()
        print(f"{GREEN if ok else YELLOW}{msg}{RESET}")
        # 如果独立守护进程未运行，才启动内置 watcher
        watcher = RAGWatcherManager()
        if ok and not watcher.is_running():
            mgr.start_watcher()
            print(f"{DIM}内置后台监控已启动（如需持久化守护，请使用 /rag_watch start）{RESET}")
    return False



def _cmd_rag_watch(state, parts):
    """管理 RAG 知识库独立守护进程"""
    from fr_cli.agent.builtins.rag import RAGWatcherManager
    arg1 = parts[1] if len(parts) > 1 else ""
    watcher = RAGWatcherManager()

    if arg1 == "start":
        kb_dir = parts[2] if len(parts) > 2 else state.cfg.get("rag_dir", "")
        if not kb_dir:
            print(f"{YELLOW}未设置知识库目录，请先使用 /rag_dir <目录> 设置。{RESET}")
            return False
        # 解析可选参数 --interval
        interval = 30
        for i, part in enumerate(parts):
            if part == "--interval" and i + 1 < len(parts):
                try:
                    interval = int(parts[i + 1])
                except ValueError:
                    pass
        ok, msg = watcher.start(kb_dir, interval=interval)
        color = GREEN if ok else YELLOW
        print(f"{color}{msg}{RESET}")
        if ok:
            print(f"{DIM}日志文件: ~/.fr_cli/rag/watcher.log{RESET}")
            print(f"{DIM}停止命令: /rag_watch stop{RESET}")

    elif arg1 == "stop":
        ok, msg = watcher.stop()
        color = GREEN if ok else YELLOW
        print(f"{color}{msg}{RESET}")

    elif arg1 == "status":
        print(f"{CYAN}{watcher.status()}{RESET}")

    elif arg1 == "log":
        lines = 50
        for i, part in enumerate(parts):
            if part == "--lines" and i + 1 < len(parts):
                try:
                    lines = int(parts[i + 1])
                except ValueError:
                    pass
        log = watcher.get_log(lines=lines)
        print(f"{DIM}--- RAG 守护进程日志（最后 {lines} 行）---{RESET}")
        print(log)
        print(f"{DIM}--- EOF ---{RESET}")

    else:
        print(f"{DIM}用法: /rag_watch start [目录] [--interval N] | /rag_watch stop | /rag_watch status | /rag_watch log [--lines N]{RESET}")
    return False



def _cmd_rag_sync(state, parts):
    """手动同步知识库"""
    from fr_cli.agent.builtins.rag import get_rag_manager, RAGWatcherManager
    kb_dir = state.cfg.get("rag_dir", "")
    if not kb_dir:
        print(f"{YELLOW}未设置知识库目录。{RESET}")
        arg1 = parts[1] if len(parts) > 1 else ""
        if arg1:
            from pathlib import Path as _Path
            p = _Path(arg1)
            if p.exists():
                state.cfg["rag_dir"] = str(p.resolve())
                state.save_cfg()
                kb_dir = str(p.resolve())
            else:
                print(f"{RED}目录不存在: {arg1}{RESET}")
                return False
        else:
            return False

    mgr = get_rag_manager(kb_dir)
    print(f"{CYAN}📚 正在同步知识库...{RESET}")
    ok, msg = mgr.sync_directory()
    color = GREEN if ok else YELLOW
    print(f"{color}{msg}{RESET}")

    watcher = RAGWatcherManager()
    if watcher.is_running():
        print(f"{DIM}ℹ️ 独立守护进程正在运行，知识库将自动保持同步。{RESET}")
    return False


