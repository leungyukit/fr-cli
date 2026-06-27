"""
注册表分组:Plan mode 工具

- enter_plan_mode: AI 主动进入计划模式,生成执行计划让用户审批
- exit_plan_mode: 用户审批/拒绝计划
"""
from fr_cli.command.registry import register


@register(
    name="enter_plan_mode",
    triggers=["enter plan mode", "进入计划模式", "制定计划"],
    description="进入 Plan Mode:让 AI 先制定详细执行计划,经用户批准后再执行",
    params={"user_input": str},
    aliases=["/enter_plan"],
)
def _enter_plan_mode(deps, **kwargs):
    from fr_cli.core.plan_mode import enter_plan_mode
    user_input = kwargs.get("user_input", "").strip()
    if not user_input:
        from fr_cli.core.result import Result
        return Result.fail("需要提供 user_input")
    return enter_plan_mode(deps.state, user_input)


@register(
    name="exit_plan_mode",
    triggers=["exit plan mode", "退出计划模式"],
    description="退出 Plan Mode:approved=true 批准并执行计划,false 拒绝",
    params={"approved": bool, "edited_plan": dict},
    aliases=["/exit_plan"],
)
def _exit_plan_mode(deps, **kwargs):
    from fr_cli.core.plan_mode import exit_plan_mode
    approved = bool(kwargs.get("approved", False))
    edited = kwargs.get("edited_plan") or None
    return exit_plan_mode(deps.state, approved=approved, edited_plan=edited)