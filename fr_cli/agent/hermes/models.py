"""
Hermes 数据模型 —— Task / Goal / 状态枚举
"""
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class TaskPriority(Enum):
    """任务优先级"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class Task:
    """Hermes 任务"""
    id: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    created_at: float = field(default_factory=time.time)
    scheduled_at: Optional[float] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[str] = None
    error: Optional[str] = None
    retries: int = 0
    max_retries: int = 3
    owner: str = "user"
    task_type: str = "adhoc"      # adhoc | cron | goal_step | command | chat
    source: str = "repl"          # repl | http | cron | master
    context: Dict = field(default_factory=dict)
    execution_mode: str = "sandbox"  # sandbox | autonomous | interactive
    user_confirmed_at: Optional[float] = None  # autonomous 任务的用户确认时间
    parent_id: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    children_ids: List[str] = field(default_factory=list)
    chain_next: Optional[str] = None
    context_tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["status"] = self.status.value if isinstance(self.status, TaskStatus) else self.status
        d["priority"] = self.priority.value if isinstance(self.priority, TaskPriority) else self.priority
        return d

    @classmethod
    def from_dict(cls, data: Dict) -> "Task":
        # 兼容旧格式（没有新字段时给默认值）
        defaults = {
            "priority": TaskPriority.NORMAL,
            "scheduled_at": None,
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None,
            "retries": 0,
            "max_retries": 3,
            "owner": "user",
            "task_type": "adhoc",
            "source": "repl",
            "context": {},
            "execution_mode": "sandbox",
            "user_confirmed_at": None,
            "parent_id": None,
            "dependencies": [],
            "children_ids": [],
            "chain_next": None,
            "context_tags": [],
        }
        for k, v in defaults.items():
            if k not in data:
                data[k] = v
        task = cls(**data)
        # 状态/优先级可能是字符串或整数值，统一转成枚举
        status = task.status
        if isinstance(status, str):
            task.status = TaskStatus(status)
        elif isinstance(status, int):
            task.status = TaskStatus(status)
        priority = task.priority
        if isinstance(priority, str):
            task.priority = TaskPriority[priority.upper()]
        elif isinstance(priority, int):
            task.priority = TaskPriority(priority)
        return task


@dataclass
class Goal:
    """目标：可拆分为多个 Task"""
    id: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    milestones: List[str] = field(default_factory=list)
    progress: float = 0.0
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    task_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: Dict) -> "Goal":
        defaults = {
            "milestones": [], "progress": 0.0, "completed_at": None,
            "task_ids": [], "created_at": time.time(), "status": "pending"
        }
        for k, v in defaults.items():
            if k not in data:
                data[k] = v
        goal = cls(**data)
        goal.status = TaskStatus(goal.status) if isinstance(goal.status, str) else goal.status
        return goal


def new_task_id() -> str:
    """生成任务 id：hms-<8位>-<时间戳>"""
    return f"hms-{uuid.uuid4().hex[:8]}-{int(time.time())}"


def new_goal_id() -> str:
    """生成目标 id：goal-<8位>-<时间戳>"""
    return f"goal-{uuid.uuid4().hex[:8]}-{int(time.time())}"