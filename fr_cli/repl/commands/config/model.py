"""
REPL /model 与 /model config 命令 —— 模型切换与配置向导
"""
from fr_cli.lang.i18n import T
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

    流程:
      1. 列出所有 provider，让用户选择
      2. 列出该 provider 下的可用模型，让用户选择
      3. 设置完成后自动切换并保存
      4. 任意步骤输入 q / 空回车 / Ctrl+C 退出
    """
    from fr_cli.core.llm import list_providers, get_provider_info
    providers = list_providers()
    if not providers:
        print(f"{RED}❌ 没有可用的模型提供商{RESET}")
        return False

    print()
    print(f"{CYAN}╔{'═' * 50}╗{RESET}")
    print(f"{CYAN}║{'🧙  模型配置向导':^48}║{RESET}")
    print(f"{CYAN}╚{'═' * 50}╝{RESET}")

    # ── 第一步：选择 Provider ──
    print(f"\n{DIM}第一步：选择模型提供商{RESET}")
    print(f"{DIM}输入编号选择，或输入 q / 回车退出{RESET}\n")
    for i, p in enumerate(providers, 1):
        marker = f" {YELLOW}👈 当前{RESET}" if p["id"] == state.provider else ""
        has_key = _provider_has_key(state, p["id"])
        key_status = f"{GREEN}✓{RESET}" if has_key else f"{RED}✗{RESET}"
        print(f"  {CYAN}[{i}]{RESET} {key_status} {p['id']} — {p['name']}{DIM} (默认: {p['default_model']}){RESET}{marker}")

    try:
        choice = input(f"\n{YELLOW}👉 Provider 编号 (q/回车退出): {RESET}").strip()
    except (EOFError, KeyboardInterrupt):
        print(f"\n{DIM}已取消。{RESET}")
        return False

    if not choice or choice.lower() == "q":
        print(f"{DIM}已取消。{RESET}")
        return False

    if not choice.isdigit():
        print(f"{RED}❌ 请输入有效编号{RESET}")
        return False

    idx = int(choice) - 1
    if idx < 0 or idx >= len(providers):
        print(f"{RED}❌ 编号超出范围，有效范围: 1-{len(providers)}{RESET}")
        return False

    selected_provider = providers[idx]
    provider_id = selected_provider["id"]
    info = get_provider_info(provider_id)

    # ── 第二步：选择 Model ──
    models = info.get("models", [info.get("default_model", "")]) if info else [selected_provider.get("default_model", "")]
    default_model = info.get("default_model", models[0]) if info else models[0]

    print()
    print(f"{DIM}第二步：选择模型 — {CYAN}{provider_id}{RESET}{DIM}{RESET}")
    print(f"{DIM}输入编号选择，或输入 q / 回车返回上一步{RESET}\n")
    for i, m in enumerate(models, 1):
        marker = f" {YELLOW}★ 默认{RESET}" if m == default_model else ""
        current = f" {GREEN}⟲ 当前使用{RESET}" if provider_id == state.provider and m == state.model_name else ""
        print(f"  {CYAN}[{i}]{RESET} {m}{marker}{current}")
    print(f"  {CYAN}[c]{RESET} {DIM}自定义输入模型名{RESET}")

    try:
        m_choice = input(f"\n{YELLOW}👉 模型编号 (q/回车返回): {RESET}").strip()
    except (EOFError, KeyboardInterrupt):
        print(f"\n{DIM}已取消。{RESET}")
        return False

    if not m_choice or m_choice.lower() == "q":
        print(f"{DIM}已返回。{RESET}")
        return False

    if m_choice.lower() == "c":
        # 自定义输入模型名
        try:
            custom_model = input(f"{YELLOW}👉 输入模型名: {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{DIM}已取消。{RESET}")
            return False
        if not custom_model:
            print(f"{DIM}已取消。{RESET}")
            return False
        target_model = custom_model
    elif m_choice.isdigit():
        m_idx = int(m_choice) - 1
        if m_idx < 0 or m_idx >= len(models):
            print(f"{RED}❌ 编号超出范围，有效范围: 1-{len(models)}{RESET}")
            return False
        target_model = models[m_idx]
    else:
        print(f"{RED}❌ 无效输入{RESET}")
        return False

    # ── 应用配置 ──
    ok = state.update_model(f"{provider_id}:{target_model}")
    if ok:
        print()
        print(f"{GREEN}✅ 默认模型已设置: [{state.provider}] {state.display_model}{RESET}")
        if hasattr(state, '_prompt') and state._prompt:
            state._prompt.update_status(model=state.display_model, provider=state.display_provider)
        if not _provider_has_key(state, state.provider):
            print(f"\n{YELLOW}⚠️ [{state.provider}] 尚未配置 API Key{RESET}")
            try:
                k = input(f"👉 请输入 [{state.provider}] 的 API Key (回车跳过): ").strip()
            except (EOFError, KeyboardInterrupt):
                k = ""
            if k:
                state.update_key(k)
                print(f"{GREEN}✅ [{state.provider}] API Key 已保存{RESET}")
    else:
        print(f"{RED}❌ 设置失败: [{provider_id}] {target_model}{RESET}")
    return False