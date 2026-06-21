"""
Hermes 后台自治任务引擎

把 Hermes 从内存 stub 升级为具备持久化任务队列、调度器、与 MasterAgent 联动的
后台自治引擎。

模块拆分：
- models: Task / Goal / TaskStatus / TaskPriority
- managers: PersistentTaskManager / PersistentGoalTracker / HermesMemoryStore / HermesAnalytics
- scheduler: HermesScheduler（后台轮询）
- engine: HermesEngine（统一入口）

公开 API 通过本 __init__ 统一对外，旧模块路径 `fr_cli.agent.hermes` 仍可用。
"""
from fr_cli.agent.hermes.models import (
    Goal,
    Task,
    TaskPriority,
    TaskStatus,
    new_goal_id,
    new_task_id,
)
from fr_cli.agent.hermes.managers import (
    HermesAnalytics,
    HermesMemoryStore,
    PersistentGoalTracker,
    PersistentTaskManager,
)
from fr_cli.agent.hermes.scheduler import HermesScheduler
from fr_cli.agent.hermes.engine import DEFAULT_TASK_TIMEOUT, HermesEngine

# 重新导出路径常量，保持旧 `fr_cli.agent.hermes.HERMES_DIR` 等用法的兼容性
from fr_cli.conf.paths import (
    DAEMON_HERMES_CONFIG_FILE,
    HERMES_ANALYTICS_FILE,
    HERMES_DIR,
    HERMES_GOALS_FILE,
    HERMES_LOG_FILE,
    HERMES_MEMORY_FILE,
    HERMES_TASKS_FILE,
)

__all__ = [
    "DAEMON_HERMES_CONFIG_FILE",
    "DEFAULT_TASK_TIMEOUT",
    "Goal",
    "HERMES_ANALYTICS_FILE",
    "HERMES_DIR",
    "HERMES_GOALS_FILE",
    "HERMES_LOG_FILE",
    "HERMES_MEMORY_FILE",
    "HERMES_TASKS_FILE",
    "HermesAnalytics",
    "HermesEngine",
    "HermesMemoryStore",
    "HermesScheduler",
    "PersistentGoalTracker",
    "PersistentTaskManager",
    "Task",
    "TaskPriority",
    "TaskStatus",
    "new_goal_id",
    "new_task_id",
]