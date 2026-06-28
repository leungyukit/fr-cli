"""
Web 控制台工具:
- console_start: 启动 HTTP 服务(自动开浏览器)
- console_stop: 停止
- console_status: 查看状态
"""
from fr_cli.command.registry import register
from fr_cli.core.result import Result


@register(
    name="console_start",
    triggers=["启动控制台", "console start", "web 控制台"],
    description="启动 Web 控制台(浏览器查看 fr-cli 状态)",
    params={"host": str, "port": int, "token": str, "no_open": bool},
    aliases=["/console", "/web"],
)
def _register_console_start(deps, **kwargs):
    host = kwargs.get("host") or "127.0.0.1"
    port = int(kwargs.get("port", 7777))
    token = kwargs.get("token") or None
    no_open = bool(kwargs.get("no_open", False))

    from fr_cli.web.console import start_console
    result = start_console(host=host, port=port, token=token, open_browser=not no_open)
    if not result["ok"]:
        return Result.fail(result.get("error", "启动失败"))

    return Result.ok(
        f"✅ Web 控制台已启动\n"
        f"  URL: {result['url']}\n"
        f"  Token: {result['token']}\n"
        f"  带 Token URL: {result['url_with_token']}\n\n"
        f"💡 API 示例:\n"
        f"  curl '{result['url_with_token'].replace('/?token=', '/api/status?token=')}'\n\n"
        f"⚠️ Token 仅在本次启动显示,丢失需重启。"
    )


@register(
    name="console_stop",
    triggers=["停止控制台", "console stop"],
    description="停止 Web 控制台",
    params={},
    aliases=["/console_stop"],
)
def _register_console_stop(deps, **kwargs):
    from fr_cli.web.console import stop_console
    result = stop_console()
    if not result["ok"]:
        return Result.fail(result.get("error"))
    return Result.ok("✅ Web 控制台已停止")


@register(
    name="console_status",
    triggers=["控制台状态", "console status"],
    description="查看 Web 控制台运行状态",
    params={},
    aliases=["/console_status"],
)
def _register_console_status(deps, **kwargs):
    from fr_cli.web.console import console_status
    s = console_status()
    if not s["running"]:
        return Result.ok("Web 控制台未运行")
    return Result.ok(
        f"🟢 Web 控制台运行中\n"
        f"  URL: {s['url']}\n"
        f"  Token: {s['token']}"
    )
