"""
REPL 命令路由处理器
从 main.py 提取的所有 / 命令实现，减轻主模块负担。
"""

from fr_cli.ui.ui import (
    CYAN, RED, DIM, RESET
)



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


