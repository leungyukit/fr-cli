"""
REPL /key 与 /providers 命令 —— API Key 与多提供商管理
"""
from fr_cli.ui.output import success, failure, warning, info, header
from fr_cli.ui.ui import CYAN, YELLOW, DIM, RESET
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
            failure(f"无效提供商: {target_provider}")
            return False
        # 临时切到目标提供商设置 key，再切回来
        original_provider = state.provider
        state.update_provider(target_provider)
        state.update_key(arg2)
        # 如果原来不是目标提供商，切回去
        if original_provider != target_provider:
            state.update_provider(original_provider)
        success(f"[{target_provider}] API Key 已更新")
    elif arg1:
        # /key <key>
        state.update_key(arg1)
        success(f"[{state.provider}] API Key 已更新")
    else:
        warning("用法")
        info("/key <API密钥>              — 为当前提供商 [{state.provider}] 设置密钥")
        info("/key <提供商> <API密钥>       — 为指定提供商设置密钥")
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
        header("提供商配置总览")
        for p in list_providers():
            pcfg = providers_cfg.get(p["id"], {})
            has_key = _provider_has_key(state, p["id"])
            key_status = "✅" if has_key else "❌"
            model = pcfg.get("model", p["default_model"])
            pinfo = get_provider_info(p["id"])
            base_url = pcfg.get("base_url") or pinfo.get("base_url", "默认")
            token_plan_url = pcfg.get("token_plan_base_url") or pinfo.get("token_plan_base_url")
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
        print()
        info("用法:")
        info("/providers setup                   — 交互式配置向导（推荐新手）")
        info("/providers add <提供商> <key> [模型] [--base-url <url>] [--token-plan-base-url <url>] — 添加/更新提供商配置")
        info("/providers del <提供商>              — 删除提供商配置")
        info("/providers use <提供商>              — 切换到指定提供商")
        return False

    if sub == "setup":
        # 启动 6 步模型配置向导
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

    if sub == "add":
        if not arg1 or not arg2:
            failure("用法: /providers add <提供商> <key> [模型] [--base-url <url>] [--token-plan-base-url <url>]")
            return False
        provider_id = arg1
        from fr_cli.core.llm import get_provider_info
        pinfo = get_provider_info(provider_id)
        if not pinfo:
            failure(f"无效提供商: {provider_id}")
            return False
        pcfg = providers_cfg.setdefault(provider_id, {})
        pcfg["key"] = arg2
        model = parts[4] if len(parts) > 4 else pinfo["default_model"]
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
        success(f"[{provider_id}] 配置已更新: 模型={model}{extra}")
        return False

    if sub == "del":
        if not arg1:
            failure("用法: /providers del <提供商>")
            return False
        if arg1 in providers_cfg:
            del providers_cfg[arg1]
            state.cfg["providers"] = providers_cfg
            state.save_cfg()
            success(f"[{arg1}] 配置已删除")
        else:
            warning(f"[{arg1}] 无配置可删除")
        return False

    if sub == "use":
        if not arg1:
            failure("用法: /providers use <提供商>")
            return False
        ok = state.update_provider(arg1)
        if ok:
            success(f"已切换到: [{state.provider}] {state.display_model}")
            # 检查新提供商是否已配置 API Key
            if not _provider_has_key(state, state.provider):
                warning(f"[{state.provider}] 尚未配置 API Key")
                k = input(f"👉 请输入 [{state.provider}] 的 API Key: ").strip()
                if k:
                    state.update_key(k)
                    success(f"[{state.provider}] API Key 已保存")
        else:
            failure(f"无效提供商: {arg1}")
        return False

    failure(f"未知子命令: {sub}")
    return False
