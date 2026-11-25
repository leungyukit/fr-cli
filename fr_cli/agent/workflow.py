
"""
Agent workflow engine

v3.1 变更：
- 依赖图按**步骤编号(num)**建表（不再假设步骤号 1..N 连续、也不等于下标+1），
  ``{{stepN.result}}`` 同样按 num 查表；
- 按 DAG **分层并行执行**：同一层（互不依赖）的步骤并行跑，层与层之间串行；
- 步骤失败时保留已成功步骤的结果（``Result.fail(error, data=(final_result, step_results))``）；
- ``_run_with_timeout`` 不再用 ``with ThreadPoolExecutor``，
  改为显式 ``shutdown(wait=False)``，否则 ``with`` 退出会 join 挂起线程，
  墙钟完全不受 timeout 约束。
"""

import concurrent.futures
import re
import threading
from typing import Any, Dict, List, Optional, Sequence, Set

from fr_cli.agent.manager import load_persona, load_memory, load_skills, save_memory
from fr_cli.core.result import Result

WORKFLOW_FILE = "workflow.md"
MAX_WORKFLOW_STEPS = 100

# 单层内最多并行多少个步骤（防止一次性拉起过多线程）
MAX_PARALLEL_STEPS = 8

# 并发安全动作白名单：只有这些动作可以在同一层内并行执行。
#
# 判断依据：
# 1) state.executor（注册表调度 / 安全确认 / 消息回写）**不是线程安全的**，
#    invoke_tool / execute_cmd 会碰它 —— 因此这两类步骤所在的层整体串行；
# 2) agent_call 会执行任意 Agent 代码，Agent 内部随时可能调用 state.executor，
#    同样按"整层串行"处理（否则并发调用会互相踩状态）；
# 3) save_memory 是对 Agent 记忆文件的"读-改-写"，已用独立文件锁保护，
#    但为了保证记忆追加顺序确定，仍按串行处理；
# 4) ai_generate 只发起一次 LLM 补全请求（client 实例并发安全），可并行。
_PARALLEL_SAFE_ACTIONS = {
    "ai_generate", "ai", "generate", "ask",
}

# save_memory 的读-改-写锁（模块级，跨工作流调用同样安全）
_MEMORY_WRITE_LOCK = threading.Lock()


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


def _build_dependency_graph(steps: Sequence[Dict[str, Any]]) -> Dict[int, Set[int]]:
    """根据 {{stepN.result}} / {{stepN.error}} 模板变量构建步骤依赖图。

    返回 ``{步骤编号(num): {依赖步骤编号}}``。

    v3.1 变更：旧实现按下标建图并假设步骤号 1..N 连续（``dep = num - 1``），
    步骤编号有跳跃或从"步骤3"起编时整体错位。现在一律按 num 建表，
    且只保留真实存在的步骤编号（引用不存在的步骤视为无依赖）。
    """
    nums = {s["num"] for s in steps}
    graph: Dict[int, Set[int]] = {s["num"]: set() for s in steps}
    var_pattern = re.compile(r"\{\{\s*step(\d+)\.(result|error)\s*\}\}", re.I)
    for step in steps:
        num = step["num"]
        for val in step.get("params", {}).values():
            for m in var_pattern.finditer(str(val)):
                dep = int(m.group(1))
                if dep != num and dep in nums:
                    graph[num].add(dep)
    return graph


def _detect_cycle(steps):
    """检测工作流步骤间是否存在循环依赖。返回成环的节点**下标**列表，无环返回 None。"""
    graph = _build_dependency_graph(steps)
    index_by_num = {s["num"]: i for i, s in enumerate(steps)}
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {num: WHITE for num in graph}

    def dfs(node, path):
        color[node] = GRAY
        for neighbor in sorted(graph[node]):
            if color[neighbor] == GRAY:
                cycle_start = path.index(neighbor)
                return path[cycle_start:] + [neighbor]
            if color[neighbor] == WHITE:
                res = dfs(neighbor, path + [neighbor])
                if res:
                    return res
        color[node] = BLACK
        return None

    for num in sorted(color):
        if color[num] == WHITE:
            cycle = dfs(num, [num])
            if cycle:
                # 对外仍返回下标（保持既有契约）
                return [index_by_num[n] for n in cycle]
    return None


