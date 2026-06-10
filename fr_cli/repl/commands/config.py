"""
REPL 命令路由处理器
从 main.py 提取的所有 / 命令实现，减轻主模块负担。
"""
import sys

from fr_cli.lang.i18n import T
from fr_cli.ui.ui import (
    CYAN, RED, YELLOW, GREEN, DIM, RESET,
    print_bye
)
from fr_cli.agent.shell_mode import ShellMode
from fr_cli.memory.history import save_sess, load_sess, del_sess, get_sessions
from fr_cli.memory.context import load_context, extract_recent_turns, build_context_summary, save_context
from fr_cli.memory.session import (
    list_sessions as list_auto_sessions,
    load_session as load_auto_session,
    delete_session as delete_auto_session,
)
from fr_cli.addon.plugin import extract_code
from fr_cli.core.stream import stream_cnt
from fr_cli.core.sysmon import get_sys_stats
from fr_cli.agent.manager import (
    create_agent_dir, save_agent_code, save_persona, save_skills,
    save_memory, agent_exists, list_agents, delete_agent,
    load_persona, load_memory, load_skills,
)
from fr_cli.agent.executor import run_agent
from fr_cli.repl.commands._common import _provider_has_key



def _cmd_model(state, parts):
    """模型切换命令

    子命令风格（专业 CLI 格式）:
      /model              — 交互式选择
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
        print(f"{CYAN}当前模型: [{state.provider}] {state.model_name}{RESET}")
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
        name = info.get("name", state.provider) if info else state.provider
        print(f"{CYAN}当前模型:{RESET}")
        print(f"  提供商: {CYAN}{state.provider}{RESET} — {name}")
        print(f"  模型:   {CYAN}{state.model_name}{RESET}")
        print(f"  Key:    {GREEN}已配置{RESET}" if _provider_has_key(state, state.provider) else f"  Key:    {RED}未配置{RESET}")
        return False

    if arg1 in ("default", "reset"):
        info = get_provider_info(state.provider)
        default_model = info.get("default_model", "glm-4-flash") if info else "glm-4-flash"
        ok = state.update_model(default_model)
        if ok:
            print(f"{GREEN}已恢复默认: [{state.provider}] {state.model_name}{RESET}")
            if hasattr(state, '_prompt') and state._prompt:
                state._prompt.update_status(model=state.model_name, provider=state.provider)
        else:
            print(f"{RED}恢复默认失败{RESET}")
        return False

    if arg1 in ("set", "use", "switch"):
        arg2 = parts[2] if len(parts) > 2 else ""
        if not arg2:
            print(f"{YELLOW}用法: /model set <编号|模型名|提供商:模型>{RESET}")
            return False
        arg1 = arg2

    # ---------- 交互式选择（无参数）----------
    if not arg1:
        print(f"{CYAN}当前模型: [{state.provider}] {state.model_name}{RESET}")
        print(f"\n{DIM}可用模型列表（输入编号或名称切换）:{RESET}")

        for i, p in enumerate(providers, 1):
            marker = " [当前]" if p["id"] == state.provider else ""
            has_key = _provider_has_key(state, p["id"])
            key_status = f"{GREEN}[已配置]{RESET}" if has_key else f"{RED}[未配置]{RESET}"
            print(f"  {CYAN}[{i}]{RESET} {p['id']}{DIM}/{p['default_model']}{RESET} — {p['name']} {key_status}{marker}")

        print(f"\n{DIM}子命令:{RESET}")
        print(f"  /model list         — 列出所有模型")
        print(f"  /model current      — 显示当前模型")
        print(f"  /model default      — 恢复默认模型")
        print(f"  /model set <arg>    — 设置模型")
        print(f"\n{DIM}快速切换:{RESET}")
        print(f"  /model <编号>       — 按编号切换")
        print(f"  /model <模型名>     — 切换模型")
        print(f"  /model <提供商>:<模型> — 同时切换提供商")

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
        print(f"{GREEN}已切换: [{state.provider}] {state.model_name}{RESET}")
        if hasattr(state, '_prompt') and state._prompt:
            state._prompt.update_status(model=state.model_name, provider=state.provider)
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
        print(f"  /key <提供商> <API密钥>       — 为指定提供商设置密钥")
    return False



def _cmd_providers(state, parts):
    """
    多模型提供商配置管理
    用法:
      /providers                  — 查看所有提供商配置
      /providers setup            — 交互式配置向导
      /providers add <提供商> <key> [模型] — 添加/更新提供商配置
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
            active = f" {YELLOW}👈 当前使用{RESET}" if p["id"] == state.provider else ""
            print(f"\n  {key_status} {CYAN}{p['id']}{RESET} — {p['name']}{active}")
            print(f"      模型: {DIM}{model}{RESET}")
            print(f"      接口: {DIM}{base_url}{RESET}")
            if has_key:
                raw_key = pcfg.get("key", state.cfg.get("key", ""))
                key_display = raw_key[:8] + "****" if len(raw_key) > 8 else raw_key
                print(f"      Key:  {DIM}{key_display}{RESET}")
        print(f"\n{DIM}用法:{RESET}")
        print(f"  /providers setup                   — 交互式配置向导（推荐新手）")
        print(f"  /providers add <提供商> <key> [模型] — 添加/更新提供商配置")
        print(f"  /providers del <提供商>              — 删除提供商配置")
        print(f"  /providers use <提供商>              — 切换到指定提供商")
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
            print(f"{RED}❌ 用法: /providers add <提供商> <key> [模型]{RESET}")
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
        for i, token in enumerate(parts):
            if token in ("--base-url", "--base_url") and i + 1 < len(parts):
                pcfg["base_url"] = parts[i + 1]
                break
        state.cfg["providers"] = providers_cfg
        state.save_cfg()
        extra = f" 自定义接口={pcfg.get('base_url')}" if pcfg.get("base_url") else ""
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
            print(f"{GREEN}✅ 已切换到: [{state.provider}] {state.model_name}{RESET}")
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


