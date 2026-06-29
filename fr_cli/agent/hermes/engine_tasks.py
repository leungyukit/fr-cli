"""
HermesEngine 任务 / 目标 CRUD + 状态查询 mixin

负责:
- create_task / confirm_task / cancel_task:任务生命周期
- create_goal / decompose_goal:目标创建与 LLM 分解
- create_subtask:为父任务创建子任务
- get_task / list_tasks:查询
- status_report:人类可读状态报告
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from fr_cli.agent.hermes.models import Goal, Task, TaskPriority, TaskStatus

# 顶层 import:供测试 monkeypatch 目标(测试 patch fr_cli.agent.hermes.engine_tasks.stream_cnt)
from fr_cli.core.stream import stream_cnt  # noqa: F401


class HermesEngineTaskMixin:
    """HermesEngine 任务 / 目标 CRUD + 状态查询"""

    # ---------- 任务创建 ----------

    def create_task(self, description: str, priority: Any = TaskPriority.NORMAL,
                    scheduled_at: Optional[float] = None, owner: str = "user",
                    task_type: str = "adhoc", source: str = "repl",
                    context: Optional[Dict] = None, execution_mode: str = "sandbox",
                    max_retries: int = 3,
                    confirm_prompt: bool = True) -> Task:
        """
        创建任务。

        当 execution_mode="autonomous" 时,默认会暂停等待用户确认(user_confirmed_at)。
        source="repl" 且 confirm_prompt=True 时会弹窗询问;确认后任务变为 PENDING,
        否则保持 PAUSED。
        """
        user_confirmed_at = None
        initial_status = TaskStatus.PENDING

        if execution_mode == "autonomous":
            if source == "repl" and confirm_prompt:
                from fr_cli.ui.ui import YELLOW, RED, GREEN, RESET
                print(f"{YELLOW}⚠️  即将创建 autonomous 任务:{RESET}")
                print(f"   描述: {description[:80]}")
                print(f"   {RED}该任务将自动执行系统级操作(shell/exec/邮件/MCP 等),不再逐条询问。{RESET}")
                try:
                    c = input(f"{YELLOW}是否确认授权? [y/N]: {RESET}").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    c = "n"
                if c in ("y", "yes"):
                    user_confirmed_at = time.time()
                    print(f"{GREEN}✅ 已授权,任务将在后台以 autonomous 模式执行。{RESET}")
                else:
                    initial_status = TaskStatus.PAUSED
                    print(f"{YELLOW}⏸️  任务已暂停,可稍后执行 /hermes confirm <id> 授权。{RESET}")
            else:
                # HTTP 或其他非交互来源:默认暂停,等待显式确认
                initial_status = TaskStatus.PAUSED

        task = self.task_manager.create(
            description=description,
            priority=priority,
            scheduled_at=scheduled_at,
            owner=owner,
            task_type=task_type,
            source=source,
            context=context,
            execution_mode=execution_mode,
            max_retries=max_retries,
            user_confirmed_at=user_confirmed_at,
        )
        if initial_status != TaskStatus.PENDING:
            task.status = initial_status
            self.task_manager.update(task)
        self._log(f"Task created: {task.id} [{task.priority.name}] {task.execution_mode}] {task.description[:60]}")
        return task

    def confirm_task(self, task_id: str) -> bool:
        """显式确认某个 autonomous 任务,使其可以执行 full_auto"""
        task = self.task_manager.get(task_id)
        if task is None:
            return False
        if task.execution_mode != "autonomous":
            return False
        task.user_confirmed_at = time.time()
        if task.status == TaskStatus.PAUSED:
            task.status = TaskStatus.PENDING
        self.task_manager.update(task)
        self._log(f"Task confirmed: {task.id}")
        return True

    def cancel_task(self, task_id: str) -> bool:
        """暂停任务(不是真删除,只是设为 PAUSED)"""
        task = self.task_manager.get(task_id)
        if task is None:
            return False
        task.status = TaskStatus.PAUSED
        self.task_manager.update(task)
        self._log(f"Task paused: {task_id}")
        return True

    # ---------- 目标 ----------

    def create_goal(self, description: str, milestones: List[str] = None) -> Goal:
        return self.goal_tracker.create(description, milestones)

    # ---------- 子任务 ----------

    def create_subtask(self, parent_id: str, description: str,
                       priority: Any = TaskPriority.NORMAL,
                       execution_mode: str = "sandbox",
                       context: Optional[Dict] = None,
                       context_tags: Optional[List[str]] = None) -> Optional[Task]:
        """为父任务创建一个 goal_step 子任务"""
        parent = self.task_manager.get(parent_id)
        if parent is None:
            return None
        child = self.task_manager.create(
            description=description,
            priority=priority,
            task_type="goal_step",
            source="repl",
            context=context or {},
            execution_mode=execution_mode,
            parent_id=parent_id,
            context_tags=context_tags or [],
        )
        parent.children_ids.append(child.id)
        self.task_manager.update(parent)
        self._log(f"Subtask created: {parent.id} -> {child.id}")
        return child

    def decompose_goal(self, description: str, execution_mode: str = "sandbox",
                       context: Optional[Dict] = None,
                       context_tags: Optional[List[str]] = None,
                       max_steps: int = 8) -> Optional[Task]:
        """
        调用 LLM 将目标分解为若干步骤,创建父任务和线性链接的子任务。
        返回父任务(Goal)对象。
        """
        state = self.state_provider()
        if (state is None or not getattr(state, "model_name", None)
                or not getattr(state, "client", None)):
            self._log_error("Cannot decompose goal: state/client/model not ready")
            return None

        prompt = (
            f"请把以下目标拆分为最多 {max_steps} 个具体可执行的步骤。\n"
            f"目标:{description}\n"
            "请只输出 JSON,格式为:{\"steps\": [\"步骤1\", \"步骤2\", ...]}"
        )
        messages = [
            {"role": "system", "content": "你是一个目标分解助手。只输出合法 JSON。"},
            {"role": "user", "content": prompt},
        ]
        try:
            # 通过 engine 模块调用 stream_cnt,让 monkeypatch 能命中
            import sys
            engine_mod = sys.modules.get("fr_cli.agent.hermes.engine") or sys.modules.get(
                "fr_cli.agent.hermes.engine_tasks"
            )
            stream_cnt = getattr(engine_mod, "stream_cnt", None)
            if stream_cnt is None:
                from fr_cli.core.stream import stream_cnt
            reply, _, _, _ = stream_cnt(
                state.client,
                state.model_name,
                messages,
                lang=getattr(state, "lang", "zh"),
                silent=True,
            )
            data = json.loads(reply)
            steps = data.get("steps", [])
            if not isinstance(steps, list) or not steps:
                raise ValueError("LLM did not return valid steps")
        except Exception as e:
            self._log_error(f"Goal decomposition failed: {e}")
            return None

        parent = self.task_manager.create(
            description=description,
            task_type="goal",
            source="repl",
            context=context or {},
            execution_mode=execution_mode,
            context_tags=context_tags or [],
        )

        prev_child_id = None
        for step_desc in steps:
            child = self.task_manager.create(
                description=step_desc,
                task_type="goal_step",
                source="repl",
                context=context or {},
                execution_mode=execution_mode,
                parent_id=parent.id,
                chain_next=None,
                context_tags=context_tags or [],
            )
            parent.children_ids.append(child.id)
            if prev_child_id:
                prev_child = self.task_manager.get(prev_child_id)
                if prev_child:
                    prev_child.chain_next = child.id
                    self.task_manager.update(prev_child)
            prev_child_id = child.id
            self.task_manager.update(child)
        self.task_manager.update(parent)

        # 让第一个子任务可立即调度
        if parent.children_ids:
            first = self.task_manager.get(parent.children_ids[0])
            if first:
                first.scheduled_at = time.time()
                self.task_manager.update(first)

        self._log(f"Goal decomposed: {parent.id} into {len(parent.children_ids)} steps")
        return parent

    # ---------- 查询 ----------

    def get_task(self, task_id: str) -> Optional[Task]:
        return self.task_manager.get(task_id)

    def list_tasks(self, status: Optional[str] = None,
                   limit: Optional[int] = None) -> List[Task]:
        task_status = TaskStatus(status) if status else None
        return self.task_manager.list_tasks(status=task_status, limit=limit)

    def status_report(self) -> str:
        """人类可读的状态报告"""
        counts = self.task_manager.counts()
        stats = self.analytics.get_stats()
        lines = [
            "📊 Hermes 状态",
            f"  任务: pending={counts['pending']} running={counts['running']} "
            f"completed={counts['completed']} failed={counts['failed']} paused={counts['paused']}",
            f"  调度器: {'运行中' if self.scheduler.running else '已停止'}",
            f"  成功率: {stats['success_rate']*100:.1f}%",
            f"  运行时长: {stats['uptime_seconds']:.0f} 秒",
        ]
        return "\n".join(lines)
