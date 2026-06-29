"""
Hermes 自治引擎 —— 统一入口(组合 mixin)

负责任务创建、调度、执行、与 MasterAgent 联动。

v3.0+ 重构说明(参考 master_agent / app_state 的 mixin 模式):
- engine.py           主类,组合 4 个 mixin
- engine_core.py      初始化 + 日志 + shutdown
- engine_tasks.py     任务/目标 CRUD + 状态查询
- engine_execution.py 任务执行 + 依赖检查 + 链式调度
- engine_daemon.py    HTTP daemon 生命周期

向后兼容:
- 老代码 from fr_cli.agent.hermes.engine import HermesEngine 仍可用
- 所有方法签名不变
"""
from __future__ import annotations

from typing import Any, Callable

from fr_cli.agent.hermes.engine_core import DEFAULT_TASK_TIMEOUT, HermesEngineCoreMixin
from fr_cli.agent.hermes.engine_daemon import HermesEngineDaemonMixin
from fr_cli.agent.hermes.engine_execution import HermesEngineExecutionMixin
from fr_cli.agent.hermes.engine_tasks import HermesEngineTaskMixin
from fr_cli.agent.hermes.managers import (
    HermesAnalytics,
    HermesMemoryStore,
    PersistentGoalTracker,
    PersistentTaskManager,
)
from fr_cli.agent.hermes.scheduler import HermesScheduler

# 顶层 import:供测试 monkeypatch 目标(老代码可能 patch fr_cli.agent.hermes.engine.stream_cnt)
from fr_cli.core.stream import stream_cnt  # noqa: F401


class HermesEngine(
    HermesEngineCoreMixin,
    HermesEngineTaskMixin,
    HermesEngineExecutionMixin,
    HermesEngineDaemonMixin,
):
    """Hermes 自治引擎 —— 统一入口

    由 4 个 mixin 组合而成:
      - HermesEngineCoreMixin:初始化 + 日志 + shutdown
      - HermesEngineTaskMixin:任务/目标 CRUD + 状态查询
      - HermesEngineExecutionMixin:任务执行 + 依赖检查 + 链式调度
      - HermesEngineDaemonMixin:HTTP daemon 生命周期
    """

    def __init__(self, state_provider: Callable[[], Any]):
        # 委托 core mixin 初始化引擎基础
        self._init_engine(state_provider)
        # 组装 4 个子系统
        self.task_manager = PersistentTaskManager()
        self.goal_tracker = PersistentGoalTracker()
        self.memory_store = HermesMemoryStore()
        self.analytics = HermesAnalytics()
        self.scheduler = HermesScheduler(self)
        self.scheduler.start()


__all__ = ["HermesEngine", "DEFAULT_TASK_TIMEOUT"]
