"""
OCR 配置命令
/ocr_config
"""
from fr_cli.ui.ui import CYAN, GREEN, RED, YELLOW, RESET, DIM
from fr_cli.weapon.ocr import get_ocr_config


def _cmd_ocr_config(state, parts):
    """
    OCR 模型配置管理

    用法:
      /ocr_config                       — 查看当前 OCR 配置
      /ocr_config setup                 — 交互式配置向导
      /ocr_config engine <vision|paddle> — 切换识别引擎（vision=多模态API，paddle=本地PaddleOCR）
      /ocr_config provider <厂商>        — 设置复用的全局厂商（如 zhipu / deepseek / kimi）
      /ocr_config model <模型名>         — 设置 OCR 模型（如 glm-4v）
      /ocr_config key <key>             — 设置专属 API Key（可选）
      /ocr_config base_url <url>        — 设置自定义接口地址
      /ocr_config prompt <prompt>       — 设置默认 OCR 提示词
      /ocr_config clear                 — 清空 OCR 配置
    """
    sub = parts[1] if len(parts) > 1 else ""
    arg = parts[2] if len(parts) > 2 else ""

    cfg = state.cfg.setdefault("ocr", {})

    if not sub or sub == "show":
        ocr_cfg = get_ocr_config(state.cfg)
        print(f"{CYAN}📝 当前 OCR 配置{RESET}")
        print(f"  引擎:     {DIM}{ocr_cfg.get('engine') or 'vision'}{RESET}")
        print(f"  厂商:     {DIM}{ocr_cfg.get('provider') or '(未设置)'}{RESET}")
        print(f"  模型:     {DIM}{ocr_cfg.get('model') or '(未设置)'}{RESET}")
        key = ocr_cfg.get("key", "")
        print(f"  Key:      {DIM}{key[:8] + '****' if len(key) > 8 else (key or '(未设置/使用全局)')}{RESET}")
        print(f"  Base URL: {DIM}{ocr_cfg.get('base_url') or '(未设置)'}{RESET}")
        prompt = ocr_cfg.get("prompt", "")
        print(f"  Prompt:   {DIM}{prompt or '(默认)'}{RESET}")
        print(f"\n{DIM}用法:{RESET}")
        print("  /ocr_config setup                 — 交互式配置向导")
        print("  /ocr_config engine vision|paddle  — 切换识别引擎")
        print("  /ocr_config provider zhipu        — 复用全局 zhipu 配置")
        print("  /ocr_config model glm-4v          — 设置 OCR 模型")
        print("  /ocr_config key sk-xxx            — 设置专属 Key（可选）")
        print("  /ocr_config base_url <url>        — 设置自定义接口")
        print("  /ocr_config prompt <prompt>       — 设置默认提示词")
        return False

    if sub == "setup":
        return _cmd_ocr_config_setup(state)

    if sub == "clear":
        state.cfg["ocr"] = {}
        state.save_cfg()
        print(f"{GREEN}✅ OCR 配置已清空{RESET}")
        return False

    # 单字段设置
    simple_fields = {
        "provider": "厂商",
        "model": "模型",
        "key": "API Key",
        "base_url": "Base URL",
        "prompt": "提示词",
    }
    if sub == "engine":
        if arg not in ("vision", "paddle"):
            print(f"{RED}❌ 用法: /ocr_config engine <vision|paddle>{RESET}")
            return False
        cfg["engine"] = arg
        state.cfg["ocr"] = cfg
        state.save_cfg()
        desc = "多模态 Vision API" if arg == "vision" else "本地 PaddleOCR 引擎"
        print(f"{GREEN}✅ OCR 引擎已切换: {desc}{RESET}")
        return False
    if sub in simple_fields:
        if not arg:
            print(f"{RED}❌ 用法: /ocr_config {sub} <值>{RESET}")
            return False
        value = " ".join(parts[2:]) if sub == "prompt" else arg
        cfg[sub] = value
        state.cfg["ocr"] = cfg
        state.save_cfg()
        print(f"{GREEN}✅ OCR {simple_fields[sub]} 已更新{RESET}")
        return False

    print(f"{RED}❌ 未知子命令: {sub}{RESET}")
    return False


