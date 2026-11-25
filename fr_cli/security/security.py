"""
四阶安全确认引擎

v2.4.4 行为变更：
- `auto_confirm_forever` 从单一 bool 拆为 `auto_confirm` 字典，按 sec_* 类别独立放行
  （如只对 sec_read 永久放行，不会顺带放过 sec_write/sec_exec）
- 新增 `clear_all_auto_confirm()` 全局撤销（供 /unconfirm 命令使用）
"""
import os
import threading
from fr_cli.ui.ui import RED, BOLD, YELLOW, CYAN, DIM, RESET, print_styled, use_color
from fr_cli.lang.i18n import T
from fr_cli.conf.config import save_config

#: 安全确认的**全局互斥锁**（v2.8.7 P2-3）。
#:
#: 并行工具调用（【并行调用】标记路径 / 原生 function calling 多 tool_calls）
#: 会在多个线程里同时走到这里。若不串行化，两个线程会同时 ``input()`` ——
#: 终端输入被抢走，**用户回答的 Y/A/F/N 可能落到另一个工具上**
#: （"允许读文件"被当成"允许执行命令"），这是安全问题，不只是显示问题。
#:
#: 用 RLock 而非 Lock：同一个工具内部再触发一次确认时不能自锁死。
_CONFIRM_LOCK = threading.RLock()


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

    # ReAct 工具执行跑在 prompt_toolkit patch_stdout 代理里(queue.py), 裸 print
    # 打色会把 ESC 替换成 '?' 泄漏 ?[91m 乱码; 统一走 print_styled(色关自动剥序列)
    #
    # 整段提示 + 读输入放进全局锁 —— 并行工具调用时**同一时刻只会有一个确认问句**,
    # 用户的 Y/A/F/N 不会串到别的工具上（见 _CONFIRM_LOCK 注释）。
    with _CONFIRM_LOCK:
        print_styled(f"\n{RED}{BOLD}{T('sec_title', l)}{RESET}")
        print_styled(f"{YELLOW}  >> {T(k, l)}: {d}{RESET}")
        print_styled(f"    {CYAN}{T('sec_opt_y', l)}  {T('sec_opt_a', l)}  {T('sec_opt_f', l)}  {T('sec_opt_n', l)}{RESET}")

        # v2.8.7：后台线程发起确认时**不能**用裸 input() ——
        # 主线程的 prompt_toolkit 正占着 stdin（raw 模式），两边抢同一个 fd：
        # 用户敲的 Y/A/F/N 全被输入框吞掉，input() 永远等不到 → 终端假死。
        # 改由主线程代读，答案经确认中转站送回（详见 security/interactive.py）。
        if _use_confirm_broker():
            print_styled(f"  {DIM}↳ 请在下方输入框输入 Y / A / F / N 回答{RESET}")
            while True:
                c = _request_confirm_via_broker(k, d)
                if c is None:
                    # 超时 / 取消 / 中转站被关闭 —— 按"拒绝"处理（fail-closed）
                    return False, sconfirm, fconfirm
                decision = _resolve_answer(c, k, sconfirm, fconfirm, config)
                if decision is not None:
                    return decision
                print_styled(f"  {YELLOW}[!] 请输入 Y/A/F/N 之一{RESET}")

        while True:
            # input() 提示同理: 代理期不能带转义序列, 退化为纯空格
            prompt = f"{BOLD} {RESET}" if use_color() else " "
            try:
                c = input(prompt).strip().lower()
            except (EOFError, KeyboardInterrupt):
                # 非交互 / 用户中断 —— 按"拒绝"处理，不能让整批工具卡死
                return False, sconfirm, fconfirm
            decision = _resolve_answer(c, k, sconfirm, fconfirm, config)
            if decision is not None:
                return decision
            # 未识别输入：重新提示（保留原 UX）
            print_styled(f"  {YELLOW}[!] 请输入 Y/A/F/N 之一{RESET}")


def _use_confirm_broker() -> bool:
    """本次确认是否走「主线程代读」通道。

    两条同时满足才走中转站：

    1. 中转站已启用（REPL 有 prompt_toolkit 输入框时才启用）
    2. 当前**不是**主线程 —— 主线程自己发起确认时（斜杠命令里触发的高危操作）
       此刻并没有 prompt_toolkit 在读 stdin，裸 ``input()`` 才是对的；
       走中转站会自己等自己（死锁）。
    """
    try:
        from fr_cli.security.interactive import BROKER
        if not BROKER.enabled:
            return False
        return threading.current_thread() is not threading.main_thread()
    except Exception:
        return False


def _request_confirm_via_broker(k, d):
    """向主线程请求一次确认答案（阻塞）。

    Returns:
        str | None: 答案；超时 / 取消返回 None（调用方按拒绝处理）
    """
    try:
        from fr_cli.security.interactive import BROKER, DEFAULT_TIMEOUT
        return BROKER.request(k, d, timeout=DEFAULT_TIMEOUT)
    except Exception:
        return None


def _resolve_answer(c, k, sconfirm, fconfirm, config):
    """把一次 Y/A/F/N 输入落成放行决策。

    Returns:
        tuple | None: (是否放行, sconfirm, fconfirm)；``None`` 表示输入无法识别，
                      调用方应重新提示。
    """
    c = (c or "").strip().lower()
    if c in ('y', 'yes'):
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
    elif c in ('n', 'no', ''):
        return False, sconfirm, fconfirm
    return None


def _migrate_fconfirm(fconfirm):
    """把旧版 fconfirm = bool 迁移为 v2.4.4 的 dict 形式。

    - bool True → {"sec_read": True, "sec_write": True, "sec_exec": True, ...所有已知 sec_*}
      （保守策略：旧版一键放行所有类别，迁移时维持语义）
    - bool False → {}
    - dict → 原样返回
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
