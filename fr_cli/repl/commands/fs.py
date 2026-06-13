"""
REPL 命令路由处理器
从 main.py 提取的所有 / 命令实现，减轻主模块负担。
"""

from fr_cli.ui.ui import (
    CYAN, RESET
)



def _cmd_dir(state, parts):
    arg1 = parts[1] if len(parts) > 1 else ""
    if arg1:
        result = state.vfs.add(arg1, state.lang)
        if result.is_ok():
            state.cfg["allowed_dirs"] = state.vfs.ds
            state.save_cfg()
        print(result.unwrap_or(result.error))
    return False



def _cmd_dirs(state, parts):
    result = state.vfs.list_dirs(state.lang)
    if result.is_fail():
        print(result.error)
    else:
        print(f"{CYAN}📂 已挂载的目录:{RESET}")
        for item in result.unwrap():
            print(item)
    return False



def _cmd_rmdir(state, parts):
    arg1 = parts[1] if len(parts) > 1 else ""
    if arg1:
        result = state.vfs.remove_dir(arg1, state.lang)
        if result.is_ok():
            state.cfg["allowed_dirs"] = state.vfs.ds
            state.save_cfg()
        print(result.unwrap_or(result.error))
    return False


