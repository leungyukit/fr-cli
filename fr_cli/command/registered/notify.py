"""
注册表分组:通知推送命令（notify_add / notify_rm / notify_list / notify）

(从 services.py 按功能拆分,registry 目录扫描自动加载)
"""
from fr_cli.command.registry import register
from fr_cli.core.result import Result


# ============== 通知推送（Notifier） ==============

@register(
    name="notify_add",
    description="添加一个通知通道（飞书/钉钉/企微/Slack/Discord/Telegram）",
    params={"channel": str, "webhook": str, "secret": str},
    aliases=["/notify_add"],
)
def _notify_add(deps, **kwargs):
    """添加通知通道。示例：/notify_add lark https://open.feishu.cn/hook/xxx [secret]"""
    from fr_cli.weapon.notifier import add_channel
    channel = (kwargs.get("channel") or "").strip()
    webhook = (kwargs.get("webhook") or "").strip()
    secret = (kwargs.get("secret") or "").strip() or None
    if not channel or not webhook:
        return Result.fail("用法: /notify_add <channel> <webhook_url> [secret]")
    return add_channel(channel, webhook, secret=secret)


@register(
    name="notify_rm",
    description="删除一个通知通道",
    params={"channel": str},
    aliases=["/notify_rm"],
)
def _notify_rm(deps, **kwargs):
    from fr_cli.weapon.notifier import remove_channel
    return remove_channel(kwargs.get("channel", ""))


@register(
    name="notify_list",
    description="列出所有通知通道",
    params={},
    aliases=["/notify_list"],
)
def _notify_list(deps, **kwargs):
    from fr_cli.weapon.notifier import list_channels
    channels = list_channels()
    if not channels:
        return Result.ok("暂无通知通道。用 /notify_add 添加。")
    lines = []
    for c in channels:
        secret_mark = " [key]" if c["has_secret"] else ""
        lines.append(f"  • {c['channel']:12} {c['webhook']}{secret_mark}")
    return Result.ok("已配置的通知通道:\n" + "\n".join(lines))


@register(
    name="notify",
    description="向指定通道发送通知（飞书/钉钉/企微/Slack/Discord/Telegram）",
    params={"channel": str, "message": str},
    aliases=["/notify"],
)
def _notify(deps, **kwargs):
    """发送通知。示例：/notify lark 任务完成"""
    from fr_cli.weapon.notifier import notify, notify_all

    channel = (kwargs.get("channel") or "").strip()
    message = (kwargs.get("message") or "").strip()
    if not channel or not message:
        return Result.fail("用法: /notify <channel|all> <消息内容>")

    if channel.lower() == "all":
        results = notify_all(message)
        ok_count = sum(1 for r in results.values() if r.is_ok())
        fail = [ch for ch, r in results.items() if r.is_fail()]
        msg = f"群发 {ok_count}/{len(results)} 通道成功"
        if fail:
            msg += f"\n  失败: {', '.join(fail)}"
        return Result.ok(msg) if not fail else Result.fail(msg)

    return notify(channel, message)
