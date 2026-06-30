"""
REPL 命令路由处理器
从 main.py 提取的所有 / 命令实现，减轻主模块负担。
"""

from fr_cli.lang.i18n import T
from fr_cli.ui.ui import (
    CYAN, RED, YELLOW, GREEN, DIM, RESET,
    print_bye
)
from fr_cli.agent.shell_mode import ShellMode
from fr_cli.core.stream import stream_cnt
from fr_cli.core.sysmon import get_sys_stats
from fr_cli.repl.commands._common import _print_help



def _cmd_exit(state, parts):
    print_bye()
    return True



def _cmd_shell(state, parts):
    """进入 Shell 模式"""
    from fr_cli.agent.shell_mode import get_shell_manager

    shell_mgr = get_shell_manager()
    shell_mgr.current_mode = ShellMode.SHELL if shell_mgr.current_mode == ShellMode.AGENT else ShellMode.AGENT

    if shell_mgr.current_mode == ShellMode.SHELL:
        print(f"{GREEN}🆗 进入 Shell 模式 - 直接执行命令，输入 exit 返回{RESET}")
        while shell_mgr.current_mode == ShellMode.SHELL:
            try:
                cmd = input("(shell) $ ").strip()
                if not cmd:
                    continue
                if cmd in ['exit', 'quit', 'q']:
                    print(f"{YELLOW}退出 Shell 模式{RESET}")
                    break
                output, code = shell_mgr.execute_command(cmd)
                print(output)
                if code != 0:
                    print(f"[exit {code}]")
            except (EOFError, KeyboardInterrupt):
                print(f"\n{YELLOW}退出 Shell 模式{RESET}")
                break
        shell_mgr.current_mode = ShellMode.AGENT
    else:
        print(f"{GREEN}切换回 Agent 模式{RESET}")
    return False



def _cmd_help(state, parts):
    arg1 = parts[1] if len(parts) > 1 else ""
    _print_help(state, arg1.lower())
    return False



def _cmd_see(state, parts):
    from fr_cli.weapon.vision import prep_see_msg
    arg1 = parts[1] if len(parts) > 1 else ""
    if not arg1:
        return False
    # 检查当前模型是否为当前 provider 配置的视觉模型
    from fr_cli.core.llm import get_provider_info
    info = get_provider_info(state.provider)
    vision_models = info.get("vision_models", []) if info else []
    if state.model_name not in vision_models:
        print(f"{YELLOW}{T('see_warn', state.lang)}{RESET}")
    print(f"{CYAN}{T('see_ing', state.lang)}{RESET}")
    prep_see_msg(state.messages, arg1, parts[2] if len(parts) > 2 else "", vfs=state.vfs)
    txt, _, response_time, _ = stream_cnt(
        state.client, state.model_name, state.messages, state.lang,
        max_tokens=state.limit
    )
    state.messages.append({"role": "assistant", "content": txt})
    sys_stats = get_sys_stats(state.lang)
    stats_extra = f" | {sys_stats}" if sys_stats else ""
    print(f"{DIM}📊 {T('stats_model', state.lang)}: {state.display_model} | {T('stats_time', state.lang)}: {response_time:.2f}{T('stats_seconds', state.lang)}{stats_extra}{RESET}")
    return False



def _cmd_update(state, parts):
    from fr_cli.breakthrough.update import update_check, update_and_restart
    arg1 = parts[1] if len(parts) > 1 else ""
    if arg1 == "check":
        ok, info, err = update_check(verbose=False)
        if err:
            print(f"{RED}[更新] 检查失败: {err}{RESET}")
        elif not ok:
            print(f"{GREEN}[更新] 当前已是最新版本。{RESET}")
        else:
            ver = info.get("version", "?")
            note = info.get("release_note", "")
            print(f"{YELLOW}[更新] 发现新版本: {ver}{RESET}")
            if note:
                print(f"{DIM}更新说明:\n{note}{RESET}")
            print(f"{DIM}输入 /update run 执行更新{RESET}")
    elif arg1 == "run":
        print(f"{YELLOW}[更新] 正在连接天道获取最新法器...{RESET}")
        ok, msg = update_and_restart(verbose=True, allow_restart=True)
        if ok:
            print(f"{GREEN}{msg}{RESET}")
        else:
            print(f"{RED}{msg}{RESET}")
    else:
        print(f"{DIM}用法: /update check (检查) | /update run (执行更新){RESET}")
    return False



