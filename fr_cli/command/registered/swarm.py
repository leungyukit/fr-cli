"""
注册表分组：蜂群（Swarm）多 Agent 协作
- swarm_run
"""
from fr_cli.command.registry import register
from fr_cli.core.result import Result


@register(
    name="swarm_run",
    triggers=["蜂群", "多Agent", "协作", "swarm", "council", "议会", "并行"],
    description="蜂群协作：并行调用多个 Agent 独立工作或汇总意见",
    params={"mode": str, "names": list, "user_input": str},
    security="sec_exec",
    aliases=["/swarm"],
)
def _swarm_run(deps, **kwargs):
    from fr_cli.agent.swarm import run_swarm

    mode = kwargs.get("mode", "parallel")
    names = kwargs.get("names", [])
    user_input = kwargs.get("user_input", "")
    max_workers = kwargs.get("max_workers", 5)

    # 统一把字符串转成 list（兼容命令行逗号分隔）
    if isinstance(names, str):
        names = [n.strip() for n in names.split(",") if n.strip()]

    try:
        max_workers = min(int(max_workers), 10)
    except (ValueError, TypeError):
        max_workers = 5

    result, err = run_swarm(mode, names, deps, user_input, max_workers=max_workers)
    return Result.from_tuple(result, err)