def _cmd_ocr_config_setup(state):
    """交互式 OCR 配置向导"""
    from fr_cli.core.llm import list_providers, get_provider_info

    providers = list_providers()
    cfg = state.cfg.setdefault("ocr", {})

    print(f"{CYAN}╔{'═' * 50}╗{RESET}")
    print(f"{CYAN}║{'📝  OCR 配置向导':^48}║{RESET}")
    print(f"{CYAN}╚{'═' * 50}╝{RESET}")

    # 第一步：选择识别引擎
    print(f"\n{DIM}第一步：选择识别引擎{RESET}")
    print(f"  {CYAN}[1]{RESET} vision — 多模态 Vision API（需配置模型与 Key）")
    print(f"  {CYAN}[2]{RESET} paddle — 本地 PaddleOCR 引擎（离线识别，需安装 paddleocr）")
    try:
        engine_choice = input(f"\n{YELLOW}👉 引擎编号 [1]: {RESET}").strip()
    except (EOFError, KeyboardInterrupt):
        print(f"\n{DIM}已取消。{RESET}")
        return False
    engine = "paddle" if engine_choice == "2" else "vision"

    # 若选择 PaddleOCR，直接保存并结束
    if engine == "paddle":
        cfg.update({
            "engine": "paddle",
            "provider": "",
            "model": "",
            "key": "",
            "base_url": "",
            "prompt": "",
        })
        state.cfg["ocr"] = cfg
        state.save_cfg()
        print(f"\n{GREEN}✅ OCR 配置完成！{RESET}")
        print(f"  引擎: {DIM}本地 PaddleOCR{RESET}")
        print(f"\n{DIM}现在可以使用：/ocr <图片或PDF路径>{RESET}")
        return False

    # 第二步：选择是否复用全局厂商
    print(f"\n{DIM}第二步：选择要复用的全局厂商（可选）{RESET}")
    print(f"{DIM}若选择厂商，将自动复用其 API Key 与 Base URL；输入 0 表示自定义。{RESET}\n")
    print(f"  {CYAN}[0]{RESET} 自定义接口")
    for i, p in enumerate(providers, 1):
        marker = f" {YELLOW}👈 当前{RESET}" if p["id"] == state.provider else ""
        print(f"  {CYAN}[{i}]{RESET} {p['id']} — {p['name']}{marker}")

    try:
        choice = input(f"\n{YELLOW}👉 厂商编号 (回车跳过): {RESET}").strip()
    except (EOFError, KeyboardInterrupt):
        print(f"\n{DIM}已取消。{RESET}")
        return False

    provider = ""
    if choice:
        if choice.isdigit():
            idx = int(choice)
            if idx == 0:
                provider = ""
            elif 1 <= idx <= len(providers):
                provider = providers[idx - 1]["id"]
            else:
                print(f"{RED}❌ 编号超出范围{RESET}")
                return False
        else:
            print(f"{RED}❌ 请输入有效编号{RESET}")
            return False

    # 第三步：输入模型名
    print(f"\n{DIM}第三步：输入 OCR Vision 模型名{RESET}")
    default_model = ""
    if provider:
        info = get_provider_info(provider)
        default_model = info.get("default_model", "") if info else ""
    hint = f" (如 {default_model})" if default_model else " (如 glm-4v / deepseek-vl)"
    try:
        model = input(f"{YELLOW}👉 模型名{hint}: {RESET}").strip()
    except (EOFError, KeyboardInterrupt):
        print(f"\n{DIM}已取消。{RESET}")
        return False
    if not model:
        print(f"{RED}❌ 模型名不能为空{RESET}")
        return False

    # 第四步：是否覆盖 Key / Base URL
    key = ""
    base_url = ""
    if not provider:
        print(f"\n{DIM}第四步：自定义接口需要 API Key 与 Base URL{RESET}")
        try:
            key = input(f"{YELLOW}👉 API Key: {RESET}").strip()
            base_url = input(f"{YELLOW}👉 Base URL (可选): {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{DIM}已取消。{RESET}")
            return False
        if not key:
            print(f"{RED}❌ 自定义接口必须提供 API Key{RESET}")
            return False
    else:
        try:
            override = input(f"\n{YELLOW}👉 是否设置专属 Key 覆盖全局配置? [y/N]: {RESET}").strip().lower()
            if override in ("y", "yes"):
                key = input(f"{YELLOW}👉 专属 API Key: {RESET}").strip()
            custom_url = input(f"{YELLOW}👉 是否设置自定义 Base URL? [y/N]: {RESET}").strip().lower()
            if custom_url in ("y", "yes"):
                base_url = input(f"{YELLOW}👉 Base URL: {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{DIM}已取消。{RESET}")
            return False

    # 第五步：自定义提示词
    try:
        prompt = input(f"\n{YELLOW}👉 OCR 提示词 (回车使用默认): {RESET}").strip()
    except (EOFError, KeyboardInterrupt):
        prompt = ""

    cfg.update({
        "engine": engine,
        "provider": provider,
        "model": model,
        "key": key,
        "base_url": base_url,
        "prompt": prompt,
    })
    state.cfg["ocr"] = cfg
    state.save_cfg()

    print(f"\n{GREEN}✅ OCR 配置完成！{RESET}")
    print(f"  引擎: {DIM}{'本地 PaddleOCR' if engine == 'paddle' else '多模态 Vision API'}{RESET}")
    print(f"  厂商: {DIM}{provider or '自定义'}{RESET}")
    print(f"  模型: {DIM}{model}{RESET}")
    print(f"\n{DIM}现在可以使用：/ocr <图片或PDF路径>{RESET}")
    return False
