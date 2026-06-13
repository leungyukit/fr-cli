"""
注册表分组：主命令路由占位（让 /h /e /s /u 能补全）

这些 handler 在 main.py 通过 COMMAND_ROUTES 直接调用，
注册到注册表纯粹是为了让 / 补全能找到它们。
"""
from fr_cli.command.registry import register


@register(
    name="help",
    description="显示帮助（/help [topic] 看分类帮助）",
    params={},
    aliases=["/help", "/?", "/h"],
)
def _help_cmd(deps, **kwargs):
    return "💡 /help 由 main.py 路由处理（不通过注册表）", None


@register(
    name="exit",
    description="退出 fr-cli",
    params={},
    aliases=["/exit", "/quit", "/q"],
)
def _exit_cmd(deps, **kwargs):
    return "💡 /exit 由 main.py 路由处理", None


@register(
    name="shell",
    description="切换到 shell 模式",
    params={},
    aliases=["/shell", "/s"],
)
def _shell_cmd(deps, **kwargs):
    return "💡 /shell 由 main.py 路由处理", None


@register(
    name="undo",
    description="撤销最后一条对话（或 /undo N 撤销 N 轮）",
    params={},
    aliases=["/undo", "/u"],
)
def _undo_cmd(deps, **kwargs):
    return "💡 /undo 由 main.py 路由处理", None
