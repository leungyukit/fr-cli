
"""
Agent workflow engine
"""

import concurrent.futures
import re
from fr_cli.agent.manager import load_persona, load_memory, load_skills, save_memory
from fr_cli.core.result import Result

WORKFLOW_FILE = "workflow.md"
MAX_WORKFLOW_STEPS = 100


class WorkflowTimeoutError(Exception):
    """工作流步骤执行超时"""
    pass


def load_workflow(name):
    from fr_cli.agent.manager import _agent_dir
    p = _agent_dir(name) / WORKFLOW_FILE
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8")


def save_workflow(name, content):
    from fr_cli.agent.manager import _agent_dir
    p = _agent_dir(name) / WORKFLOW_FILE
    p.write_text(content, encoding="utf-8")


def parse_workflow(text):
    steps = []
    sections = re.split(r"\n## ", text)
    for sec in sections[1:]:
        lines = sec.strip().split("\n")
        title_line = lines[0].strip()
        m = re.match(r"步骤?(\d+)[\s:\-\.]+(.+)", title_line, re.I)
        if m:
            step_num = int(m.group(1))
            step_title = m.group(2).strip()
        else:
            step_num = len(steps) + 1
            step_title = title_line
        action = ""
        params = {}
        in_params = False
        for line in lines[1:]:
            line = line.rstrip()
            if not line:
                continue
            am = re.match(r"-\s+\*\*action\*\*\s*:\s*(.+)", line, re.I)
            if am:
                action = am.group(1).strip()
                continue
            if re.match(r"-\s+\*\*params\*\*\s*:", line, re.I):
                in_params = True
                continue
            if in_params:
                pm = re.match(r"\s+-\s+([\w_]+)\s*:\s*(.+)", line)
                if pm:
                    params[pm.group(1)] = pm.group(2).strip()
        if action:
            steps.append({"num": step_num, "title": step_title, "action": action, "params": params})
    steps.sort(key=lambda x: x["num"])
    return steps


def _build_dependency_graph(steps):
    """根据 {{stepN.result}} / {{stepN.error}} 模板变量构建步骤依赖图"""
    graph = {i: set() for i in range(len(steps))}
    var_pattern = re.compile(r"\{\{\s*step(\d+)\.(result|error)\s*\}\}", re.I)
    for i, step in enumerate(steps):
        for val in step.get("params", {}).values():
            for m in var_pattern.finditer(str(val)):
                dep = int(m.group(1)) - 1
                if dep != i and 0 <= dep < len(steps):
                    graph[i].add(dep)
    return graph


def _detect_cycle(steps):
    """检测工作流步骤间是否存在循环依赖。返回形成环的节点索引列表，无环返回 None。"""
    graph = _build_dependency_graph(steps)
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {i: WHITE for i in range(len(steps))}

    def dfs(node, path):
        color[node] = GRAY
        for neighbor in graph[node]:
            if color[neighbor] == GRAY:
                cycle_start = path.index(neighbor)
                return path[cycle_start:] + [neighbor]
            if color[neighbor] == WHITE:
                res = dfs(neighbor, path + [neighbor])
                if res:
                    return res
        color[node] = BLACK
        return None

    for i in range(len(steps)):
        if color[i] == WHITE:
            cycle = dfs(i, [i])
            if cycle:
                return cycle
    return None


def _resolve_var(var_expr, context, step_results, user_input):
    """解析模板变量，如 {{step1.result}} {{user_input}}"""
    var_expr = var_expr.strip()
    if var_expr == "user_input":
        return user_input or ""
    if var_expr == "agent.persona":
        return context.get("persona", "")
    if var_expr == "agent.memory":
        return context.get("memory", "")
    if var_expr == "agent.skills":
        return context.get("skills", "")
    sm = re.match(r"step(\d+)\.result", var_expr, re.I)
    if sm:
        idx = int(sm.group(1)) - 1
        if 0 <= idx < len(step_results):
            return str(step_results[idx].get("result", ""))
    sm = re.match(r"step(\d+)\.error", var_expr, re.I)
    if sm:
        idx = int(sm.group(1)) - 1
        if 0 <= idx < len(step_results):
            return str(step_results[idx].get("error", ""))
    return "{" + var_expr + "}"


def _substitute_vars(text, context, step_results, user_input):
    """替换文本中的所有 {{var}} 模板变量"""
    if not isinstance(text, str):
        return text
    def repl(m):
        return _resolve_var(m.group(1), context, step_results, user_input)
    return re.sub(r"\{\{([^}]+)\}\}", repl, text)


def _run_with_timeout(func, timeout):
    """执行函数并设置超时；timeout 为 None 或 <=0 时不限制"""
    if timeout is None or timeout <= 0:
        return func()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise WorkflowTimeoutError(f"步骤执行超时（{timeout:g}秒）")


