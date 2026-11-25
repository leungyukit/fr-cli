"""
注册表分组：Agent Team（多 Agent 协作小组）
- agent_team_run
"""
from fr_cli.command.registry import register
from fr_cli.core.result import Result


@register(
    name="agent_team_run",
    triggers=["团队协作", "组队", "多智能体", "agent team"],
    description="Agent Team 协作：自动拆解任务，多个成员并行完成后汇总成最终答案",
    params={"user_input": str},
    security="sec_exec",
    aliases=["/agent_team_run"],
)
def _agent_team_run(deps, **kwargs):
    from fr_cli.agent.team import AgentTeam

    user_input = kwargs.get("user_input", "") or ""
    if not user_input.strip():
        return Result.fail("缺少 user_input：需要描述要协作完成的任务")

    try:
        max_workers = int(kwargs.get("max_workers") or 6)
    except (TypeError, ValueError):
        max_workers = 6

    result = AgentTeam(deps).run(user_input, max_workers=max_workers)
    if result.is_fail():
        return Result.fail(result.error, error_type=result.error_type)

    payload = result.unwrap() or {}
    return Result.ok(payload.get("answer", ""))
