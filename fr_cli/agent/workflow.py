
"""
Agent workflow engine
"""

import re

WORKFLOW_FILE = "workflow.md"

def load_workflow(name):
    from pathlib import Path
    from fr_cli.agent.manager import _agent_dir
    p = _agent_dir(name) / WORKFLOW_FILE
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8")

def save_workflow(name, content):
    from pathlib import Path
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

def run_workflow(name, state, user_input=None, **kwargs):
    """执行 Agent 的工作流。返回 (final_result, error, step_results)"""
    wf_text = load_workflow(name)
    if not wf_text:
        return None, "工作流不存在，使用 /agent_edit <name> workflow 定义工作流", []
    steps = parse_workflow(wf_text)
    if not steps:
        return None, "工作流为空或解析失败", []

    persona = load_persona(name)
    memory = load_memory(name)
    skills = load_skills(name)

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

    step_results = []
    for step in steps:
        action = step["action"]
        params = {k: _substitute_vars(v, context, step_results, user_input) for k, v in step["params"].items()}
        result = None
        error = None

        try:
            if action in ("invoke_tool", "tool"):
                tool_name = params.pop("tool", list(params.keys())[0] if params else "")
                tool_params = params
                result, error = state.executor.invoke_tool(tool_name, tool_params)
            elif action in ("execute_cmd", "cmd", "command"):
                cmd_str = params.get("cmd", "")
                result, error = state.executor.execute(cmd_str)
            elif action in ("agent_call", "agent", "call_agent"):
                target = params.get("target") or params.get("agent") or params.get("to")
                message = params.get("message", "")
                result, error = run_agent(target, state, pipeline_input=message, **kwargs)
            elif action in ("ai_generate", "ai", "generate", "ask"):
                prompt = params.get("prompt", "")
                from fr_cli.core.stream import stream_cnt
                msgs = [{"role": "user", "content": prompt}]
                result, _, _ = stream_cnt(state.client, state.model_name, msgs, state.lang)
            elif action in ("save_memory", "memory_append"):
                mem = params.get("content", "")
                from fr_cli.agent.manager import save_memory, load_memory
                old = load_memory(name)
                save_memory(name, old + "\n" + mem if old else mem)
                result = "记忆已更新"
            else:
                error = f"未知动作: {action}"
        except Exception as e:
            error = str(e)

        step_results.append({
            "step": step["num"],
            "title": step["title"],
            "action": action,
            "result": result,
            "error": error,
        })

        if error:
            return None, f"步骤 {step['num']} ({step['title']}) 失败: {error}", step_results

    final_result = step_results[-1]["result"] if step_results else None
    return final_result, None, step_results

