"""命令处理器 —— other"""

from fr_cli.command.registry import register

@register(
    name="help",
    description="显示帮助（/help [topic] 看分类帮助）",
    params={},
    aliases=["/help", "/?", "/h"],
)
def _help_cmd(deps, **kwargs):
    # 实际逻辑在 main.py 路由表里
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

