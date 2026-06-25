"""
本机应用启动命令：/open, /launch, /apps
"""
from fr_cli.ui.ui import CYAN, RED, GREEN, RESET


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
