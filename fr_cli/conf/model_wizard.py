"""
模型配置向导 —— 6 步交互式配置

步骤:
  a. 选择模型供应商
  b. 选择兼容模式 (Anthropic / OpenAI)
  c. 选择该提供商可提供的模型
  d. 设置 baseUrl
  e. 设置 API Key
  f. 确认是否将这个模型设置为默认使用的模型
     → 是:设为 default_provider
     → 否:设为 backup_provider(若已有 backup 则覆盖)

兼容模式含义:
  - openai    → OpenAI 兼容协议(默认)
  - anthropic → Anthropic Messages 协议
  - zhipu     → 智谱原生 SDK(只对 zhipu/zhipu-coding 可选)

特殊模式:
  - mode="setup"   : 首次配置向导,完整 6 步
  - mode="add"     : 添加/重配一个新 provider,完整 6 步
  - mode="switch"  : 仅切换默认 provider/model,跳过 d/e(已有 key 复用)
"""
import getpass

from fr_cli.conf.config import save_config
from fr_cli.core.llm import list_providers, get_provider_info
from fr_cli.ui.ui import CYAN, RED, YELLOW, GREEN, DIM, RESET, get_display_width


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _box(title, lines, width=58):
    """打印带边框的小标题块"""
    inner = width - 2
    print()
    print(f"{CYAN}╔{'═' * width}╗{RESET}")
    title_pad = max(inner - get_display_width(title), 0)
    print(f"{CYAN}║{RESET}{title}{' ' * title_pad}{CYAN}║{RESET}")
    print(f"{CYAN}╠{'═' * width}╣{RESET}")
    for line in lines:
        text = line
        plain_w = get_display_width(text)
        pad = max(inner - plain_w, 0)
        print(f"{CYAN}║{RESET}{text}{' ' * pad}{CYAN}║{RESET}")
    print(f"{CYAN}╚{'═' * width}╝{RESET}")


def _prompt(label, default=""):
    """带默认值的输入提示"""
    if default:
        val = input(f"{CYAN}👉 {label} [{default}]: {RESET}").strip()
        return val if val else default
    return input(f"{CYAN}👉 {label}: {RESET}").strip()


def _confirm(text, default=True):
    """Y/N 确认"""
    suffix = "[Y/n]" if default else "[y/N]"
    r = input(f"{YELLOW}{text} {suffix}: {RESET}").strip().lower()
    if not r:
        return default
    return r in ("y", "yes", "是")


def _choose_from_list(prompt, items, *, allow_back=True, allow_custom=False):
    """从列表中选择一项,返回 (idx or "custom", label)

    items: list of (id, label) or list of dict{id, label}

    行为:
      - 数字 → 选中对应项
      - q     → 取消(返回 None,无论 allow_back)
      - c     → 自定义(若 allow_custom=True)
      - 空    → 取消(若 allow_back) 或 重试(否则)
    """
    while True:
        try:
            raw = input(f"{YELLOW}{prompt}: {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{DIM}已取消。{RESET}")
            return None
        # q 总是取消,无论是否 allow_back(防止死循环)
        if raw.lower() == "q":
            print(f"{DIM}已取消。{RESET}")
            return None
        if not raw:
            if allow_back:
                print(f"{DIM}已取消。{RESET}")
                return None
            print(f"{RED}❌ 请输入有效编号{RESET}")
            continue
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(items):
                return idx
            print(f"{RED}❌ 编号超出范围 (1-{len(items)}){RESET}")
            continue
        if allow_custom and raw.lower() == "c":
            return "custom"
        print(f"{RED}❌ 无效输入{RESET}")


# ---------------------------------------------------------------------------
# 6 步向导主流程
# ---------------------------------------------------------------------------

