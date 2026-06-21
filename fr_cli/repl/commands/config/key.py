"""
REPL /key 与 /providers 命令 —— API Key 与多提供商管理
"""
from fr_cli.ui.ui import CYAN, RED, YELLOW, GREEN, DIM, RESET
from fr_cli.repl.commands._common import _provider_has_key


def _cmd_key(state, parts):
    """
    设置 API Key
    用法:
      /key <key>              — 为当前提供商设置 key
      /key <提供商> <key>       — 为指定提供商设置 key
    """
    arg1 = parts[1] if len(parts) > 1 else ""
    arg2 = parts[2] if len(parts) > 2 else ""
    if arg1 and arg2:
        # /key <provider> <key>
        target_provider = arg1
        from fr_cli.core.llm import get_provider_info
        if not get_provider_info(target_provider):
            print(f"{RED}❌ 无效提供商: {target_provider}{RESET}")
            return False
        # 临时切到目标提供商设置 key，再切回来
        original_provider = state.provider
        state.update_provider(target_provider)
        state.update_key(arg2)
        # 如果原来不是目标提供商，切回去
        if original_provider != target_provider:
            state.update_provider(original_provider)
        print(f"{GREEN}✅ [{target_provider}] API Key 已更新{RESET}")
    elif arg1:
        # /key <key>
        state.update_key(arg1)
        print(f"{GREEN}✅ [{state.provider}] API Key 已更新{RESET}")
    else:
        print(f"{YELLOW}⚠️ 用法:{RESET}")
        print(f"  /key <API密钥>              — 为当前提供商 [{state.provider}] 设置密钥")
        print("  /key <提供商> <API密钥>       — 为指定提供商设置密钥")
    return False


