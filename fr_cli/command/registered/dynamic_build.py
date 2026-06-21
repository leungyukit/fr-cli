"""
注册表分组：动态构建
- dynamic_build: AI 可调用的动态构建工具
- analyze_gap: 分析需求与现有工具集的能力缺口
- build_missing_tool: 发现缺口并自动构建新工具
- build_cmd: /build 命令补全占位
- install_package: 安装 Python pip 包
"""
from types import SimpleNamespace

from fr_cli.command.registry import register, get_registry
from fr_cli.core.result import Result


def _build_state_from_deps(deps):
    """从 deps 构造动态构建所需的最小 state。"""
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
    return state


@register(
    name="dynamic_build",
    description="根据需求动态构建新工具（自动安装依赖并生成代码）",
    params={"requirement": str},
    triggers=["构建", "生成工具", "install", "build tool", "缺功能", "没有这个功能"],
    security="sec_exec",
)
def _dynamic_build(deps, **kwargs):
    """AI 调用：根据需求描述动态构建工具"""
    from fr_cli.dynamic_builder import build_tool

    requirement = kwargs.get("requirement", "")
    if not requirement:
        return Result.fail("请提供需求描述，例如 dynamic_build({\"requirement\": \"生成二维码识别工具\"})")

    state = _build_state_from_deps(deps)
    return build_tool(requirement, state, lang=getattr(deps, "lang", "zh"), confirm=True)


@register(
    name="analyze_gap",
    description="分析用户需求是否已被现有工具覆盖，返回能力缺口报告",
    params={"requirement": str},
    triggers=["缺口", "缺功能", "analyze gap", "capability gap", "能不能做"],
)
def _analyze_gap(deps, **kwargs):
    """AI 调用：分析需求与现有工具集的能力缺口"""
    from fr_cli.dynamic_builder.gap_analyzer import CapabilityGapAnalyzer

    requirement = kwargs.get("requirement", "")
    if not requirement:
        return Result.fail("请提供需求描述，例如 analyze_gap({\"requirement\": \"生成二维码\"})")

    tools = get_registry().get_available_tools(getattr(deps, "plugins", {}))
    analyzer = CapabilityGapAnalyzer()
    result = analyzer.analyze(requirement, tools, state=_build_state_from_deps(deps), lang=getattr(deps, "lang", "zh"))
    return Result.ok(result)


@register(
    name="build_missing_tool",
    description="分析能力缺口并在确认存在缺口后自动构建新工具",
    params={"requirement": str},
    triggers=["自动构建", "build missing", "发现缺口"],
    security="sec_exec",
)
def _build_missing_tool(deps, **kwargs):
    """AI 调用：先分析缺口，若确实存在缺口则调用 dynamic_build"""
    from fr_cli.dynamic_builder.gap_analyzer import CapabilityGapAnalyzer
    from fr_cli.dynamic_builder import build_tool

    requirement = kwargs.get("requirement", "")
    if not requirement:
        return Result.fail("请提供需求描述")

    state = _build_state_from_deps(deps)
    tools = get_registry().get_available_tools(getattr(deps, "plugins", {}))
    analyzer = CapabilityGapAnalyzer()
    gap_report = analyzer.analyze(requirement, tools, state=state, lang=getattr(deps, "lang", "zh"))
    if not gap_report.get("gap"):
        return Result.ok({
            "built": False,
            "reason": gap_report.get("reasoning", "现有工具已覆盖该需求"),
            "report": gap_report,
        })

    build_result = build_tool(requirement, state, lang=getattr(deps, "lang", "zh"), confirm=True)
    if build_result.is_fail():
        return build_result
    return Result.ok({
        "built": True,
        "report": gap_report,
        "result": build_result.unwrap(),
    })


@register(
    name="build_cmd",
    description="动态构建工具（/build <需求>）",
    params={},
    aliases=["/build"],
)
def _build_cmd(deps, **kwargs):
    """占位：/build 由 main.py 路由处理"""
    return Result.ok("💡 /build 由 main.py 路由处理")


@register(
    name="install_package",
    description="安装 Python pip 包（如 msal、requests、pillow 等）",
    params={"package": str},
    triggers=["安装", "install", "pip install", "装一下", "缺少"],
    security="sec_exec",
)
def _install_package(deps, **kwargs):
    """AI 调用：安装指定的 pip 包"""
    from fr_cli.dynamic_builder.dependency_manager import install_dependency

    package = kwargs.get("package", "").strip()
    if not package:
        return Result.fail("请提供包名，例如 install_package({\"package\": \"msal\"})")

    return install_dependency(package, lang=getattr(deps, "lang", "zh"), confirm=True)
