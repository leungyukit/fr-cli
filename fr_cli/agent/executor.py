# Agent executor
from fr_cli.agent.manager import (load_persona, load_memory, load_skills, load_agent_module, agent_exists, load_progress)
from fr_cli.agent.workflow import run_workflow, load_workflow
from fr_cli.core.result import Result


def run_agent(name, state, **kwargs):
    if not agent_exists(name):
        return Result.fail("Agent not found. Use /agent_create <name> <description>")
    if load_workflow(name):
        wf_result = run_workflow(name, state, user_input=kwargs.get("pipeline_input"), **kwargs)
        if wf_result.is_fail():
            return Result.fail(wf_result.error)
        final_result, _ = wf_result.unwrap()
        return Result.ok(final_result)
    persona = load_persona(name)
    memory = load_memory(name)
    skills = load_skills(name)
    mod = load_agent_module(name)
    if mod is None:
        return Result.fail("agent.py not found or load failed")
    if not hasattr(mod, "run"):
        return Result.fail("agent.py missing run(context, **kwargs)")
    progress = load_progress(name)
    latest = progress.get("latest", {})

    # 解析 Agent 专属 LLM 配置
    client, provider, model = state.resolve_agent_llm(name)

    context = {
        "persona": persona,
        "memory": memory,
        "skills": skills,
        "client": client,
        "provider": provider,
        "model": model,
        "lang": state.lang,
        "executor": state.executor,
        "state": state,
        "agent_name": name,
        "progress": progress,
        "latest_result": latest.get("result", ""),
        "latest_status": latest.get("status", ""),
        "execution_count": progress.get("counter", 0),
    }
    # v2.4.4 变更：tool 调用由 Agent 内部代码用 context["executor"].invoke_tool(..., client=client, model=model) 显式传
    # —— 取代了之前的 push_agent_context 栈式覆盖
    result = mod.run(context, **kwargs)
    if isinstance(result, Result):
        return result
    return Result.ok(result)


def delegate_to_agent(name, state, pipeline_input=None, **kwargs):
    """将请求委托给指定 Agent 执行，支持管道输入（pipeline_input）供多 Agent 协作链使用。

    v2.4.4 变更：移除 push_agent_context/pop_agent_context 包装。Agent 内部代码通过
    context["executor"].invoke_tool(..., client=client, model=model) 显式传 LLM 上下文。
    """
    if not agent_exists(name):
        return Result.fail(f"Agent not found: {name}")
    persona = load_persona(name)
    memory = load_memory(name)
    skills = load_skills(name)
    mod = load_agent_module(name)
    if mod is None:
        return Result.fail("agent.py not found or load failed")
    if not hasattr(mod, "run"):
        return Result.fail("agent.py missing run(context, **kwargs)")

    # 解析 Agent 专属 LLM 配置
    client, provider, model = state.resolve_agent_llm(name)

    context = {
        "persona": persona,
        "memory": memory,
        "skills": skills,
        "client": client,
        "provider": provider,
        "model": model,
        "lang": state.lang,
        "executor": state.executor,
        "state": state,
        "agent_name": name,
        "pipeline_input": pipeline_input,
    }
    result = mod.run(context, **kwargs)
    if isinstance(result, Result):
        return result
    return Result.ok(result)


def run_multi_agent(names, state, initial_input=None, **kwargs):
    """多 Agent 流水线协作 —— 将多个 Agent 串联执行，前一个的输出作为后一个的输入。"""
    pipeline_result = initial_input
    logs = []
    for idx, name in enumerate(names, start=1):
        print(f"[流水线] {idx}/{len(names)}: 运行 Agent {name}")
        result = delegate_to_agent(name, state, pipeline_input=pipeline_result, **kwargs)
        if result.is_fail():
            return Result.fail(f"Pipeline step {idx} ('{name}'): {result.error}")
        logs.append({"agent": name, "result": result.unwrap()})
        pipeline_result = result.unwrap()
    return Result.ok(logs)