def _execute_step_action(action, params, context, state, name, user_input, kwargs):
    """执行单个步骤的动作，返回 Result。

    v2.4.4 变更：invoke_tool / execute_cmd 步骤显式传入 Agent 专属 client/model_name
    （取代之前的 push_agent_context/pop_agent_context 栈式覆盖）。
    """
    # Agent 专属 LLM 上下文（用于 invoke_tool / execute 步骤的 sec_* 操作）
    agent_client = context.get("client")
    agent_model = context.get("model")
    try:
        if action in ("invoke_tool", "tool"):
            tool_name = params.pop("tool", list(params.keys())[0] if params else "")
            tool_params = params
            return state.executor.invoke_tool(
                tool_name, tool_params,
                client=agent_client, model_name=agent_model,
            )
        elif action in ("execute_cmd", "cmd", "command"):
            cmd_str = params.get("cmd", "")
            return state.executor.execute(
                cmd_str,
                client=agent_client, model_name=agent_model,
            )
        elif action in ("agent_call", "agent", "call_agent"):
            from fr_cli.agent.executor import run_agent
            target = params.get("target") or params.get("agent") or params.get("to")
            message = params.get("message", "")
            return run_agent(target, state, pipeline_input=message, **kwargs)
        elif action in ("ai_generate", "ai", "generate", "ask"):
            prompt = params.get("prompt", "")
            max_tokens = int(params.get("max_tokens", "4096") or 4096)
            from fr_cli.core.stream import stream_cnt
            msgs = [{"role": "user", "content": prompt}]
            txt, _, _, _ = stream_cnt(context["client"], context["model"], msgs, state.lang, max_tokens=max_tokens)
            return Result.ok(txt)
        elif action in ("save_memory", "memory_append"):
            mem = params.get("content", "")
            old = load_memory(name)
            save_memory(name, old + "\n" + mem if old else mem)
            return Result.ok("记忆已更新")
        else:
            return Result.fail(f"未知动作: {action}")
    except Exception as e:
        return Result.fail(str(e))


def run_workflow(name, state, user_input=None, **kwargs):
    """执行 Agent 的工作流。返回 Result[(final_result, step_results)]"""
    wf_text = load_workflow(name)
    if not wf_text:
        return Result.fail("工作流不存在，使用 /agent_edit <name> workflow 定义工作流")
    steps = parse_workflow(wf_text)
    if not steps:
        return Result.fail("工作流为空或解析失败")
    if len(steps) > MAX_WORKFLOW_STEPS:
        return Result.fail(f"工作流步骤数超过上限 {MAX_WORKFLOW_STEPS}")

    cycle = _detect_cycle(steps)
    if cycle:
        cycle_desc = " -> ".join(f"步骤 {steps[i]['num']}" for i in cycle)
        return Result.fail(f"工作流存在循环依赖: {cycle_desc}")

    persona = load_persona(name)
    memory = load_memory(name)
    skills = load_skills(name)

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
    }

    # v2.4.4 变更：移除 push_agent_context/pop_agent_context 包装。
    # 步骤 action 中调用 state.executor.invoke_tool/execute/process_ai_commands 时
    # 需显式传 client=client, model_name=model 来使用 Agent 专属 LLM 上下文。
    step_results = []
    for step in steps:
        action = step["action"]
        params = {k: _substitute_vars(v, context, step_results, user_input) for k, v in step["params"].items()}
        retry_count = int(params.pop("retry_count", "0") or 0)
        step_timeout = params.pop("timeout", None)
        try:
            step_timeout = float(step_timeout) if step_timeout is not None else None
        except (TypeError, ValueError):
            step_timeout = None

        step_result = None
        for attempt in range(retry_count + 1):
            # 每次重试使用原始参数副本，避免 pop 破坏后续重试
            current_params = dict(params)
            try:
                step_result = _run_with_timeout(
                    lambda: _execute_step_action(
                        action, current_params, context, state, name, user_input, kwargs
                    ),
                    step_timeout,
                )
            except WorkflowTimeoutError as e:
                step_result = Result.fail(str(e))

            if step_result.is_ok():
                break

        step_results.append({
            "step": step["num"],
            "title": step["title"],
            "action": action,
            "result": step_result.unwrap() if step_result.is_ok() else None,
            "error": step_result.error if step_result.is_fail() else None,
            "attempts": attempt + 1,
        })

        if step_result.is_fail():
            return Result.fail(f"步骤 {step['num']} ({step['title']}) 失败: {step_result.error}")

    final_result = step_results[-1]["result"] if step_results else None
    return Result.ok((final_result, step_results))
