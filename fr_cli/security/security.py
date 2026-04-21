"""
四阶安全确认引擎
"""
import os
from fr_cli.ui.ui import RED, BOLD, YELLOW, CYAN, RESET
from fr_cli.lang.i18n import T
from fr_cli.conf.config import save_config

def ask(k, d, l, fconfirm, sconfirm, config):
    """
    安全询问逻辑
    :param k: 操作类型键名 (如 sec_read, sec_exec)
    :param d: 具体操作描述 (如文件名或命令)
    :param l: 当前语言
    :param fconfirm: 永久放行状态
    :param sconfirm: 本次轮回放行状态
    :param config: 配置字典对象 (用于持久化永久放行状态)
    :return: tuple (是否放行:bool, 更新后的sconfirm:bool, 更新后的fconfirm:bool)
    """
    # 如果已经处于放行状态，直接放行
    if fconfirm or sconfirm:
        return True, sconfirm, fconfirm

    # 非交互环境（如 Agent HTTP 服务、CI）默认拒绝，避免阻塞或崩溃
    if os.environ.get("FR_CLI_NON_INTERACTIVE"):
        return False, sconfirm, fconfirm

    print(f"\n{RED}{BOLD}{T('sec_title', l)}{RESET}")
    print(f"{YELLOW}  >> {T(k, l)}: {d}{RESET}")
    print(f"    {CYAN}{T('sec_opt_y', l)}  {T('sec_opt_a', l)}  {T('sec_opt_f', l)}  {T('sec_opt_n', l)}{RESET}")

    while True:
        c = input(f"{BOLD}    👉 {RESET}").strip().lower()
        if c == 'y':
            return True, sconfirm, fconfirm
        elif c == 'a':
            return True, True, fconfirm
        elif c == 'f':
            # 永久放行，写入配置文件
            sconfirm = True
            fconfirm = True
            config["auto_confirm_forever"] = True
            save_config(config)
            return True, sconfirm, fconfirm
        elif c == 'n' or c == '':
            return False, sconfirm, fconfirm