# Agent executor
from fr_cli.agent.manager import (load_persona, load_memory, load_skills, load_agent_module, agent_exists, load_progress)
from fr_cli.agent.workflow import run_workflow, load_workflow


def run_agent(name, state, **kwargs):
    if not agent_exists(name):
        return None, "Agent not found. Use /agent_create <name> <description>"
    if load_workflow(name):
        result, err, _ = run_workflow(name, state, user_input=kwargs.get("pipeline_input"), **kwargs)
        return result, err
    persona = load_persona(name)
    memory = load_memory(name)
    skills = load_skills(name)
    mod = load_agent_module(name)
    if mod is None:
        return None, "agent.py not found or load failed"
    if not hasattr(mod, "run"):
        return None, "agent.py missing run(context, **kwargs)"
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
    # 将工具调用的 LLM 上下文切换为 Agent 专属配置
    state.executor.push_agent_context(client, model)
    try:
        result = mod.run(context, **kwargs)
        return result, None
    except Exception as e:
        return None, str(e)
    finally:
        state.executor.pop_agent_context()


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
    # 将工具调用的 LLM 上下文切换为 Agent 专属配置
    state.executor.push_agent_context(client, model)
    try:
        result = mod.run(context, **kwargs)
        return result, None
    except Exception as e:
        return None, str(e)
    finally:
        state.executor.pop_agent_context()


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
