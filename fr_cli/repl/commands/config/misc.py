"""
REPL 杂项配置命令 —— /limit, /lang, /usage, /autonomous
"""
import os

from fr_cli.lang.i18n import T
from fr_cli.ui.ui import CYAN, RED, YELLOW, GREEN, DIM, RESET


def _cmd_limit(state, parts):
    arg1 = parts[1] if len(parts) > 1 else ""
    if arg1:
        try:
            v = int(arg1)
            if v < 1000:
                raise ValueError
            state.update_limit(v)
            print(f"{GREEN}{T('ok_limit', state.lang, v)}{RESET}")
        except ValueError:
            print(f"{RED}{T('err_limit', state.lang)}{RESET}")
    return False


def _cmd_lang(state, parts):
    arg1 = parts[1] if len(parts) > 1 else ""
    if arg1:
        if arg1 in ["zh", "en"]:
            state.update_lang(arg1)
            print(f"{GREEN}语言已切换为: {'中文' if arg1 == 'zh' else 'English'}{RESET}")
        else:
            print(f"{RED}支持的语言: zh (中文), en (English){RESET}")
    return False


def _cmd_usage(state, parts):
    """查看 LLM 用量统计：/usage [days]"""
    arg1 = parts[1] if len(parts) > 1 else ""
    try:
        days = int(arg1) if arg1 else 30
        if days <= 0:
            days = 30
    except ValueError:
        days = 30

    if not hasattr(state, "usage"):
        print(f"{RED}用量统计模块未初始化{RESET}")
        return False

    stats = state.usage.summary(days=days)
    is_zh = state.lang == "zh"
    print()
    title = f"最近 {days} 天用量统计" if is_zh else f"Usage last {days} days"
    print(f"{CYAN}{title}{RESET}")
    print(f"  {DIM}{'调用次数:' if is_zh else 'Calls:'}{RESET} {stats['calls']}")
    print(f"  {DIM}{'输入 tokens:' if is_zh else 'Input tokens:'}{RESET} {stats['prompt_tokens']}")
    print(f"  {DIM}{'输出 tokens:' if is_zh else 'Output tokens:'}{RESET} {stats['completion_tokens']}")
    print(f"  {DIM}{'总 tokens:' if is_zh else 'Total tokens:'}{RESET} {stats['total_tokens']}")
    cost_label = "预估费用:" if is_zh else "Estimated cost:"
    print(f"  {DIM}{cost_label}{RESET} ¥{stats['estimated_cost']:.4f}")
    if is_zh:
        print(f"  {DIM}提示: 可在 config.json 中配置 usage_prices 以启用精确费用估算{RESET}")
    else:
        print(f"  {DIM}Tip: configure usage_prices in config.json for accurate cost estimation{RESET}")
    return False


def _cmd_autonomous(state, parts):
    """
    查看/设置自治模式
    用法:
      /autonomous                  — 显示当前自治模式
      /autonomous manual           — 默认：每次 sec_* 都询问
      /autonomous sandbox_auto     — 沙盒内读/写/网络自动放行，系统级仍询问
      /autonomous full_auto        — 所有操作自动放行（危险）
      /autonomous off              — 等同于 manual
    """
    arg1 = parts[1] if len(parts) > 1 else ""
    if not arg1:
        mode = getattr(state.security, "autonomous_mode", "manual")
        env_override = os.environ.get("FR_CLI_AUTONOMOUS_MODE")
        print(f"{CYAN}当前自治模式: {mode}{RESET}")
        if env_override:
            print(f"{YELLOW}环境变量覆盖: FR_CLI_AUTONOMOUS_MODE={env_override}{RESET}")
        print(f"{DIM}可用模式: manual | sandbox_auto | full_auto | off{RESET}")
        return False

    mode = arg1.lower().strip()
    from fr_cli.security.policy import normalize_autonomous_mode
    normalized = normalize_autonomous_mode(mode)

    if mode not in ("manual", "sandbox_auto", "full_auto", "off"):
        print(f"{RED}❌ 未知模式: {arg1}{RESET}")
        print(f"{DIM}用法: /autonomous [manual|sandbox_auto|full_auto|off]{RESET}")
        return False

    ok = state.security.set_autonomous_mode(normalized)
    if ok:
        label = {
            "manual": "手动确认（默认）",
            "sandbox_auto": "沙盒自动 / 系统确认",
            "full_auto": "完全自动（危险）",
        }.get(normalized, normalized)
        print(f"{GREEN}✅ 自治模式已设为: {label} ({normalized}){RESET}")
    else:
        print(f"{RED}❌ 设置失败{RESET}")
    return False