def _cmd_mode(state, parts):
    """切换思维模式或 UI 模式"""
    arg1 = parts[1] if len(parts) > 1 else ""

    # UI 模式切换: /mode ui <chat|dev|agent>
    if arg1.lower() == "ui":
        arg2 = parts[2] if len(parts) > 2 else ""
        if not arg2:
            print(f"{CYAN}当前 UI 模式: {getattr(state, 'ui_mode', 'dev')}{RESET}")
            print(f"{DIM}可用模式: chat（纯对话）| dev（开发模式，默认）| agent（Agent 主控）{RESET}")
            return False
        ui_mode = arg2.lower()
        if ui_mode not in ("chat", "dev", "agent"):
            print(f"{RED}无效 UI 模式: {ui_mode}{RESET}")
            print(f"{DIM}可用模式: chat | dev | agent{RESET}")
            return False
        ok = state.update_ui_mode(ui_mode)
        if ok:
            ui_desc = {
                "chat": "纯对话模式 — AI 只回答，不主动调用工具",
                "dev": "开发模式 — AI 可以读写文件、执行命令、搜索等",
                "agent": "Agent 模式 — 启用自我进化主控，AI 自主规划执行",
            }
            print(f"{GREEN}✅ UI 模式已切换: {ui_desc.get(ui_mode, ui_mode)}{RESET}")
        return False

    # 思维模式切换: /mode <direct|cot|tot|react>
    # MasterAgent 模式下思维模式由其内部 ReAct 循环控制，/mode 无效
    if getattr(state, 'master_agent', None) and state.master_agent.is_enabled():
        print(f"{YELLOW}⚠️ MasterAgent 主控模式下，思维模式由其内部 ReAct 循环自主管理，/mode 命令无效。{RESET}")
        print(f"{DIM}  提示: 使用 /master off 关闭主控后可切换思维模式。{RESET}")
        return False

    from fr_cli.core.thinking import ThinkingEngine
    if not arg1:
        print(f"{CYAN}当前思维模式: {state.thinking_mode}{RESET}")
        print(f"{CYAN}当前 UI 模式: {getattr(state, 'ui_mode', 'dev')}{RESET}")
        print(f"{DIM}思维模式: direct（直接回答）| cot（思维链）| tot（思维树）| react（推理+行动）| plan（计划模式）{RESET}")
        print(f"{DIM}UI 模式: /mode ui chat | /mode ui dev | /mode ui agent{RESET}")
        return False
    mode = arg1.lower()
    if not ThinkingEngine.is_valid_mode(mode):
        print(f"{RED}无效模式: {mode}{RESET}")
        print(f"{DIM}思维模式: direct | cot | tot | react | plan{RESET}")
        print(f"{DIM}UI 模式: /mode ui <chat|dev|agent>{RESET}")
        return False
    state.update_thinking_mode(mode)
    mode_desc = {
        "direct": "直接回答（默认）",
        "cot": "思维链 — 先进行问题拆解和自我验证，再回答",
        "tot": "思维树 — 生成多分支策略树，评估后选择最优路径",
        "react": "ReAct — 每一步先思考再行动，循环直到问题解决",
        "plan": "计划模式 — 先制定结构化计划，确认后按步骤执行并汇总",
    }
    print(f"{GREEN}✅ 思维模式已切换: {mode_desc.get(mode, mode)}{RESET}")
    return False



def _cmd_banner(state, parts):
    """开关启动画面"""
    arg1 = parts[1] if len(parts) > 1 else ""
    if arg1.lower() in ("on", "1", "true", "enable"):
        state.cfg["banner_enabled"] = True
        state.save_cfg()
        print(f"{GREEN}✅ 启动画面已开启{RESET}")
    elif arg1.lower() in ("off", "0", "false", "disable"):
        state.cfg["banner_enabled"] = False
        state.save_cfg()
        print(f"{GREEN}✅ 启动画面已关闭{RESET}")
    else:
        status = "开启" if state.cfg.get("banner_enabled", True) else "关闭"
        print(f"{CYAN}启动画面: {status}{RESET}")
        print(f"{DIM}用法: /banner on | /banner off{RESET}")
    return False



def _cmd_tutorial(state, parts):
    """交互式新手教程(从 i18n 加载)"""
    from fr_cli.ui.ui import CYAN, GREEN, YELLOW, DIM, RESET

    lang = state.lang
    steps = []
    for i in range(1, 11):
        title = T(f"tutorial_step{i}_title", lang)
        content = T(f"tutorial_step{i}_content", lang)
        if title and content:
            steps.append((title, content))

    print(f"{CYAN}{'='*50}{RESET}")
    print(f"{CYAN}  {T('tutorial_title', lang)}{RESET}")
    print(f"{CYAN}{'='*50}{RESET}\n")

    total = len(steps)
    for i, (title, content_step) in enumerate(steps, 1):
        print(f"{GREEN}{title}{RESET}")
        print(f"{DIM}{content_step}{RESET}")
        if i < total:
            print(f"\n{YELLOW}{T('tutorial_prompt_next', lang)}{RESET}")
            try:
                input()
            except (EOFError, KeyboardInterrupt):
                print(f"\n{YELLOW}{T('tutorial_skipped', lang)}{RESET}")
                return False

    print(f"\n{GREEN}{T('tutorial_complete', lang)}{RESET}")
    print(f"{DIM}{T('tutorial_hint', lang)}{RESET}")
    return False
