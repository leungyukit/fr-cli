"""
股票/量化配置命令
/stock_config
"""
from fr_cli.ui.ui import CYAN, GREEN, RED, YELLOW, DIM, RESET
from fr_cli.agent.builtins.stock import (
    _load_stock_cfg,
    _save_stock_cfg,
    _print_config,
)


def _cmd_stock_config(state, parts):
    """
    股票/量化配置管理

    用法:
      /stock_config              — 查看当前配置
      /stock_config setup        — 交互式配置向导
      /stock_config source <源>  — 切换默认数据源
      /stock_config key <源> <值> — 设置 API Key / Token
      /stock_config clear        — 清空配置
    """
    sub = parts[1] if len(parts) > 1 else ""
    arg1 = parts[2] if len(parts) > 2 else ""
    arg2 = parts[3] if len(parts) > 3 else ""

    cfg = _load_stock_cfg()

    if not sub or sub == "show":
        _print_config(cfg)
        print(f"\n{DIM}用法:{RESET}")
        print("  /stock_config setup")
        print("  /stock_config source akshare|mairui|tushare|trade")
        print("  /stock_config key mairui <key>")
        print("  /stock_config token tushare <token>")
        print("  /stock_config clear")
        return False

    if sub == "setup":
        return _cmd_stock_setup(state, parts)

    if sub == "clear":
        _save_stock_cfg({})
        print(f"{GREEN}✅ 股票配置已清空{RESET}")
        return False

    if sub == "source" and arg1:
        if arg1 not in ("akshare", "mairui", "tushare", "trade"):
            print(f"{RED}❌ 不支持的数据源: {arg1}{RESET}")
            return False
        cfg["default_source"] = arg1
        _save_stock_cfg(cfg)
        print(f"{GREEN}✅ 默认数据源已切换为: {arg1}{RESET}")
        return False

    if sub in ("key", "token") and arg1 and arg2:
        source = arg1
        key_field = "token" if source == "tushare" else "key"
        if source not in cfg:
            cfg[source] = {}
        cfg[source][key_field] = arg2
        cfg[source]["enabled"] = True
        _save_stock_cfg(cfg)
        print(f"{GREEN}✅ [{source}] {key_field} 已更新{RESET}")
        return False

    print(f"{RED}❌ 未知子命令或参数不足{RESET}")
    return False


def _cmd_stock_setup(state, parts):
    """交互式股票数据源配置向导"""
    cfg = _load_stock_cfg()

    print(f"{CYAN}╔{'═' * 50}╗{RESET}")
    print(f"{CYAN}║{'📈  StockShareAgent 配置向导':^46}║{RESET}")
    print(f"{CYAN}╚{'═' * 50}╝{RESET}")

    print(f"\n{DIM}请选择默认数据源:{RESET}")
    sources = [
        ("akshare", "开源 A 股数据（无需 key，推荐新手）"),
        ("mairui", "麦蕊金融数据 API（需 token）"),
        ("tushare", "tushare 数据接口（需 token）"),
        ("trade", "券商/量化交易 API（仅配置框架）"),
    ]
    for i, (sid, desc) in enumerate(sources, 1):
        marker = f" {YELLOW}👈 当前{RESET}" if cfg.get("default_source") == sid else ""
        print(f"  {CYAN}[{i}]{RESET} {sid} — {DIM}{desc}{RESET}{marker}")

    try:
        choice = input(f"\n{YELLOW}👉 数据源编号 (回车跳过): {RESET}").strip()
    except (EOFError, KeyboardInterrupt):
        print(f"\n{DIM}已取消。{RESET}")
        return False

    if choice:
        if choice.isdigit() and 1 <= int(choice) <= len(sources):
            cfg["default_source"] = sources[int(choice) - 1][0]
        else:
            print(f"{RED}❌ 无效编号{RESET}")
            return False

    for sid in ("akshare", "mairui", "tushare"):
        scfg = cfg.setdefault(sid, {})
        default_enabled = "y" if scfg.get("enabled") else "n"
        try:
            en = input(f"\n{YELLOW}👉 启用 {sid}? [{default_enabled}/N]: {RESET}").strip().lower()
        except (EOFError, KeyboardInterrupt):
            en = ""
        scfg["enabled"] = en in ("", "y", "yes") if default_enabled == "y" else en in ("y", "yes")

        if scfg["enabled"] and sid in ("mairui", "tushare"):
            key_label = "Token" if sid == "tushare" else "API Key"
            try:
                key = input(f"{YELLOW}👉 {sid} {key_label}: {RESET}").strip()
            except (EOFError, KeyboardInterrupt):
                key = ""
            if sid == "tushare":
                scfg["token"] = key
            else:
                scfg["key"] = key

    _save_stock_cfg(cfg)
    print(f"\n{GREEN}✅ StockShareAgent 配置已保存！{RESET}")
    _print_config(cfg)
    return False
