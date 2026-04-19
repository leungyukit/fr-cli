# Agent executor
from fr_cli.agent.manager import (load_persona, load_memory, load_skills, load_agent_module, agent_exists)
from fr_cli.agent.workflow import run_workflow, load_workflow


def run_agent(name, state, **kwargs):
    if not agent_exists(name):
        return None, "Agent not found. Use /agent_create <name> <description>"
    if load_workflow(name):
        return run_workflow(name, state, user_input=kwargs.get("pipeline_input"), **kwargs)
    persona = load_persona(name)
    memory = load_memory(name)
    skills = load_skills(name)
    mod = load_agent_module(name)
    if mod is None:
        return None, "agent.py not found or load failed"
    if not hasattr(mod, "run"):
        return None, "agent.py missing run(context, **kwargs)"
    context = {
        "persona": persona,
        "memory": memory,
        "skills": skills,
        "client": state.client,
        "model": state.model_name,
        "lang": state.lang,
        "executor": state.executor,
        "state": state,
        "agent_name": name,
    }
    try:
        result = mod.run(context, **kwargs)
        return result, None
    except Exception as e:
        return None, str(e)


def delegate_to_agent(name, state, pipeline_input=None, **kwargs):
    """将请求委托给指定 Agent 执行，支持管道输入（pipeline_input）供多 Agent 协作链使用。"""
    if not agent_exists(name):
        return None, f"Agent not found: {name}"
    persona = load_persona(name)
    memory = load_memory(name)
    skills = load_skills(name)
    mod = load_agent_module(name)
    if mod is None:
        return None, "agent.py not found or load failed"
    if not hasattr(mod, "run"):
        return None, "agent.py missing run(context, **kwargs)"
    context = {
        "persona": persona,
        "memory": memory,
        "skills": skills,
        "client": state.client,
        "model": state.model_name,
        "lang": state.lang,
        "executor": state.executor,
        "state": state,
        "agent_name": name,
        "pipeline_input": pipeline_input,
    }
    try:
        result = mod.run(context, **kwargs)
        return result, None
    except Exception as e:
        return None, str(e)


def run_multi_agent(names, state, initial_input=None, **kwargs):
    """多 Agent 流水线协作 —— 将多个 Agent 串联执行，前一个的输出作为后一个的输入。"""
    pipeline_result = initial_input
    logs = []
    for idx, name in enumerate(names, start=1):
        print(f"[流水线] {idx}/{len(names)}: 运行 Agent {name}")
        result, err = delegate_to_agent(name, state, pipeline_input=pipeline_result, **kwargs)
        if err:
            return None, f"Pipeline step {idx} ('{name}'): {err}"
        logs.append({"agent": name, "result": result})
        pipeline_result = result
    return logs, None
