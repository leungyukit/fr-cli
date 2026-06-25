"""
REPL /model 与 /model config 命令 —— 模型切换与配置向导
"""
from fr_cli.ui.ui import CYAN, RED, YELLOW, GREEN, DIM, RESET
from fr_cli.repl.commands._common import _provider_has_key


def _cmd_model(state, parts):
    """模型切换命令

    子命令风格（专业 CLI 格式）:
      /model              — 交互式选择
      /model config       — 交互式模型配置向导（推荐新手）
      /model list         — 列出所有可用模型
      /model current      — 显示当前模型
      /model default      — 恢复当前提供商的默认模型
      /model set <arg>    — 设置模型（等同 /model <arg>）
      /model <arg>        — 直接切换（向后兼容）

    <arg> 支持格式:
      - <编号>            如: 3
      - <模型名>          如: deepseek-chat
      - <提供商>:<模型>   如: deepseek:deepseek-chat
    """
    arg1 = parts[1] if len(parts) > 1 else ""
    from fr_cli.core.llm import list_providers, get_provider_info
    providers = list_providers()

    # ---------- 子命令处理 ----------
    if arg1 in ("list", "ls"):
        print(f"{CYAN}当前模型: [{state.provider}] {state.display_model}{RESET}")
        print(f"\n{DIM}可用模型列表:{RESET}")
        for i, p in enumerate(providers, 1):
            marker = " [当前]" if p["id"] == state.provider else ""
            has_key = _provider_has_key(state, p["id"])
            key_status = f"{GREEN}[已配置]{RESET}" if has_key else f"{RED}[未配置]{RESET}"
            print(f"  {CYAN}[{i}]{RESET} {p['id']}{DIM}/{p['default_model']}{RESET} — {p['name']} {key_status}{marker}")
        print(f"\n{DIM}用法: /model <编号|模型名|提供商:模型>{RESET}")
        return False

    if arg1 in ("current", "status", "now"):
        info = get_provider_info(state.provider)
        print(f"{CYAN}当前模型信息:{RESET}")
        print(f"  提供商: {state.provider} ({info.get('name', '?') if info else '?'})")
        print(f"  模型:   {state.display_model}")
        print(f"  限制:   {state.limit} tokens")
        return False

    if arg1 == "default":
        from fr_cli.core.llm import get_provider_info
        info = get_provider_info(state.provider)
        if info:
            state.update_model(info["default_model"])
            print(f"{GREEN}已恢复默认模型: [{state.provider}] {state.display_model}{RESET}")
        return False

    if arg1 in ("config", "setup", "wizard"):
        return _cmd_model_config(state)

    if arg1 == "set":
        arg1 = parts[2] if len(parts) > 2 else ""
        if not arg1:
            print(f"{RED}用法: /model set <编号|模型名|提供商:模型>{RESET}")
            return False

    # ---------- 无参数：交互式选择 ----------
    if not arg1:
        print(f"{CYAN}当前模型: [{state.provider}] {state.display_model}{RESET}")
        print(f"\n{DIM}可用模型列表:{RESET}")
        for i, p in enumerate(providers, 1):
            marker = " [当前]" if p["id"] == state.provider else ""
            has_key = _provider_has_key(state, p["id"])
            key_status = f"{GREEN}[已配置]{RESET}" if has_key else f"{RED}[未配置]{RESET}"
            print(f"  {CYAN}[{i}]{RESET} {p['id']}{DIM}/{p['default_model']}{RESET} — {p['name']} {key_status}{marker}")

        print(f"\n{DIM}快速切换:{RESET}")
        print("  /model <编号>       — 按编号切换")
        print("  /model <模型名>     — 切换模型")
        print("  /model <提供商>:<模型> — 同时切换提供商")
        print("  /model config       — 交互式模型配置向导（推荐新手）")

        try:
            choice = input(f"\n{YELLOW}输入编号或模型名（回车取消）: {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"{DIM}已取消。{RESET}")
            return False

        if not choice:
            return False
        arg1 = choice

    # ---------- 执行切换 ----------
    # 支持按编号切换
    if arg1.isdigit():
        idx = int(arg1) - 1
        if 0 <= idx < len(providers):
            target = providers[idx]
            arg1 = f"{target['id']}:{target['default_model']}"
        else:
            print(f"{RED}编号超出范围，有效范围: 1-{len(providers)}{RESET}")
            return False

    ok = state.update_model(arg1)
    if ok:
        print(f"{GREEN}已切换: [{state.provider}] {state.display_model}{RESET}")
        if hasattr(state, '_prompt') and state._prompt:
            state._prompt.update_status(model=state.display_model, provider=state.display_provider)
        if not _provider_has_key(state, state.provider):
            print(f"{YELLOW}注意: [{state.provider}] 尚未配置 API Key{RESET}")
            try:
                k = input(f"请输入 [{state.provider}] 的 API Key: ").strip()
            except (EOFError, KeyboardInterrupt):
                k = ""
            if k:
                state.update_key(k)
                print(f"{GREEN}[{state.provider}] API Key 已保存{RESET}")
            else:
                print(f"{RED}未输入 Key，[{state.provider}] 可能无法正常使用{RESET}")
    else:
        print(f"{RED}无效的提供商或模型: {arg1}{RESET}")
    return False


def _cmd_model_config(state):
    """交互式模型配置向导 —— /model config

    v2.5+: 委托给 conf/model_wizard.run_model_wizard(6 步流程),
    保持设置完成后自动切换并保存。
    """
    from fr_cli.conf.model_wizard import run_model_wizard
    try:
        run_model_wizard(state.cfg, mode="add")
    except (KeyboardInterrupt, EOFError):
        print(f"\n{DIM}已取消。{RESET}")
        return False
    # 应用新配置到 state
    state.reinit_client()
    # 同步显示
    if hasattr(state, '_prompt') and state._prompt:
        state._prompt.update_status(model=state.display_model, provider=state.display_provider)
    return False