def run_model_wizard(cfg: dict, *, mode: str = "setup", preset_provider: str = None) -> dict:
    """运行模型配置向导(原地修改 cfg,完成后自动持久化)。

    Args:
        cfg: 当前配置字典(会被原地修改并保存)
        mode: setup(完整 6 步) / add(添加) / switch(只切 model)
        preset_provider: 跳过 a 步,直接锁定到指定 provider(供内部调用)

    Returns:
        更新后的 cfg(并已 save_config)
    """
    providers = list_providers()
    if not providers:
        print(f"{RED}❌ 没有可用的模型提供商,请检查 default_models.yaml{RESET}")
        return cfg

    # =================================================================
    # a. 选择供应商
    # =================================================================
    if preset_provider:
        provider_id = preset_provider
        info = get_provider_info(provider_id)
        if not info:
            print(f"{RED}❌ 无效的 provider: {provider_id}{RESET}")
            return cfg
        print(f"\n{CYAN}当前供应商: {info['name']} ({provider_id}){RESET}")
    else:
        _box(
            "步骤 a/6  ·  选择模型供应商",
            [
                f"{DIM}输入编号选择,或按 q 取消{RESET}",
                "",
            ],
        )
        # 列出来源:已配置的优先
        providers_cfg = cfg.setdefault("providers", {})
        for i, p in enumerate(providers, 1):
            info = get_provider_info(p["id"])
            default_model = info.get("default_model", "?") if info else "?"
            marker = f"{GREEN}✓{RESET}" if p["id"] in providers_cfg else f"{DIM}·{RESET}"
            compat = info.get("compat", "?") if info else "?"
            print(f"  {marker} [{CYAN}{i:>2}{RESET}] {p['id']:<22} {DIM}{p['name']:<14} 默认:{default_model:<24} compat:{compat}{RESET}")

        idx = _choose_from_list("👉 供应商编号", providers, allow_back=False)
        if idx is None:
            print(f"{DIM}已取消。{RESET}")
            return cfg
        provider_id = providers[idx]["id"]
        info = get_provider_info(provider_id)

    # =================================================================
    # b. 选择兼容模式 (Anthropic / OpenAI)
    # =================================================================
    default_compat = (info or {}).get("compat", "openai")

    # 直接通过 compat 字段判断 zhipu 原生客户端(避免运行时还没 import 客户端类)
    if default_compat == "zhipu":
        compat = "zhipu"
        print(f"\n{DIM}步骤 b: 供应商 {provider_id} 使用原生 SDK ({default_compat}),跳过兼容模式选择{RESET}")
    else:
        _box(
            "步骤 b/6  ·  选择兼容模式",
            [
                f"{DIM}fr-cli 支持 OpenAI / Anthropic 两种主流协议{RESET}",
                f"{DIM}多数厂商走 OpenAI 兼容(默认);部分厂商走 Anthropic 协议{RESET}",
                "",
            ],
        )
        print(f"  [{CYAN}1{RESET}] {GREEN}OpenAI 兼容{RESET}    {DIM}(推荐,适用于大多数厂商){RESET}")
        print(f"  [{CYAN}2{RESET}] {GREEN}Anthropic{RESET}      {DIM}(Claude/Kimi Anthropic 兼容端点){RESET}")
        print(f"  [{CYAN}q{RESET}] {DIM}取消{RESET}")
        # 默认值提示
        default_choice = "1" if default_compat == "openai" else "2"
        try:
            raw = input(f"{YELLOW}👉 选择 [1/2] (默认 {default_choice}): {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{DIM}已取消。{RESET}")
            return cfg
        if raw.lower() == "q":
            print(f"{DIM}已取消。{RESET}")
            return cfg
        if raw == "2":
            compat = "anthropic"
        elif raw == "" or raw == "1":
            compat = "openai"
        else:
            print(f"{RED}❌ 无效输入,使用默认 OpenAI 兼容{RESET}")
            compat = "openai"

    # =================================================================
    # c. 选择模型
    # =================================================================
    models = (info or {}).get("models") or [(info or {}).get("default_model")]
    models = [m for m in models if m]
    default_model = (info or {}).get("default_model") or (models[0] if models else "")

    _box(
        "步骤 c/6  ·  选择模型",
        [
            f"{DIM}输入编号选择,可输入 c 自定义模型名{RESET}",
            "",
        ],
    )
    if models:
        for i, m in enumerate(models, 1):
            marker = f" {YELLOW}★ 默认{RESET}" if m == default_model else ""
            print(f"  [{CYAN}{i:>2}{RESET}] {m}{marker}")
    print(f"  [{CYAN} c{RESET}] {DIM}自定义输入模型名{RESET}")

    idx = _choose_from_list("👉 模型编号", models, allow_back=False, allow_custom=True)
    if idx is None:
        print(f"{DIM}已取消。{RESET}")
        return cfg
    if idx == "custom":
        target_model = _prompt("输入模型名", default_model)
        if not target_model:
            target_model = default_model
    else:
        target_model = models[idx]

    # =================================================================
    # d. 设置 baseUrl
    # =================================================================
    print()
    print(f"{CYAN}步骤 d/6  ·  设置 baseUrl{RESET}")
    providers_cfg = cfg.setdefault("providers", {})
    pcfg = providers_cfg.setdefault(provider_id, {})
    default_base_url = pcfg.get("base_url") or (info or {}).get("base_url") or ""
    if default_base_url:
        print(f"{DIM}  当前默认值: {default_base_url}{RESET}")
    raw = _prompt("baseUrl(回车使用默认,输入 none 表示空)", default_base_url)
    base_url = "" if raw.lower() in ("none", "空") else raw

    # =================================================================
    # e. 设置 API Key
    # =================================================================
    print()
    print(f"{CYAN}步骤 e/6  ·  设置 API Key{RESET}")
    env_key_name = (info or {}).get("env_key", "")
    if env_key_name:
        print(f"{DIM}  提示: 可通过环境变量 {env_key_name} 传入{RESET}")
    existing_key = pcfg.get("key") or cfg.get("key", "")
    if existing_key:
        masked = existing_key[:4] + "****" + existing_key[-4:] if len(existing_key) > 8 else "****"
        print(f"{DIM}  已有 key: {masked}(回车保留,或粘贴新 key){RESET}")
        try:
            raw = input(f"{CYAN}👉 API Key(回车保留): {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{DIM}已取消。{RESET}")
            return cfg
        if raw:
            api_key = raw
        else:
            api_key = existing_key
    else:
        try:
            api_key = getpass.getpass(f"{CYAN}👉 API Key(隐藏显示): {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{DIM}已取消。{RESET}")
            return cfg
        if not api_key and env_key_name:
            # 尝试从环境变量读取
            import os
            api_key = os.environ.get(env_key_name, "")
            if api_key:
                print(f"{GREEN}✅ 已从环境变量 {env_key_name} 读取{RESET}")
    if not api_key:
        print(f"{RED}❌ API Key 不能为空{RESET}")
        return cfg

    # =================================================================
    # f. 确认是否设为默认模型
    # =================================================================
    print()
    print(f"{CYAN}步骤 f/6  ·  设置 default / backup{RESET}")
    existing_default = cfg.get("default_provider", "")
    existing_backup = cfg.get("backup_provider", "")
    print(f"{DIM}  当前 default: {existing_default or '(未设置)'}{RESET}")
    print(f"{DIM}  当前 backup:  {existing_backup or '(未设置)'}{RESET}")

    # 应用配置
    pcfg["key"] = api_key
    pcfg["model"] = target_model
    pcfg["compat"] = compat  # 记录用户选择的 compat(便于排查)
    if base_url:
        pcfg["base_url"] = base_url
    elif "base_url" in pcfg:
        # 用户输入 none → 清空,使用 provider 默认
        del pcfg["base_url"]

    cfg["providers"] = providers_cfg

    if mode == "switch":
        # switch 模式只切当前 model 不重写 default
        cfg["provider"] = provider_id
        cfg["model"] = target_model
    else:
        # setup / add:询问用户
        if not existing_default:
            # 首次配置:必须设为 default
            cfg["default_provider"] = provider_id
            cfg["provider"] = provider_id
            cfg["model"] = target_model
            print(f"{GREEN}✅ 已设为默认模型: [{provider_id}] {target_model}{RESET}")
        else:
            # 已有 default,询问是否覆盖
            print()
            print(f"  [{CYAN}1{RESET}] 设为 {GREEN}default{RESET}(覆盖当前 default={existing_default})")
            print(f"  [{CYAN}2{RESET}] 设为 {GREEN}backup{RESET}(覆盖当前 backup={existing_backup or '(空)'})")
            print(f"  [{CYAN}3{RESET}] {DIM}仅保存配置,不修改 default/backup{RESET}")
            try:
                pick = input(f"{YELLOW}👉 选择 [1/2/3] (默认 2): {RESET}").strip()
            except (EOFError, KeyboardInterrupt):
                pick = "2"
            if pick == "1":
                cfg["default_provider"] = provider_id
                cfg["provider"] = provider_id
                cfg["model"] = target_model
                print(f"{GREEN}✅ 已设为默认模型: [{provider_id}] {target_model}{RESET}")
            elif pick == "3":
                print(f"{DIM}已保存配置,不修改 default/backup{RESET}")
            else:
                cfg["backup_provider"] = provider_id
                print(f"{GREEN}✅ 已设为备用模型: [{provider_id}] {target_model}{RESET}")

    # 标记向导已通过(避免下次启动再次提示)
    cfg["model_wizard_skipped"] = True

    # 持久化
    if save_config(cfg):
        print(f"\n{GREEN}✅ 配置已保存{RESET}")
    else:
        print(f"\n{RED}❌ 配置保存失败,请检查 ~/.fr_cli/config.json 权限{RESET}")

    return cfg
