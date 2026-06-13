"""
注册表分组：动态构建
- dynamic_build: AI 可调用的动态构建工具
- build_cmd: /build 命令补全占位
"""
from fr_cli.command.registry import register
from fr_cli.core.result import Result


@register(
    name="dynamic_build",
    description="根据需求动态构建新工具（自动安装依赖并生成代码）",
    params={"requirement": str},
    triggers=["构建", "生成工具", "install", "build tool", "缺功能", "没有这个功能"],
    security="sec_exec",
)
def _dynamic_build(deps, **kwargs):
    """AI 调用：根据需求描述动态构建工具"""
    from types import SimpleNamespace
    from fr_cli.dynamic_builder import build_tool

    requirement = kwargs.get("requirement", "")
    if not requirement:
        return Result.fail("请提供需求描述，例如 dynamic_build({\"requirement\": \"生成二维码识别工具\"})")

    # 从 deps 构造最小 state（动态构建所需）
    state = getattr(deps, "state", None)
    if state is None:
        state = SimpleNamespace(
            client=getattr(deps, "client", None),
            model_name=getattr(deps, "model_name", None),
            lang=getattr(deps, "lang", "zh"),
            cfg=getattr(deps, "cfg", {}),
            vfs=getattr(deps, "vfs", None),
            security=getattr(deps, "security", None),
            plugins=getattr(deps, "plugins", {}),
        )

    result = build_tool(requirement, state, lang=getattr(deps, "lang", "zh"), confirm=True)
    return result


@register(
    name="build_cmd",
    description="动态构建工具（/build <需求>）",
    params={},
    aliases=["/build"],
)
def _build_cmd(deps, **kwargs):
    """占位：/build 由 main.py 路由处理"""
    return Result.ok("💡 /build 由 main.py 路由处理")
