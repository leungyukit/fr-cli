"""
/start 命令 — 一键快速开始向导(痛点 5)

5 步友好引导,适合首次启动后调起,也适合老用户快速回顾:
  1. 欢迎 + 检测环境
  2. 模型配置(若未配,引导走 /providers setup)
  3. MasterAgent 简介 + 是否启用
  4. 核心命令简介(3 条)
  5. 完成 + 写 start_wizard_done 标志

用法:
  /start         — 跑 5 步向导
  /start skip    — 跳过向导(等价于设置 start_wizard_done=True)
  /start reset   — 重置标志,下次 /start 重新跑
"""
from fr_cli.ui.output import (
    success, failure, warning, info, header
)
from fr_cli.ui.ui import CYAN, GREEN, DIM, RESET


def _has_model_configured(state) -> bool:
    """是否已配置好模型(provider + key 都有)"""
    cfg = getattr(state, "cfg", {}) or {}
    has_provider = bool(cfg.get("default_provider") or cfg.get("provider"))
    providers_cfg = cfg.get("providers", {})
    has_any_key = bool(providers_cfg) and any(
        bool(p.get("key")) for p in providers_cfg.values()
    )
    if not has_any_key and cfg.get("key"):
        has_any_key = True
    return has_provider and has_any_key


def _step_welcome(state) -> None:
    """步骤 1:欢迎 + 检测环境"""
    header("Step 1/5 · 欢迎使用 fr-cli")
    print(f"  {DIM}凡人打字机 — 你的终端 AI 助手{RESET}")
    print(f"  {DIM}· 模型: {state.provider}/{state.display_model}{RESET}")
    print(f"  {DIM}· 语言: {state.lang}{RESET}")
    print(f"  {DIM}· 工作目录: {getattr(state, 'vfs', None) and state.vfs.cwd or '(未挂载)'}{RESET}")
    print()


def _step_model(state) -> bool:
    """步骤 2:模型配置

    Returns: True 表示已配置好,可继续
    """
    header("Step 2/5 · 模型配置")
    if _has_model_configured(state):
        info(f"已配置: {state.provider}/{state.display_model}")
        return True

    warning("尚未配置任何模型", detail="需要至少一个 API Key 才能调用 AI")
    print()
    print(f"  {DIM}将启动 6 步模型配置向导...{RESET}")
    try:
        from fr_cli.conf.model_wizard import run_model_wizard
        cfg = run_model_wizard(state.cfg, mode="setup")
        state.cfg = cfg
        state.reinit_client()
        success("模型配置完成")
        return _has_model_configured(state)
    except (KeyboardInterrupt, EOFError):
        failure("配置被取消", suggestion="随时跑 /providers setup 重试")
        return False


def _step_master_agent(state) -> bool:
    """步骤 3:MasterAgent 简介 + 是否启用"""
    header("Step 3/5 · MasterAgent 主控(可选)")
    info("MasterAgent 是一个 ReAct 循环的中央控制器")
    print(f"  {DIM}· 启用后,所有对话走 ReAct 循环,自动调用工具{RESET}")
    print(f"  {DIM}· 每 10 次交互会自动反思并进化 prompt{RESET}")
    print(f"  {DIM}· 适合:复杂多步任务; 不适合:快速问答{RESET}")
    print()
    master = getattr(state, "master_agent", None)
    if master and getattr(master, "is_enabled", lambda: False)():
        success("MasterAgent 已启用")
        return True
    try:
        yn = input(f"{CYAN}👉 启用 MasterAgent? [y/N]: {RESET}").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if yn in ("y", "yes", "是"):
        try:
            master.toggle(True)
            success("MasterAgent 已启用")
        except Exception as e:
            failure(f"启用失败: {e}")
    else:
        info("已跳过,稍后可用 /master on 启用")
    return True


def _step_quick_commands(state) -> None:
    """步骤 4:核心命令简介(3 条)"""
    header("Step 4/5 · 3 条核心命令")
    print()
    print(f"  {GREEN}/help{RESET}             {DIM}查看所有命令 + 最近新功能{RESET}")
    print(f"  {GREEN}/insight extract{RESET}  {DIM}跑一次选品洞察提炼(从历史数据提炼爆款规律){RESET}")
    print(f"  {GREEN}/master on/off{RESET}    {DIM}开/关 MasterAgent 自控模式{RESET}")
    print()


def _step_done(state) -> None:
    """步骤 5:写标志 + 收尾"""
    header("Step 5/5 · 完成 🎉")
    state.cfg["start_wizard_done"] = True
    state.save_cfg()
    info("已标记 /start 完成,下次启动不再弹向导")
    print()
    info("下一步建议:")
    print(f"  {DIM}· 输 {CYAN}/help new{RESET}{DIM} 看最近新功能{RESET}")
    print(f"  {DIM}· 输 {CYAN}/status{RESET}{DIM} 看全局状态{RESET}")
    print(f"  {DIM}· 直接跟我对话: {CYAN}你好,介绍一下你自己{RESET}{DIM}{RESET}")
    print()


def _cmd_start(state, parts):
    """/start 一键快速开始向导(痛点 5)

    用法:
      /start         — 跑 5 步向导
      /start skip    — 跳过,设置标志
      /start reset   — 重置标志
    """
    arg1 = parts[1].lower() if len(parts) > 1 else ""

    if arg1 == "skip":
        state.cfg["start_wizard_done"] = True
        state.save_cfg()
        success("已标记 /start 跳过,下次启动不再弹")
        return False

    if arg1 == "reset":
        state.cfg["start_wizard_done"] = False
        state.save_cfg()
        info("已重置 /start 标志,下次 /start 会完整跑一遍")
        return False

    if arg1 and arg1 not in ("skip", "reset"):
        failure(f"未知参数: {arg1}", suggestion="用法: /start [skip|reset]")
        return False

    # 跑 5 步
    _step_welcome(state)
    if not _step_model(state):
        return False
    _step_master_agent(state)
    _step_quick_commands(state)
    _step_done(state)
    return False
