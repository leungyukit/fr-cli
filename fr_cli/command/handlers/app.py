"""命令处理器 —— app"""

from fr_cli.command.registry import register

@register(
    name="launch_app",
    triggers=["打开应用", "启动程序", "运行软件", "launch app", "打开微信", "打开浏览器", "打开 Word", "打开 Excel"],
    description="启动指定应用程序，可带文件或 URL 参数",
    params={"name": str},
    aliases=["/launch"],
)
def _launch_app(deps, **kwargs):
    from fr_cli.weapon.launcher import launch_app
    ok, msg = launch_app(kwargs["name"], kwargs.get("target"), deps.lang)
    return (msg, None) if ok else (None, msg)


@register(
    name="list_apps",
    description="列出本机可用应用别名",
    params={},
    aliases=["/apps"],
)
def _list_apps(deps, **kwargs):
    from fr_cli.weapon.launcher import list_apps
    res, err = list_apps(deps.lang)
    return (res, None) if not err else (None, err)


# ------------------------------------------------------------------

