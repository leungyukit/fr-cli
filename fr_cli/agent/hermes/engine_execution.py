"""
HermesEngine 执行 mixin —— 任务执行内部逻辑

负责:
- _execute_task:实际跑任务(设置环境 → MasterAgent → 记录结果)
- _fail_task:任务失败处理
- _dependencies_satisfied:依赖检查
- _has_cycle:循环依赖检测(DFS)
- _on_child_completed:子任务完成回调(聚合到父任务)
- _schedule_chain_next:链式调度
"""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Optional

from fr_cli.agent.hermes.models import Task, TaskStatus


# 单个 Hermes 后台任务最大执行时间(秒)
DEFAULT_TASK_TIMEOUT = 300


class HermesEngineExecutionMixin:
    """HermesEngine 执行内部逻辑"""

    def _execute_task(self, task: Task):
        """执行单个任务:设置环境 → 调用 MasterAgent → 记录结果"""
        state = self.state_provider()
        if state is None:
            self._fail_task(task, "AppState not ready")
            return
        if not getattr(state, "model_name", None):
            self._fail_task(task, "Model not configured")
            return

        # autonomous 任务必须经用户确认,否则降级为 sandbox 执行
        effective_mode = task.execution_mode
        if effective_mode == "autonomous" and task.user_confirmed_at is None:
            self._log(f"Task {task.id} autonomous mode not confirmed, downgrade to sandbox")
            effective_mode = "sandbox"

        # 更新状态
        task.status = TaskStatus.RUNNING
        task.started_at = time.time()
        self.task_manager.update(task)

        # 设置执行环境
        env_backup = {}
        if effective_mode == "sandbox":
            env_backup["FR_CLI_AUTONOMOUS_MODE"] = os.environ.get("FR_CLI_AUTONOMOUS_MODE")
            os.environ["FR_CLI_AUTONOMOUS_MODE"] = "sandbox_auto"
            env_backup["FR_CLI_NON_INTERACTIVE"] = os.environ.get("FR_CLI_NON_INTERACTIVE")
            os.environ["FR_CLI_NON_INTERACTIVE"] = "1"
        elif effective_mode == "autonomous":
            env_backup["FR_CLI_AUTONOMOUS_MODE"] = os.environ.get("FR_CLI_AUTONOMOUS_MODE")
            os.environ["FR_CLI_AUTONOMOUS_MODE"] = "full_auto"
            env_backup["FR_CLI_NON_INTERACTIVE"] = os.environ.get("FR_CLI_NON_INTERACTIVE")
            os.environ["FR_CLI_NON_INTERACTIVE"] = "1"
        # interactive 模式不修改环境变量

        # 隔离用户主会话
        saved_messages = getattr(state, "messages", None)
        context_messages = []

        # 跨任务记忆:注入相关历史任务摘要
        memory_hints = ""
        if task.context_tags:
            relevant = self.memory_store.find_relevant(task.context_tags, limit=3)
            if relevant:
                lines = ["[历史相关任务]"]
                for rec in relevant:
                    lines.append(f"- {rec['description']}\n  结果摘要: {rec['result_summary']}")
                memory_hints = "\n".join(lines)

        # 任务超时(允许通过环境变量覆盖,默认 300 秒)
        try:
            timeout = float(os.environ.get("FR_CLI_HERMES_TASK_TIMEOUT", DEFAULT_TASK_TIMEOUT))
        except Exception:
            timeout = DEFAULT_TASK_TIMEOUT

        executor = ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(
                state.master_agent.handle,
                task.description,
                context_messages=context_messages,
                background=True,
                memory_hints=memory_hints,
            )
            reply, _ = future.result(timeout=timeout)
            task.result = str(reply)[:4000] if reply is not None else ""
            task.status = TaskStatus.COMPLETED
            task.completed_at = time.time()
            self.analytics.record_task(True)
            self._log(f"Task completed: {task.id}")
            # 记录到跨任务记忆
            self.memory_store.record(
                task.id, task.description, task.result or "", task.context_tags
            )
            self._schedule_chain_next(task)
            self._on_child_completed(task)
        except FutureTimeoutError:
            self._log_error(f"Task {task.id} timed out after {timeout}s")
            task.retries += 1
            task.error = f"执行超时(>{timeout}s)"
            if task.retries >= task.max_retries:
                task.status = TaskStatus.FAILED
                task.completed_at = time.time()
                self.analytics.record_task(False)
                from fr_cli.core.error_ledger import get_error_ledger
                get_error_ledger().record(
                    "hermes_task", task.id, task.description, task.error,
                    metadata={"execution_mode": task.execution_mode, "task_type": task.task_type, "cause": "timeout"}
                )
            else:
                task.status = TaskStatus.PENDING
                # 指数退避,最多 10 分钟
                backoff = min(2 ** task.retries, 600)
                task.scheduled_at = time.time() + backoff
                self._log(f"Task {task.id} will retry in {backoff}s (retry {task.retries}/{task.max_retries})")
        except Exception as e:
            self._log_error(f"Task {task.id} failed: {e}")
            task.retries += 1
            task.error = str(e)[:1000]
            if task.retries >= task.max_retries:
                task.status = TaskStatus.FAILED
                task.completed_at = time.time()
                self.analytics.record_task(False)
                from fr_cli.core.error_ledger import get_error_ledger
                get_error_ledger().record(
                    "hermes_task", task.id, task.description, task.error,
                    metadata={"execution_mode": task.execution_mode, "task_type": task.task_type, "cause": "exception"}
                )
            else:
                task.status = TaskStatus.PENDING
                # 指数退避,最多 10 分钟
                backoff = min(2 ** task.retries, 600)
                task.scheduled_at = time.time() + backoff
                self._log(f"Task {task.id} will retry in {backoff}s (retry {task.retries}/{task.max_retries})")
        finally:
            executor.shutdown(wait=False)
            # 恢复环境变量
            for k, v in env_backup.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            # 恢复用户会话
            if saved_messages is not None:
                state.messages = saved_messages
            self.task_manager.update(task)

    def _fail_task(self, task: Task, error: str):
        task.status = TaskStatus.FAILED
        task.error = error
        task.completed_at = time.time()
        self.task_manager.update(task)
        self.analytics.record_task(False)
        self._log_error(f"Task {task.id} failed permanently: {error}")
        from fr_cli.core.error_ledger import get_error_ledger
        get_error_ledger().record(
            "hermes_task", task.id, task.description, error,
            metadata={"execution_mode": task.execution_mode, "task_type": task.task_type}
        )

    def _dependencies_satisfied(self, task: Task) -> bool:
        """检查任务的所有依赖是否已完成"""
        for dep_id in task.dependencies:
            dep = self.task_manager.get(dep_id)
            if dep is None or dep.status != TaskStatus.COMPLETED:
                return False
        return True

    def _has_cycle(self, task_id: str, visited: Optional[set] = None) -> bool:
        """基于 dependencies 的 DFS 环检测"""
        if visited is None:
            visited = set()
        if task_id in visited:
            return True
        task = self.task_manager.get(task_id)
        if task is None:
            return False
        visited.add(task_id)
        for dep_id in task.dependencies:
            if self._has_cycle(dep_id, visited.copy()):
                return True
        return False

    def _on_child_completed(self, child: Task):
        """子任务完成回调:若存在父任务,聚合状态"""
        if not child.parent_id:
            return
        parent = self.task_manager.get(child.parent_id)
        if parent is None:
            return
        if child.status == TaskStatus.FAILED:
            self._fail_task(parent, f"子任务 {child.id} 失败")
            return
        # 检查是否所有子任务都已完成
        all_completed = True
        for cid in parent.children_ids:
            sibling = self.task_manager.get(cid)
            if sibling is None or sibling.status != TaskStatus.COMPLETED:
                all_completed = False
                break
        if all_completed:
            parent.status = TaskStatus.COMPLETED
            parent.completed_at = time.time()
            self.task_manager.update(parent)
            self.analytics.record_task(True)
            self._log(f"Goal completed: {parent.id}")

    def _schedule_chain_next(self, task: Task):
        """链式任务:当前任务完成后触发下一个"""
        if not task.chain_next:
            return
        next_task = self.task_manager.get(task.chain_next)
        if next_task is None:
            return
        # 立即进入调度
        next_task.scheduled_at = time.time()
        self.task_manager.update(next_task)
        self._log(f"Chain next scheduled: {task.id} -> {next_task.id}")
