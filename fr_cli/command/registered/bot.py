"""
Bot 统一适配层的命令入口:
- bot_start:  启动 Bot 守护进程
- bot_stop:   停止
- bot_status: 查看状态
- bot_config: 查看 / 编辑 Bot 配置
- bot_channels: 列出已实现的通道与配置状态
"""

from fr_cli.command.registry import register
from fr_cli.core.result import Result


@register(
    name="bot_start",
    triggers=["启动 bot", "bot start", "机器人启动"],
    description="启动 Bot 守护进程(接收 IM 平台 webhook)",
    params={"host": str, "port": int},
    aliases=["/bot", "/bot_start"],
)
def _register_bot_start(deps, **kwargs):
    from fr_cli.bot.runtime.manager import BotManager

    host = kwargs.get("host") or None
    port = int(kwargs["port"]) if kwargs.get("port") else None

    mgr = BotManager()
    if mgr.is_running():
        return Result.fail(f"Bot 已在运行 (pid={mgr._read_pid()})，用 /bot_status 查看")

    result = mgr.start(host=host, port=port)
    if not result.get("ok"):
        return Result.fail(result.get("error", "启动失败"))

    from fr_cli.bot.runtime.engine import load_bot_config
    cfg = load_bot_config()
    channels = sorted((cfg.get("channels") or {}).keys())
    lines = [
        "[OK] Bot 守护进程已启动",
        f"  PID: {result.get('pid')}",
        f"  地址: {result.get('url')}",
    ]
    if channels:
        lines.append(f"  已配置通道: {', '.join(channels)}")
        lines.append(f"  入站路径: POST {result.get('url')}/bot/<channel>")
    else:
        lines.append("  [!] 尚未配置任何通道 —— 用 /bot_config 配置后再启动才有意义")
    lines.append("")
    lines.append("各平台的 webhook 地址请填到平台后台，并指向上面这个地址。")
    return Result.ok("\n".join(lines))


@register(
    name="bot_stop",
    triggers=["停止 bot", "bot stop", "机器人停止"],
    description="停止 Bot 守护进程",
    params={},
    aliases=["/bot_stop"],
)
def _register_bot_stop(deps, **kwargs):
    from fr_cli.bot.runtime.manager import BotManager

    result = BotManager().stop()
    if not result.get("ok"):
        return Result.fail(result.get("error", "停止失败"))
    return Result.ok(f"[OK] Bot 已停止 ({result.get('note', '')})")


@register(
    name="bot_status",
    triggers=["bot 状态", "bot status", "机器人状态"],
    description="查看 Bot 运行状态与统计",
    params={},
    aliases=["/bot_status"],
)
def _register_bot_status(deps, **kwargs):
    from fr_cli.bot.runtime.manager import BotManager
    from fr_cli.bot.runtime.engine import load_bot_config, BotEngine

    mgr = BotManager()
    st = mgr.status()
    cfg = load_bot_config()

    lines = ["=== Bot 状态 ==="]
    lines.append(f"  运行中: {'是' if st.get('running') else '否'}")
    if st.get("pid"):
        lines.append(f"  PID:    {st['pid']}")
    lines.append(f"  监听:   {cfg.get('host', '127.0.0.1')}:{cfg.get('port', 8790)}")
    lines.append(f"  状态池: {cfg.get('pool_size', 2)} 个 AppState")
    lines.append(f"  机器人名: {', '.join(cfg.get('bot_names') or []) or '(未设置)'}")

    configured = sorted((cfg.get("channels") or {}).keys())
    lines.append(f"  已配置通道: {', '.join(configured) or '(无)'}")

    try:
        available = BotEngine({}, cfg).available_channels()
        lines.append(f"  可用通道:   {', '.join(available) or '(无)'}")
    except Exception:
        pass

    if st.get("running"):
        lines.append(f"  日志: {st.get('log_file')}")
    return Result.ok("\n".join(lines))


@register(
    name="bot_config",
    triggers=["bot 配置", "bot config"],
    description="查看或修改 Bot 配置",
    params={"set": str, "value": str},
    aliases=["/bot_config"],
)
def _register_bot_config(deps, **kwargs):
    from fr_cli.bot.runtime.engine import load_bot_config, save_bot_config

    cfg = load_bot_config()
    key = (kwargs.get("set") or "").strip()
    value = kwargs.get("value")

    if not key:
        import json
        return Result.ok("=== Bot 配置 ===\n" + json.dumps(cfg, ensure_ascii=False, indent=2))

    if value is None:
        cur = cfg.get(key)
        return Result.ok(f"{key} = {cur!r}")

    # 尝试按 JSON 解析值（数字/布尔/列表），失败则按字符串
    parsed: object = value
    try:
        parsed = json.loads(value)
    except Exception:
        pass

    if key == "channels" and isinstance(parsed, dict):
        merged = dict(cfg.get("channels") or {})
        merged.update(parsed)
        cfg["channels"] = merged
    else:
        cfg[key] = parsed

    if not save_bot_config(cfg):
        return Result.fail("保存配置失败")

    # 需要重连的键
    if key in ("port", "host"):
        lines = [f"[OK] 已设置 {key} = {parsed!r}", "[!] 需重启 Bot 生效: /bot_stop 然后 /bot_start"]
    else:
        lines = [f"[OK] 已设置 {key} = {parsed!r}"]
    return Result.ok("\n".join(lines))


@register(
    name="bot_channels",
    triggers=["bot 通道", "bot channels", "支持哪些平台"],
    description="列出 Bot 支持的消息通道及配置状态",
    params={},
    aliases=["/bot_channels"],
)
def _register_bot_channels(deps, **kwargs):
    from fr_cli.bot.runtime.engine import BotEngine, load_bot_config

    cfg = load_bot_config()
    configured = cfg.get("channels") or {}

    try:
        available = BotEngine({}, cfg).available_channels()
    except Exception as e:
        return Result.fail(f"加载通道列表失败: {e}")

    lines = ["=== Bot 通道 ==="]
    for name in available:
        mark = "[已配置]" if name in configured else "[未配置]"
        lines.append(f"  {mark} {name}")
    if not available:
        lines.append("  (未发现任何通道实现)")
        lines.append("")
        lines.append("  新增平台：在 fr_cli/bot/channels/ 下实现 Channel 子类并用")
        lines.append("  @register_channel 登记，然后在 /bot_config 里加一段 channels 配置。")
    else:
        lines.append("")
        lines.append("  配置示例:")
        lines.append("  /bot_config set channels '{\"lark\": {\"app_id\": \"...\", \"app_secret\": \"...\"}}'")
    return Result.ok("\n".join(lines))