def _cmd_providers(state, parts):
    """
    多模型提供商配置管理
    用法:
      /providers                  — 查看所有提供商配置
      /providers setup            — 交互式配置向导
      /providers add <提供商> <key> [模型] [--base-url <url>] [--token-plan-base-url <url>] — 添加/更新提供商配置
      /providers del <提供商>       — 删除提供商配置
      /providers use <提供商>       — 切换到指定提供商
    """
    sub = parts[1] if len(parts) > 1 else ""
    arg1 = parts[2] if len(parts) > 2 else ""
    arg2 = parts[3] if len(parts) > 3 else ""

    providers_cfg = state.cfg.setdefault("providers", {})

    if not sub or sub == "list":
        from fr_cli.core.llm import list_providers, get_provider_info
        print(f"{CYAN}📜 提供商配置总览{RESET}")
        for p in list_providers():
            pcfg = providers_cfg.get(p["id"], {})
            has_key = _provider_has_key(state, p["id"])
            key_status = f"{GREEN}✅{RESET}" if has_key else f"{RED}❌{RESET}"
            model = pcfg.get("model", p["default_model"])
            info = get_provider_info(p["id"])
            base_url = pcfg.get("base_url") or info.get("base_url", "默认")
            token_plan_url = pcfg.get("token_plan_base_url") or info.get("token_plan_base_url")
            active = f" {YELLOW}👈 当前使用{RESET}" if p["id"] == state.provider else ""
            print(f"\n  {key_status} {CYAN}{p['id']}{RESET} — {p['name']}{active}")
            print(f"      模型: {DIM}{model}{RESET}")
            print(f"      接口: {DIM}{base_url}{RESET}")
            if token_plan_url:
                print(f"      Token Plan 接口: {DIM}{token_plan_url}{RESET}")
            if has_key:
                raw_key = pcfg.get("key", state.cfg.get("key", ""))
                key_display = raw_key[:8] + "****" if len(raw_key) > 8 else raw_key
                print(f"      Key:  {DIM}{key_display}{RESET}")
        print(f"\n{DIM}用法:{RESET}")
        print("  /providers setup                   — 交互式配置向导（推荐新手）")
        print("  /providers add <提供商> <key> [模型] [--base-url <url>] [--token-plan-base-url <url>] — 添加/更新提供商配置")
        print("  /providers del <提供商>              — 删除提供商配置")
        print("  /providers use <提供商>              — 切换到指定提供商")
        return False

    if sub == "setup":
        # 交互式配置向导
        from fr_cli.core.llm import list_providers, get_provider_info
        providers = list_providers()
        print(f"{CYAN}🧙 大模型配置向导{RESET}")
        print(f"{DIM}请选择要配置的提供商（输入编号）:{RESET}")
        for i, p in enumerate(providers, 1):
            print(f"  [{i}] {CYAN}{p['id']}{RESET} — {p['name']} {DIM}(默认模型: {p['default_model']}){RESET}")
        choice = input(f"{YELLOW}👉 编号 (回车取消): {RESET}").strip()
        if not choice or not choice.isdigit():
            print(f"{DIM}已取消。{RESET}")
            return False
        idx = int(choice) - 1
        if idx < 0 or idx >= len(providers):
            print(f"{RED}❌ 无效编号{RESET}")
            return False
        selected = providers[idx]
        provider_id = selected["id"]
        info = get_provider_info(provider_id)

        # 输入 API Key
        print(f"\n{DIM}正在配置 [{provider_id}]{RESET}")
        k = input(f"{YELLOW}👉 请输入 API Key: {RESET}").strip()
        if not k:
            print(f"{RED}❌ API Key 不能为空{RESET}")
            return False

        # 选择模型
        default_model = info["default_model"]
        print(f"\n{DIM}默认模型: {default_model}{RESET}")
        m = input(f"{YELLOW}👉 模型名 (回车使用默认): {RESET}").strip()
        model = m if m else default_model

        # 保存配置
        pcfg = providers_cfg.setdefault(provider_id, {})
        pcfg["key"] = k
        pcfg["model"] = model
        state.cfg["providers"] = providers_cfg

        # 询问是否设为全局默认
        is_default = input(f"\n{YELLOW}👉 是否设为全局默认? [Y/n]: {RESET}").strip().lower()
        if is_default in ("", "y", "yes"):
            state.cfg["provider"] = provider_id
            state.cfg["model"] = model
            state.provider = provider_id
            state.model_name = model

        state.save_cfg()
        state.reinit_client()
        print(f"\n{GREEN}✅ [{provider_id}] 配置完成！{RESET}")
        print(f"   模型: {DIM}{model}{RESET}")
        if state.provider == provider_id:
            print(f"   {YELLOW}⭐ 已设为全局默认{RESET}")
        return False

    if sub == "add":
        if not arg1 or not arg2:
            print(f"{RED}❌ 用法: /providers add <提供商> <key> [模型] [--base-url <url>] [--token-plan-base-url <url>]{RESET}")
            return False
        provider_id = arg1
        from fr_cli.core.llm import get_provider_info
        info = get_provider_info(provider_id)
        if not info:
            print(f"{RED}❌ 无效提供商: {provider_id}{RESET}")
            return False
        pcfg = providers_cfg.setdefault(provider_id, {})
        pcfg["key"] = arg2
        model = parts[4] if len(parts) > 4 else info["default_model"]
        pcfg["model"] = model
        # 支持自定义 base_url: /providers add <provider> <key> [model] --base-url <url>
        # 支持自定义 token_plan_base_url: --token-plan-base-url <url>
        for i, token in enumerate(parts):
            if token in ("--base-url", "--base_url") and i + 1 < len(parts):
                pcfg["base_url"] = parts[i + 1]
            if token in ("--token-plan-base-url", "--token_plan_base_url") and i + 1 < len(parts):
                pcfg["token_plan_base_url"] = parts[i + 1]
        state.cfg["providers"] = providers_cfg
        state.save_cfg()
        extra_parts = []
        if pcfg.get("base_url"):
            extra_parts.append(f"自定义接口={pcfg.get('base_url')}")
        if pcfg.get("token_plan_base_url"):
            extra_parts.append(f"Token Plan 接口={pcfg.get('token_plan_base_url')}")
        extra = " ".join(extra_parts)
        extra = f" {extra}" if extra else ""
        print(f"{GREEN}✅ [{provider_id}] 配置已更新: 模型={model}{extra}{RESET}")
        return False

    if sub == "del":
        if not arg1:
            print(f"{RED}❌ 用法: /providers del <提供商>{RESET}")
            return False
        if arg1 in providers_cfg:
            del providers_cfg[arg1]
            state.cfg["providers"] = providers_cfg
            state.save_cfg()
            print(f"{GREEN}✅ [{arg1}] 配置已删除{RESET}")
        else:
            print(f"{YELLOW}⚠️ [{arg1}] 无配置可删除{RESET}")
        return False

    if sub == "use":
        if not arg1:
            print(f"{RED}❌ 用法: /providers use <提供商>{RESET}")
            return False
        ok = state.update_provider(arg1)
        if ok:
            print(f"{GREEN}✅ 已切换到: [{state.provider}] {state.display_model}{RESET}")
            # 检查新提供商是否已配置 API Key
            if not _provider_has_key(state, state.provider):
                print(f"{YELLOW}⚠️ [{state.provider}] 尚未配置 API Key{RESET}")
                k = input(f"👉 请输入 [{state.provider}] 的 API Key: ").strip()
                if k:
                    state.update_key(k)
                    print(f"{GREEN}✅ [{state.provider}] API Key 已保存{RESET}")
        else:
            print(f"{RED}❌ 无效提供商: {arg1}{RESET}")
        return False

    print(f"{RED}❌ 未知子命令: {sub}{RESET}")
    return False