def _build_layers(steps: Sequence[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """按依赖关系把步骤分层：同一层内步骤互不依赖，可并行执行；层与层之间串行。"""
    graph = _build_dependency_graph(steps)
    pending = {s["num"]: set(graph.get(s["num"], set())) for s in steps}
    done: Set[int] = set()
    layers: List[List[Dict[str, Any]]] = []

    while pending:
        layer = [s for s in steps if s["num"] in pending and pending[s["num"]] <= done]
        if not layer:
            # 理论上环检测已拦截；此处兜底，把剩余步骤放进最后一层避免死循环
            layer = [s for s in steps if s["num"] in pending]
        layers.append(layer)
        for step in layer:
            pending.pop(step["num"], None)
        done.update(s["num"] for s in layer)
    return layers


def _index_steps_by_num(step_results) -> Dict[int, Dict[str, Any]]:
    """把步骤结果转成 ``{步骤编号: 结果dict}``。

    兼容两种形态：
    - dict：已经是 num 索引
    - list：结果 dict 列表（每项含 "step" 键表示编号）
    """
    if isinstance(step_results, dict):
        return step_results
    indexed: Dict[int, Dict[str, Any]] = {}
    for entry in step_results or []:
        if isinstance(entry, dict) and "step" in entry:
            indexed[int(entry["step"])] = entry
    return indexed


def _resolve_var(var_expr, context, step_results, user_input):
    """解析模板变量，如 {{step1.result}} {{user_input}}

    v3.1 变更：``{{stepN.result}}`` / ``{{stepN.error}}`` 按**步骤编号**查表，
    不再把 N 当下标（步骤编号可以不连续）。
    """
    var_expr = var_expr.strip()
    if var_expr == "user_input":
        return user_input or ""
    if var_expr == "agent.persona":
        return context.get("persona", "")
    if var_expr == "agent.memory":
        return context.get("memory", "")
    if var_expr == "agent.skills":
        return context.get("skills", "")
    by_num = _index_steps_by_num(step_results)
    sm = re.match(r"step(\d+)\.result", var_expr, re.I)
    if sm:
        entry = by_num.get(int(sm.group(1)))
        if entry is not None:
            return str(entry.get("result", ""))
    sm = re.match(r"step(\d+)\.error", var_expr, re.I)
    if sm:
        entry = by_num.get(int(sm.group(1)))
        if entry is not None:
            return str(entry.get("error", ""))
    return "{" + var_expr + "}"


def _substitute_vars(text, context, step_results, user_input):
    """替换文本中的所有 {{var}} 模板变量"""
    if not isinstance(text, str):
        return text
    def repl(m):
        return _resolve_var(m.group(1), context, step_results, user_input)
    return re.sub(r"\{\{([^}]+)\}\}", repl, text)


def _run_with_timeout(func, timeout):
    """执行函数并设置超时；timeout 为 None 或 <=0 时不限制。

    v3.1 变更：旧实现用 ``with ThreadPoolExecutor(max_workers=1)``，
    退出时 ``shutdown(wait=True)`` 会阻塞到挂起任务真正结束 ——
    实测 timeout=0.1s + sleep 1.0s 的墙钟仍是 1.005s，超时形同虚设。
    现在改用显式 executor + ``shutdown(wait=False)``，超时立即返回。

    诚实边界：Python 无法强杀线程，超时后任务线程仍会继续跑完。
    """
    if timeout is None or timeout <= 0:
        return func()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(func)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise WorkflowTimeoutError(f"步骤执行超时（{timeout:g}秒）")
    finally:
        executor.shutdown(wait=False)


def _is_parallel_safe(action: str) -> bool:
    """判断该 action 能否在同一层内与其他步骤并发执行（判断依据见 _PARALLEL_SAFE_ACTIONS）。"""
    return str(action).strip().lower() in _PARALLEL_SAFE_ACTIONS


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
                source="workflow",
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
            # 读-改-写整体加锁，避免同层并发写同一份记忆文件时丢内容
            with _MEMORY_WRITE_LOCK:
                old = load_memory(name)
                save_memory(name, old + "\n" + mem if old else mem)
            return Result.ok("记忆已更新")
        else:
            return Result.fail(f"未知动作: {action}")
    except Exception as e:
        return Result.fail(str(e))


def _parse_int_param(raw, default: int = 0) -> int:
    """把参数字符串安全地转成 int（非法值退回默认值）。"""
    try:
        return int(str(raw).strip() or default)
    except (TypeError, ValueError):
        return default


def _parse_float_param(raw) -> Optional[float]:
    """把参数字符串安全地转成 float（非法值返回 None）。"""
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _run_single_step(step, context, state, name, user_input, kwargs, results_by_num):
    """执行单个步骤（含重试语义），返回步骤结果 dict。"""
    action = step["action"]
    params = {k: _substitute_vars(v, context, results_by_num, user_input)
              for k, v in step["params"].items()}
    retry_count = max(0, _parse_int_param(params.pop("retry_count", "0"), 0))
    step_timeout = _parse_float_param(params.pop("timeout", None))

    step_result = None
    attempt = 0
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

    return {
        "step": step["num"],
        "title": step["title"],
        "action": action,
        "result": step_result.unwrap() if step_result.is_ok() else None,
        "error": step_result.error if step_result.is_fail() else None,
        "attempts": attempt + 1,
    }


def _run_layer(layer: List[Dict[str, Any]], execute_one) -> List[Dict[str, Any]]:
    """执行同一层的步骤。

    并发策略：只有当层内**全部**步骤都是并发安全动作时才并行；
    否则整层串行（保守退化，避免 state.executor 被并发调用）。
    """
    if len(layer) == 1 or not all(_is_parallel_safe(s["action"]) for s in layer):
        # 串行层：保持原有"遇到失败即停"的语义
        results: List[Dict[str, Any]] = []
        for step in layer:
            entry = execute_one(step)
            results.append(entry)
            if entry.get("error"):
                break
        return results

    workers = min(len(layer), MAX_PARALLEL_STEPS)
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    results = []
    try:
        futures = {executor.submit(execute_one, step): step for step in layer}
        for future in concurrent.futures.as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                step = futures[future]
                results.append({
                    "step": step["num"],
                    "title": step["title"],
                    "action": step["action"],
                    "result": None,
                    "error": str(e),
                    "attempts": 1,
                })
    finally:
        # 不等待挂起线程：层内步骤自带 timeout，层本身不再额外阻塞
        executor.shutdown(wait=False)
    return results


def run_workflow(name, state, user_input=None, **kwargs):
    """执行 Agent 的工作流。返回 Result[(final_result, step_results)]

    v3.1 变更：按 DAG 分层并行执行；步骤失败时保留已成功步骤的结果
    （``Result.fail(error, data=(final_result, step_results))``）。
    """
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

    # 按步骤编号(num)落位，保证 {{stepN.result}} 取到的是 num==N 的那一步
    results_by_num: Dict[int, Dict[str, Any]] = {}
    results_lock = threading.Lock()
    ordered_results: List[Dict[str, Any]] = []
    last_success: Any = None

    for layer in _build_layers(steps):
        # 层内步骤只依赖更早的层，故用快照做模板变量查表（避免并发读写同一 dict）
        with results_lock:
            snapshot = dict(results_by_num)

        def _execute_one(step, _snapshot=snapshot):
            entry = _run_single_step(step, context, state, name, user_input, kwargs, _snapshot)
            with results_lock:
                results_by_num[entry["step"]] = entry
            return entry

        layer_entries = _run_layer(layer, _execute_one)
        # 同层结果按步骤编号排序，保证整体顺序稳定
        with results_lock:
            for entry in layer_entries:
                results_by_num[entry["step"]] = entry
            ordered_results = [results_by_num[num] for num in sorted(results_by_num)]

        failed = next((e for e in layer_entries if e.get("error")), None)
        if failed is not None:
            # 保留已成功步骤的结果（部分失败语义）
            for entry in ordered_results:
                if entry.get("error") is None and entry.get("result") is not None:
                    last_success = entry["result"]
            return Result.fail(
                f"步骤 {failed['step']} ({failed['title']}) 失败: {failed['error']}",
                data=(last_success, ordered_results),
            )

        for entry in layer_entries:
            if entry.get("error") is None:
                last_success = entry["result"]

    final_result = last_success
    return Result.ok((final_result, ordered_results))
