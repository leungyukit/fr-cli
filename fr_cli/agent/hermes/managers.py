"""
Hermes 持久化管理器 —— 任务队列、目标追踪、记忆、统计

每个管理器负责一项独立职责，共享 JsonStore 抽象与线程安全模式。
"""
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fr_cli.core.store import JsonStore
from fr_cli.conf.paths import (
    HERMES_TASKS_FILE,
    HERMES_GOALS_FILE,
    HERMES_ANALYTICS_FILE,
    HERMES_MEMORY_FILE,
)

from fr_cli.agent.hermes.models import (
    Goal,
    Task,
    TaskPriority,
    TaskStatus,
    new_goal_id,
    new_task_id,
)


class PersistentTaskManager:
    """持久化任务管理器 —— Hermes 核心"""

    def __init__(self, store_path: Optional[Path] = None):
        self._store = JsonStore(store_path or HERMES_TASKS_FILE, default=list)
        self._lock = threading.RLock()
        self.tasks: Dict[str, Task] = {}
        self._load()

    def _load(self):
        raw_list = self._store.read()
        for raw in raw_list:
            try:
                task = Task.from_dict(raw)
                self.tasks[task.id] = task
            except Exception:
                continue

    def _persist(self):
        with self._lock:
            data = [t.to_dict() for t in self.tasks.values()]
            self._store.write(data)

    def create(self, description: str, priority: Any = TaskPriority.NORMAL,
               scheduled_at: Optional[float] = None, owner: str = "user",
               task_type: str = "adhoc", source: str = "repl",
               context: Optional[Dict] = None, execution_mode: str = "sandbox",
               max_retries: int = 3,
               user_confirmed_at: Optional[float] = None,
               parent_id: Optional[str] = None,
               dependencies: Optional[List[str]] = None,
               children_ids: Optional[List[str]] = None,
               chain_next: Optional[str] = None,
               context_tags: Optional[List[str]] = None) -> Task:
        """创建任务"""
        if isinstance(priority, str):
            priority = TaskPriority[priority.upper()]
        task = Task(
            id=new_task_id(),
            description=description,
            priority=priority,
            scheduled_at=scheduled_at,
            owner=owner,
            task_type=task_type,
            source=source,
            context=context or {},
            execution_mode=execution_mode,
            max_retries=max_retries,
            user_confirmed_at=user_confirmed_at,
            parent_id=parent_id,
            dependencies=dependencies or [],
            children_ids=children_ids or [],
            chain_next=chain_next,
            context_tags=context_tags or [],
        )
        with self._lock:
            self.tasks[task.id] = task
        self._persist()
        return task

    def get(self, task_id: str) -> Optional[Task]:
        return self.tasks.get(task_id)

    def update(self, task: Task):
        with self._lock:
            self.tasks[task.id] = task
        self._persist()

    def list_tasks(self, status: Optional[TaskStatus] = None,
                   limit: Optional[int] = None) -> List[Task]:
        tasks = list(self.tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        # 优先级降序，同优先级按创建时间升序
        tasks.sort(key=lambda t: (-t.priority.value, t.created_at))
        return tasks[:limit] if limit else tasks

    def delete(self, task_id: str) -> bool:
        with self._lock:
            if task_id in self.tasks:
                del self.tasks[task_id]
        self._persist()
        return True

    def counts(self) -> Dict[str, int]:
        counts = {"pending": 0, "running": 0, "completed": 0, "failed": 0, "paused": 0}
        for t in self.tasks.values():
            counts[t.status.value] = counts.get(t.status.value, 0) + 1
        return counts


class PersistentGoalTracker:
    """持久化目标追踪器"""

    def __init__(self, store_path: Optional[Path] = None):
        self._store = JsonStore(store_path or HERMES_GOALS_FILE, default=list)
        self._lock = threading.RLock()
        self.goals: Dict[str, Goal] = {}
        self._load()

    def _load(self):
        for raw in self._store.read():
            try:
                goal = Goal.from_dict(raw)
                self.goals[goal.id] = goal
            except Exception:
                continue

    def _persist(self):
        with self._lock:
            self._store.write([g.to_dict() for g in self.goals.values()])

    def create(self, description: str, milestones: List[str] = None) -> Goal:
        goal = Goal(id=new_goal_id(), description=description, milestones=milestones or [])
        with self._lock:
            self.goals[goal.id] = goal
        self._persist()
        return goal

    def get(self, goal_id: str) -> Optional[Goal]:
        return self.goals.get(goal_id)

    def update(self, goal: Goal):
        with self._lock:
            self.goals[goal.id] = goal
        self._persist()

    def list_goals(self, status: Optional[TaskStatus] = None) -> List[Goal]:
        goals = list(self.goals.values())
        if status:
            goals = [g for g in goals if g.status == status]
        return sorted(goals, key=lambda g: g.created_at, reverse=True)


class HermesMemoryStore:
    """跨任务记忆存储：记录已完成任务的摘要与标签，供相似任务继承上下文。"""

    def __init__(self, store_path: Optional[Path] = None):
        self._store = JsonStore(store_path or HERMES_MEMORY_FILE, default=list)
        self._lock = threading.RLock()
        self.records: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        self.records = self._store.read() or []

    def _persist(self):
        with self._lock:
            # 最多保留 200 条记录
            self.records = self.records[-200:]
            self._store.write(self.records)

    def record(self, task_id: str, description: str, result_summary: str, tags: Optional[List[str]] = None):
        with self._lock:
            self.records.append({
                "task_id": task_id,
                "description": description[:200],
                "result_summary": result_summary[:300],
                "tags": list(tags or []),
                "created_at": time.time(),
            })
        self._persist()

    def find_relevant(self, tags: List[str], limit: int = 3) -> List[Dict[str, Any]]:
        if not tags:
            return []
        tag_set = set(tags)
        scored = []
        for rec in self.records:
            overlap = len(tag_set & set(rec.get("tags", [])))
            if overlap:
                scored.append((overlap, rec.get("created_at", 0), rec))
        scored.sort(key=lambda x: (-x[0], -x[1]))
        return [rec for _, _, rec in scored[:limit]]


class HermesAnalytics:
    """Hermes 统计（内存 + 可选持久化）"""

    def __init__(self, store_path: Optional[Path] = None):
        self._store = JsonStore(store_path or HERMES_ANALYTICS_FILE, default=dict)
        self._lock = threading.RLock()
        self.stats = self._store.read()
        defaults = {
            "total_requests": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "successful_tasks": 0,
            "failed_tasks": 0,
            "models_used": {},
            "start_time": time.time(),
        }
        for k, v in defaults.items():
            self.stats.setdefault(k, v)

    def record_request(self, model: str, tokens: int, cost: float):
        with self._lock:
            self.stats["total_requests"] += 1
            self.stats["total_tokens"] += tokens
            self.stats["total_cost"] += cost
            if model not in self.stats["models_used"]:
                self.stats["models_used"][model] = {"requests": 0, "tokens": 0}
            self.stats["models_used"][model]["requests"] += 1
            self.stats["models_used"][model]["tokens"] += tokens
            self._store.write(self.stats)

    def record_task(self, success: bool):
        with self._lock:
            if success:
                self.stats["successful_tasks"] += 1
            else:
                self.stats["failed_tasks"] += 1
            self._store.write(self.stats)

    def get_stats(self) -> Dict:
        with self._lock:
            uptime = time.time() - self.stats["start_time"]
            total = self.stats["successful_tasks"] + self.stats["failed_tasks"]
            return {
                **self.stats,
                "uptime_seconds": uptime,
                "success_rate": self.stats["successful_tasks"] / max(1, total),
            }