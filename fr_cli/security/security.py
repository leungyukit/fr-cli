"""
四阶安全确认引擎

v2.4.4 行为变更：
- `auto_confirm_forever` 从单一 bool 拆为 `auto_confirm` 字典，按 sec_* 类别独立放行
  （如只对 sec_read 永久放行，不会顺带放过 sec_write/sec_exec）
- 新增 `clear_all_auto_confirm()` 全局撤销（供 /unconfirm 命令使用）
"""
import os
from fr_cli.ui.ui import RED, BOLD, YELLOW, CYAN, RESET
from fr_cli.lang.i18n import T
from fr_cli.conf.config import save_config


def clear_all_auto_confirm(config):
    """清除所有 sec_* 的永久放行设置（/unconfirm 入口）。"""
    if "auto_confirm" in config:
        del config["auto_confirm"]
    # 兼容旧字段
    if "auto_confirm_forever" in config:
        del config["auto_confirm_forever"]
    save_config(config)


def ask(k, d, l, fconfirm, sconfirm, config):
    """
    安全询问逻辑
    :param k: 操作类型键名 (如 sec_read, sec_exec)
    :param d: 具体操作描述 (如文件名或命令)
    :param l: 当前语言
    :param fconfirm: 永久放行状态（v2.4.4 起为 dict，按 sec_* 类别；旧版 bool 自动迁移）
    :param sconfirm: 本次会话放行状态（dict 或 bool）
    :param config: 配置字典对象 (用于持久化永久放行状态)
    :return: tuple (是否放行:bool, 更新后的sconfirm, 更新后的fconfirm)
    注：security 返回的是内部状态三元组，不适用 Result 成功/失败语义，保持元组以兼容现有调用方。
    """
    # 批量确认模式（用于脚本/自动化场景）
    if os.environ.get("FR_CLI_BATCH_CONFIRM") == "1":
        return True, sconfirm, fconfirm

    # 兼容旧版 fconfirm = bool 的情况
    fconfirm = _migrate_fconfirm(fconfirm)
    sconfirm = _migrate_sconfirm(sconfirm)

    # 如果当前 sec_* 类别已永久放行，直接放行
    if fconfirm.get(k, False):
        return True, sconfirm, fconfirm
    # 本次会话放行状态（仅对当前 sec_* 类别生效）
    if isinstance(sconfirm, dict) and sconfirm.get(k, False):
        return True, sconfirm, fconfirm
    # 旧版 sconfirm = True（全类别放行）—— 保留兼容
    if sconfirm is True:
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
            # 仅对当前 sec_* 类别标记本次会话放行
            sconfirm[k] = True
            return True, sconfirm, fconfirm
        elif c == 'f':
            # 仅对当前 sec_* 类别永久放行（v2.4.4 关键修复：不波及其他类别）
            sconfirm[k] = True
            fconfirm[k] = True
            config["auto_confirm"] = dict(fconfirm)
            # 兼容清理：如果旧版 bool 字段存在且为 True，但新版 dict 已细粒度化，删除旧字段
            if "auto_confirm_forever" in config:
                del config["auto_confirm_forever"]
            save_config(config)
            return True, sconfirm, fconfirm
        elif c == 'n' or c == '':
            return False, sconfirm, fconfirm
        # 未识别输入：重新提示（保留原 UX）
        print(f"  {YELLOW}⚠️ 请输入 Y/A/F/N 之一{RESET}")


def _migrate_fconfirm(fconfirm):
    """把旧版 fconfirm = bool 迁移为 v2.4.4 的 dict 形式。

    - bool True  →  {"sec_read": True, "sec_write": True, "sec_exec": True, ...所有已知 sec_*}
      （保守策略：旧版一键放行所有类别，迁移时维持语义）
    - bool False → {}
    - dict      → 原样返回
    """
    if isinstance(fconfirm, dict):
        return fconfirm
    if fconfirm is True:
        # 列出所有已知 sec_* 类别，迁移时全部置 True 维持旧语义
        # 类别表与 fr_cli/lang/translations/*.py 中 help_detail_security 保持一致
        return {
            "sec_read": True,
            "sec_write": True,
            "sec_exec": True,
            "sec_set_key": True,
            "sec_set_model": True,
            "sec_set_limit": True,
            "sec_set_lang": True,
            "sec_set_alias": True,
            "sec_mcp_call": True,
            "sec_read_mail": True,
            "sec_open_file": True,
            "sec_launch_app": True,
            "sec_create_agent": True,
            "sec_update": True,
            "sec_m365_config": True,
            "sec_mount": True,
            "sec_gen_img": True,
            "sec_send_mail": True,
            "sec_fetch_web": True,
            "sec_upload_disk": True,
            "sec_download_disk": True,
            "sec_shell": True,
        }
    return {}


def _migrate_sconfirm(sconfirm):
    """把旧版 sconfirm = bool 迁移为 dict 形式（仅本次会话，不持久化）。"""
    if isinstance(sconfirm, dict):
        return sconfirm
    if sconfirm is True:
        return _migrate_fconfirm(True)
    return {}
