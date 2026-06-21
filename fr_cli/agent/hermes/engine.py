"""
Hermes 自治引擎 —— 统一入口

负责任务创建、调度、执行、与 MasterAgent 联动。
"""
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any, Callable, Dict, List, Optional

from fr_cli.conf.paths import HERMES_DIR, HERMES_LOG_FILE
from fr_cli.core.error_ledger import get_error_ledger
from fr_cli.core.stream import stream_cnt

from fr_cli.agent.hermes.managers import (
    HermesAnalytics,
    HermesMemoryStore,
    PersistentGoalTracker,
    PersistentTaskManager,
)
from fr_cli.agent.hermes.models import Goal, Task, TaskPriority, TaskStatus
from fr_cli.agent.hermes.scheduler import HermesScheduler

# 单个 Hermes 后台任务最大执行时间（秒）
DEFAULT_TASK_TIMEOUT = 300


class HermesEngine:
    """Hermes 自治引擎 —— 统一入口"""

    def __init__(self, state_provider: Callable[[], Any]):
        self.state_provider = state_provider
        self.task_manager = PersistentTaskManager()
        self.goal_tracker = PersistentGoalTracker()
        self.memory_store = HermesMemoryStore()
        self.analytics = HermesAnalytics()
        self.scheduler = HermesScheduler(self)
        self.scheduler.start()
        self._daemon: Optional[Any] = None

    # ---------- 日志 ----------
    def _log(self, message: str):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {message}\n"
        try:
            HERMES_DIR.mkdir(parents=True, exist_ok=True)
            with open(HERMES_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass

    def _log_error(self, message: str):
        self._log(f"[ERROR] {message}")

    # ---------- 任务创建 ----------
    def create_task(self, description: str, priority: Any = TaskPriority.NORMAL,
                    scheduled_at: Optional[float] = None, owner: str = "user",
                    task_type: str = "adhoc", source: str = "repl",
                    context: Optional[Dict] = None, execution_mode: str = "sandbox",
                    max_retries: int = 3,
                    confirm_prompt: bool = True) -> Task:
        """
        创建任务。

        当 execution_mode="autonomous" 时，默认会暂停等待用户确认（user_confirmed_at）。
        source="repl" 且 confirm_prompt=True 时会弹窗询问；确认后任务变为 PENDING，
        否则保持 PAUSED。
        """
        user_confirmed_at = None
        initial_status = TaskStatus.PENDING

        if execution_mode == "autonomous":
            if source == "repl" and confirm_prompt:
                from fr_cli.ui.ui import YELLOW, RED, GREEN, RESET
                print(f"{YELLOW}⚠️  即将创建 autonomous 任务：{RESET}")
                print(f"   描述: {description[:80]}")
                print(f"   {RED}该任务将自动执行系统级操作（shell/exec/邮件/MCP 等），不再逐条询问。{RESET}")
                try:
                    c = input(f"{YELLOW}是否确认授权？ [y/N]: {RESET}").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    c = "n"
                if c in ("y", "yes"):
                    user_confirmed_at = time.time()
                    print(f"{GREEN}✅ 已授权，任务将在后台以 autonomous 模式执行。{RESET}")
                else:
                    initial_status = TaskStatus.PAUSED
                    print(f"{YELLOW}⏸️  任务已暂停，可稍后执行 /hermes confirm <id> 授权。{RESET}")
            else:
                # HTTP 或其他非交互来源：默认暂停，等待显式确认
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
        """显式确认某个 autonomous 任务，使其可以执行 full_auto"""
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

    def create_goal(self, description: str, milestones: List[str] = None) -> Goal:
        return self.goal_tracker.create(description, milestones)

    # ---------- 状态查询 ----------
    def get_task(self, task_id: str) -> Optional[Task]:
        return self.task_manager.get(task_id)

    def list_tasks(self, status: Optional[str] = None, limit: Optional[int] = None) -> List[Task]:
        task_status = TaskStatus(status) if status else None
        return self.task_manager.list_tasks(status=task_status, limit=limit)

    def status_report(self) -> str:
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

    # ---------- 任务执行 ----------
    def _execute_task(self, task: Task):
        """执行单个任务：设置环境 → 调用 MasterAgent → 记录结果"""
        state = self.state_provider()
        if state is None:
            self._fail_task(task, "AppState not ready")
            return
        if not getattr(state, "model_name", None):
            self._fail_task(task, "Model not configured")
            return

        # autonomous 任务必须经用户确认，否则降级为 sandbox 执行
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

        # 跨任务记忆：注入相关历史任务摘要
        memory_hints = ""
        if task.context_tags:
            relevant = self.memory_store.find_relevant(task.context_tags, limit=3)
            if relevant:
                lines = ["[历史相关任务]"]
                for rec in relevant:
                    lines.append(f"- {rec['description']}\n  结果摘要: {rec['result_summary']}")
                memory_hints = "\n".join(lines)

        # 任务超时（允许通过环境变量覆盖，默认 300 秒）
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
            task.error = f"执行超时（>{timeout}s）"
            if task.retries >= task.max_retries:
                task.status = TaskStatus.FAILED
                task.completed_at = time.time()
                self.analytics.record_task(False)
                get_error_ledger().record(
                    "hermes_task", task.id, task.description, task.error,
                    metadata={"execution_mode": task.execution_mode, "task_type": task.task_type, "cause": "timeout"}
                )
            else:
                task.status = TaskStatus.PENDING
                # 指数退避，最多 10 分钟
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
                get_error_ledger().record(
                    "hermes_task", task.id, task.description, task.error,
                    metadata={"execution_mode": task.execution_mode, "task_type": task.task_type, "cause": "exception"}
                )
            else:
                task.status = TaskStatus.PENDING
                # 指数退避，最多 10 分钟
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
        get_error_ledger().record(
            "hermes_task", task.id, task.description, error,
            metadata={"execution_mode": task.execution_mode, "task_type": task.task_type}
        )

    # ---------- 子任务 / 目标分解 ----------
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
        """子任务完成回调：若存在父任务，聚合状态"""
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
        """链式任务：当前任务完成后触发下一个"""
        if not task.chain_next:
            return
        next_task = self.task_manager.get(task.chain_next)
        if next_task is None:
            return
        # 立即进入调度
        next_task.scheduled_at = time.time()
        self.task_manager.update(next_task)
        self._log(f"Chain next scheduled: {task.id} -> {next_task.id}")

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
        调用 LLM 将目标分解为若干步骤，创建父任务和线性链接的子任务。
        返回父任务（Goal）对象。
        """
        state = self.state_provider()
        if state is None or not getattr(state, "model_name", None) or not getattr(state, "client", None):
            self._log_error("Cannot decompose goal: state/client/model not ready")
            return None

        prompt = (
            f"请把以下目标拆分为最多 {max_steps} 个具体可执行的步骤。\n"
            f"目标：{description}\n"
            "请只输出 JSON，格式为：{\"steps\": [\"步骤1\", \"步骤2\", ...]}"
        )
        messages = [
            {"role": "system", "content": "你是一个目标分解助手。只输出合法 JSON。"},
            {"role": "user", "content": prompt},
        ]
        try:
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

    def cancel_task(self, task_id: str) -> bool:
        task = self.task_manager.get(task_id)
        if task is None:
            return False
        task.status = TaskStatus.PAUSED
        self.task_manager.update(task)
        self._log(f"Task paused: {task_id}")
        return True

    # ---------- HTTP Daemon ----------
    def start_daemon(self, port: int = 8765, host: str = "127.0.0.1") -> "HermesEngine":
        from fr_cli.agent.hermes_daemon import HermesDaemon
        if self._daemon is not None and getattr(self._daemon, "running", False):
            return self
        self._daemon = HermesDaemon(port=port, host=host, engine=self)
        t = threading.Thread(target=self._daemon.start, daemon=True, name="HermesDaemon")
        t.start()
        self._log(f"Hermes daemon started on {host}:{port}")
        return self

    def stop_daemon(self) -> bool:
        if self._daemon is not None:
            self._daemon.running = False
            self._daemon = None
            self._log("Hermes daemon stopped")
            return True
        return False

    def is_daemon_running(self) -> bool:
        return self._daemon is not None and getattr(self._daemon, "running", False)

    def shutdown(self):
        """完全关闭 Hermes 引擎（停止调度器和守护进程）"""
        self.scheduler.stop()
        self.stop_daemon()
        self._log("Hermes engine shutdown")