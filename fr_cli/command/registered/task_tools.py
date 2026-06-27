"""
注册表分组:Hermes / 任务管理工具

- task_output: 查询 Hermes 后台任务的状态/输出(Claude Code 风格)
- spawn_agent: 启动子 Agent 处理子任务(MasterAgent 委派机制)
"""
from fr_cli.command.registry import register


@register(
    name="task_output",
    triggers=["任务输出", "后台任务", "task output", "查任务"],
    description="查询 Hermes 后台任务的最新输出/状态",
    params={"task_id": str, "wait": bool, "max_wait_seconds": int},
    aliases=["/task_output"],
)
def _task_output(deps, **kwargs):
    """查 Hermes 后台任务输出。

    Args:
        task_id: 任务 ID
        wait: 是否阻塞等待任务完成
        max_wait_seconds: 等待的最长时间(秒)
    """
    task_id = kwargs.get("task_id", "").strip()
    wait = bool(kwargs.get("wait", False))
    try:
        max_wait = int(kwargs.get("max_wait_seconds", 30))
    except (ValueError, TypeError):
        max_wait = 30

    if not task_id:
        from fr_cli.core.result import Result
        return Result.fail("需要提供 task_id")

    state = deps.state
    hermes = getattr(state, "hermes", None)
    if hermes is None:
        from fr_cli.core.result import Result
        return Result.fail("Hermes 引擎未初始化")

    try:
        task = hermes.get_task(task_id)
        if task is None:
            from fr_cli.core.result import Result
            return Result.fail(f"任务不存在: {task_id}")

        if wait and task.status.value in ("pending", "running"):
            import time
            start = time.time()
            while time.time() - start < max_wait:
                time.sleep(0.5)
                task = hermes.get_task(task_id) or task
                if task.status.value in ("completed", "failed", "paused", "cancelled"):
                    break

        from fr_cli.core.result import Result
        out = (
            f"任务 ID: {task.id}\n"
            f"描述: {task.description}\n"
            f"状态: {task.status.value}\n"
            f"执行模式: {task.execution_mode}\n"
            f"创建时间: {task.created_at}\n"
        )
        if task.started_at:
            out += f"开始时间: {task.started_at}\n"
        if task.completed_at:
            out += f"完成时间: {task.completed_at}\n"
        if hasattr(task, "result") and task.result:
            out += f"\n--- 结果 ---\n{task.result}\n"
        if hasattr(task, "error") and task.error:
            out += f"\n--- 错误 ---\n{task.error}\n"
        return Result.ok(out)
    except Exception as e:
        from fr_cli.core.result import Result
        return Result.fail(f"查询任务失败: {e}")


@register(
    name="spawn_agent",
    triggers=["派生子任务", "spawn agent", "启动子agent", "子任务"],
    description="启动一个独立的子 Agent 来处理子任务(可并发),返回任务 ID",
    params={"description": str, "agent_type": str, "execution_mode": str},
    security="sec_exec",
    aliases=["/spawn_agent"],
)
def _spawn_agent(deps, **kwargs):
    """派生子 Agent 处理子任务。

    Args:
        description: 子任务描述
        agent_type: 子 Agent 类型(builtin:local / builtin:spider 等)
        execution_mode: 执行模式(sandbox / autonomous)
    """
    description = kwargs.get("description", "").strip()
    agent_type = kwargs.get("agent_type", "builtin:local")
    execution_mode = kwargs.get("execution_mode", "sandbox")

    if not description:
        from fr_cli.core.result import Result
        return Result.fail("需要提供任务描述 description")

    state = deps.state
    hermes = getattr(state, "hermes", None)
    if hermes is None:
        from fr_cli.core.result import Result
        return Result.fail("Hermes 引擎未初始化")

    try:
        # 通过 hermes 创建任务
        task = hermes.create_task(
            description=description,
            source="spawn_agent",
            execution_mode=execution_mode,
            agent_type=agent_type,
        )
        from fr_cli.core.result import Result
        return Result.ok({
            "task_id": task.id,
            "status": task.status.value,
            "execution_mode": task.execution_mode,
            "message": f"已派生子 Agent 任务: {task.id}",
        })
    except Exception as e:
        from fr_cli.core.result import Result
        return Result.fail(f"派生子 Agent 失败: {e}")


@register(
    name="list_background_tasks",
    triggers=["后台任务列表", "查任务", "list tasks"],
    description="列出所有后台任务(pending/running/completed/failed)",
    params={"status_filter": str, "limit": int},
    aliases=["/list_tasks"],
)
def _list_background_tasks(deps, **kwargs):
    """列出后台任务"""
    status_filter = kwargs.get("status_filter") or None
    try:
        limit = int(kwargs.get("limit", 20))
    except (ValueError, TypeError):
        limit = 20

    state = deps.state
    hermes = getattr(state, "hermes", None)
    if hermes is None:
        from fr_cli.core.result import Result
        return Result.fail("Hermes 引擎未初始化")

    try:
        tasks = hermes.list_tasks(status=status_filter, limit=limit)
        if not tasks:
            return __import__("fr_cli.core.result", fromlist=["Result"]).Result.ok("暂无后台任务")

        lines = [f"后台任务 (共 {len(tasks)} 个):"]
        for t in tasks[:limit]:
            marker = {
                "pending": "⏳",
                "running": "🏃",
                "completed": "✅",
                "failed": "❌",
                "paused": "⏸️",
            }.get(t.status.value, "?")
            desc = t.description[:50]
            lines.append(f"  {marker} {t.id} | {t.status.value:<10} | {desc}")
        return __import__("fr_cli.core.result", fromlist=["Result"]).Result.ok("\n".join(lines))
    except Exception as e:
        return __import__("fr_cli.core.result", fromlist=["Result"]).Result.fail(f"列出任务失败: {e}")
