"""命令处理器 —— agent"""

from fr_cli.command.registry import register

@register(
    name="agent_create",
    triggers=["创建Agent", "新建Agent", "生成Agent", "create agent", "new agent"],
    description="根据需求自动生成 Agent 分身",
    params={"name": str, "description": str},
    aliases=["/agent_create"],
)
def _agent_create(deps, **kwargs):
    from fr_cli.agent.generator import generate_agent
    from fr_cli.agent.manager import save_persona, save_skills, save_agent_code, create_agent_dir
    name = kwargs["name"]
    desc = kwargs["description"]
    d = create_agent_dir(name)
    result = generate_agent(deps.client, deps.model_name, name, desc, deps.lang)
    if result["persona"]:
        save_persona(name, result["persona"])
    if result["skills"]:
        save_skills(name, result["skills"])
    if result["code"]:
        save_agent_code(name, result["code"])
    return f"Agent [{name}] 创建完成！路径: {d}", None


def _make_compat_state(deps):
    """将 SimpleNamespace deps 包装为兼容 AppState 的对象，供 Agent executor 使用"""
    class _CompatState:
        def __init__(self, d):
            for k, v in d.__dict__.items():
                setattr(self, k, v)
    compat = _CompatState(deps)
    compat.executor = getattr(deps, 'executor', None)
    return compat


@register(
    name="agent_run",
    triggers=["运行Agent", "调用Agent", "执行Agent", "run agent"],
    description="运行指定本地 Agent",
    params={"name": str},
    security="sec_exec",
    aliases=["/agent_run"],
)
def _agent_run(deps, **kwargs):
    from fr_cli.agent.executor import run_agent
    result, err = run_agent(kwargs["name"], _make_compat_state(deps))
    return (result, None) if not err else (None, err)


@register(
    name="agent_call",
    triggers=["调用Agent", "协作Agent", "agent_call", "召唤Agent"],
    description="调用Agent（本地或远程）并传入任务描述，实现MasterAgent与其他Agent协作",
    params={"name": str, "user_input": str},
    security="sec_exec",
    aliases=["/agent_call"],
)
def _agent_call(deps, **kwargs):
    from fr_cli.agent.executor import run_agent
    name = kwargs.get("name", "")
    user_input = kwargs.get("user_input", "")
    compat = _make_compat_state(deps)
    result, err = run_agent(name, compat, user_input=user_input)
    return (result, None) if not err else (None, err)


# ------------------------------------------------------------------
# 调试 / 诊断 工具
# ------------------------------------------------------------------

