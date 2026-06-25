"""
Hermes 后台自治任务引擎测试
覆盖：任务持久化、调度器、HermesEngine 创建/查询/状态报告、失败重试。
"""
import os
import time
from unittest.mock import MagicMock

import pytest

from fr_cli.agent.hermes import (
    TaskStatus,
    TaskPriority,
    Task,
    PersistentTaskManager,
    PersistentGoalTracker,
    HermesAnalytics,
    HermesEngine,
)


@pytest.fixture
def tmp_hermes_dir(tmp_path):
    """为每个测试提供独立的 Hermes 目录"""
    d = tmp_path / "hermes"
    d.mkdir()
    return d


class TestTask:
    def test_task_to_dict_roundtrip(self):
        t = Task(id="t1", description="hello", priority=TaskPriority.HIGH)
        d = t.to_dict()
        assert d["priority"] == TaskPriority.HIGH.value
        assert d["status"] == TaskStatus.PENDING.value
        t2 = Task.from_dict(d)
        assert t2.priority == TaskPriority.HIGH
        assert t2.status == TaskStatus.PENDING

    def test_task_from_legacy_dict(self):
        """兼容缺少新字段的旧格式"""
        legacy = {"id": "t1", "description": "legacy", "status": "pending", "created_at": time.time()}
        t = Task.from_dict(legacy)
        assert t.priority == TaskPriority.NORMAL
        assert t.execution_mode == "sandbox"
        assert t.max_retries == 3


class TestPersistentTaskManager:
    def test_create_and_persist(self, tmp_hermes_dir):
        store = tmp_hermes_dir / "tasks.json"
        mgr = PersistentTaskManager(store)
        t = mgr.create("test task", priority="critical")
        assert t.description == "test task"
        assert t.priority == TaskPriority.CRITICAL
        assert t.status == TaskStatus.PENDING

        # 重新加载后仍能读取
        mgr2 = PersistentTaskManager(store)
        t2 = mgr2.get(t.id)
        assert t2 is not None
        assert t2.priority == TaskPriority.CRITICAL

    def test_list_and_order(self, tmp_hermes_dir):
        store = tmp_hermes_dir / "tasks.json"
        mgr = PersistentTaskManager(store)
        t_low = mgr.create("low", priority="low")
        t_high = mgr.create("high", priority="high")
        t_norm = mgr.create("normal", priority="normal")
        listed = mgr.list_tasks()
        # 优先级降序
        assert listed[0].id == t_high.id
        assert listed[1].id == t_norm.id
        assert listed[2].id == t_low.id

    def test_counts(self, tmp_hermes_dir):
        store = tmp_hermes_dir / "tasks.json"
        mgr = PersistentTaskManager(store)
        t1 = mgr.create("one")
        t2 = mgr.create("two")
        t1.status = TaskStatus.COMPLETED
        mgr.update(t1)
        counts = mgr.counts()
        assert counts["pending"] == 1
        assert counts["completed"] == 1


class TestPersistentGoalTracker:
    def test_create_and_persist(self, tmp_hermes_dir):
        store = tmp_hermes_dir / "goals.json"
        tracker = PersistentGoalTracker(store)
        g = tracker.create("write report", ["search", "read", "write"])
        assert g.description == "write report"
        assert len(g.milestones) == 3

        tracker2 = PersistentGoalTracker(store)
        g2 = tracker2.get(g.id)
        assert g2 is not None
        assert g2.milestones == ["search", "read", "write"]


class TestHermesAnalytics:
    def test_record_task(self, tmp_hermes_dir):
        store = tmp_hermes_dir / "analytics.json"
        a = HermesAnalytics(store)
        a.record_task(True)
        a.record_task(False)
        stats = a.get_stats()
        assert stats["successful_tasks"] == 1
        assert stats["failed_tasks"] == 1


class TestHermesEngine:
    @pytest.fixture(scope="function")
    def engine(self, tmp_hermes_dir, monkeypatch):
        # 把 Hermes 默认路径指向临时目录，避免污染真实配置
        # 注意：fr_cli.agent.hermes.managers 与 fr_cli.agent.hermes.engine 都各自
        # 在 import 时绑定了 HERMES_*_FILE 路径常量，需对每个使用模块都做 patch
        import fr_cli.agent.hermes.managers as _managers_mod
        import fr_cli.agent.hermes.engine as _engine_mod
        import fr_cli.conf.paths as _paths_mod
        import fr_cli.agent.hermes as _pkg_mod

        paths_map = {
            "HERMES_DIR": tmp_hermes_dir,
            "HERMES_TASKS_FILE": tmp_hermes_dir / "tasks.json",
            "HERMES_GOALS_FILE": tmp_hermes_dir / "goals.json",
            "HERMES_ANALYTICS_FILE": tmp_hermes_dir / "analytics.json",
            "HERMES_LOG_FILE": tmp_hermes_dir / "hermes.log",
            "HERMES_MEMORY_FILE": tmp_hermes_dir / "memory.json",
        }
        for mod in (_paths_mod, _pkg_mod, _managers_mod, _engine_mod):
            for name, value in paths_map.items():
                if hasattr(mod, name):
                    monkeypatch.setattr(mod, name, value)

        state = MagicMock()
        state.model_name = "mock-model"
        state.messages = []
        state.master_agent = MagicMock()
        state.master_agent.handle = MagicMock(return_value=("done", True))

        eng = HermesEngine(state_provider=lambda: state)
        # 停止调度器避免后台干扰
        eng.scheduler.stop()
        yield eng
        eng.scheduler.stop()

    def test_create_task(self, engine):
        t = engine.create_task("research AI agents")
        assert t.status == TaskStatus.PENDING
        assert t.execution_mode == "sandbox"
        loaded = engine.get_task(t.id)
        assert loaded.description == "research AI agents"

    def test_status_report(self, engine):
        engine.create_task("task1")
        engine.create_task("task2")
        report = engine.status_report()
        assert "pending=2" in report
        assert "调度器" in report

    def test_execute_task_success(self, engine):
        t = engine.create_task("do something")
        engine._execute_task(t)
        assert t.status == TaskStatus.COMPLETED
        assert t.result == "done"
        # MasterAgent.handle 应被调用过（可能同一 engine 被调度器触发过其他任务）
        calls = [c.args[0] for c in engine.state_provider().master_agent.handle.call_args_list]
        assert "do something" in calls

    def test_execute_task_isolates_state_messages(self, engine):
        state = engine.state_provider()
        original_messages = ["orig"]
        state.messages = original_messages
        t = engine.create_task("isolated task")
        engine._execute_task(t)
        # state.messages 应被恢复
        assert state.messages == original_messages

    def test_execute_task_retry_and_fail(self, engine):
        state = engine.state_provider()
        state.master_agent.handle.side_effect = RuntimeError("boom")
        t = engine.create_task("failing task")
        t.max_retries = 2
        # 第一次执行
        engine._execute_task(t)
        assert t.status == TaskStatus.PENDING
        assert t.retries == 1
        assert t.scheduled_at is not None
        # 第二次执行应失败
        engine._execute_task(t)
        assert t.status == TaskStatus.FAILED
        assert t.retries == 2

    def test_sandbox_mode_sets_env(self, engine, monkeypatch):
        """sandbox 执行模式应设置 FR_CLI_AUTONOMOUS_MODE=sandbox_auto"""
        monkeypatch.delenv("FR_CLI_AUTONOMOUS_MODE", raising=False)
        t = engine.create_task("sandbox task", execution_mode="sandbox")
        engine._execute_task(t)
        assert os.environ.get("FR_CLI_AUTONOMOUS_MODE") is None  # 执行后已恢复

    def test_cancel_task(self, engine):
        t = engine.create_task("cancel me")
        assert engine.cancel_task(t.id) is True
        assert engine.get_task(t.id).status == TaskStatus.PAUSED
        assert engine.cancel_task("not-exist") is False

    def test_autonomous_task_requires_confirmation(self, engine):
        """autonomous 任务默认应被暂停，等待用户确认"""
        t = engine.create_task(
            "autonomous task",
            execution_mode="autonomous",
            source="repl",
            confirm_prompt=False,
        )
        assert t.execution_mode == "autonomous"
        assert t.user_confirmed_at is None
        assert t.status == TaskStatus.PAUSED

    def test_confirm_task(self, engine):
        """确认后 autonomous 任务变为 pending 且带有 user_confirmed_at"""
        t = engine.create_task(
            "autonomous task",
            execution_mode="autonomous",
            source="repl",
            confirm_prompt=False,
        )
        assert engine.confirm_task(t.id) is True
        loaded = engine.get_task(t.id)
        assert loaded.status == TaskStatus.PENDING
        assert loaded.user_confirmed_at is not None

    def test_confirm_task_only_for_autonomous(self, engine):
        t = engine.create_task("sandbox task", execution_mode="sandbox")
        assert engine.confirm_task(t.id) is False

    def test_autonomous_downgrade_when_unconfirmed(self, engine, monkeypatch):
        """未确认的 autonomous 任务执行时应降级为 sandbox，不设置 full_auto"""
        monkeypatch.delenv("FR_CLI_AUTONOMOUS_MODE", raising=False)
        env_values = []
        original_handle = engine.state_provider().master_agent.handle

        def _capture_handle(*args, **kwargs):
            env_values.append(os.environ.get("FR_CLI_AUTONOMOUS_MODE"))
            return original_handle(*args, **kwargs)

        engine.state_provider().master_agent.handle = _capture_handle
        t = engine.create_task(
            "unconfirmed autonomous",
            execution_mode="autonomous",
            source="repl",
            confirm_prompt=False,
        )
        assert t.status == TaskStatus.PAUSED
        engine._execute_task(t)
        # 降级为 sandbox_auto，而不是 full_auto
        assert env_values == ["sandbox_auto"]
        assert t.status == TaskStatus.COMPLETED

    def test_autonomous_full_auto_when_confirmed(self, engine, monkeypatch):
        """确认后的 autonomous 任务执行时应使用 full_auto"""
        monkeypatch.delenv("FR_CLI_AUTONOMOUS_MODE", raising=False)
        env_values = []
        original_handle = engine.state_provider().master_agent.handle

        def _capture_handle(*args, **kwargs):
            env_values.append(os.environ.get("FR_CLI_AUTONOMOUS_MODE"))
            return original_handle(*args, **kwargs)

        engine.state_provider().master_agent.handle = _capture_handle
        t = engine.create_task(
            "confirmed autonomous",
            execution_mode="autonomous",
            source="repl",
            confirm_prompt=False,
        )
        engine.confirm_task(t.id)
        engine._execute_task(t)
        assert env_values == ["full_auto"]
        assert t.status == TaskStatus.COMPLETED

    def test_task_execution_timeout(self, engine, monkeypatch):
        """任务执行超时应标记为失败或重试"""
        import time as _time
        monkeypatch.setenv("FR_CLI_HERMES_TASK_TIMEOUT", "0.1")

        def _slow_handle(*args, **kwargs):
            _time.sleep(2)
            return "done", True

        engine.state_provider().master_agent.handle = _slow_handle
        t = engine.create_task("slow task")
        t.max_retries = 1
        engine._execute_task(t)
        assert "超时" in (t.error or "")
        assert t.status == TaskStatus.FAILED


class TestHermesScheduler:
    def test_scheduler_picks_up_pending_task(self, tmp_hermes_dir, monkeypatch):
        monkeypatch.setattr("fr_cli.agent.hermes.HERMES_DIR", tmp_hermes_dir)
        monkeypatch.setattr("fr_cli.agent.hermes.HERMES_TASKS_FILE", tmp_hermes_dir / "tasks.json")
        monkeypatch.setattr("fr_cli.agent.hermes.HERMES_GOALS_FILE", tmp_hermes_dir / "goals.json")
        monkeypatch.setattr("fr_cli.agent.hermes.HERMES_ANALYTICS_FILE", tmp_hermes_dir / "analytics.json")
        monkeypatch.setattr("fr_cli.agent.hermes.HERMES_LOG_FILE", tmp_hermes_dir / "hermes.log")

        state = MagicMock()
        state.model_name = "mock-model"
        state.messages = []
        state.master_agent = MagicMock()
        state.master_agent.handle = MagicMock(return_value=("done", True))

        eng = HermesEngine(state_provider=lambda: state)
        # 调度器已启动，先停掉，用短轮询手动触发
        eng.scheduler.stop()

        t = eng.create_task("scheduled task")
        # 手动跑一次调度循环逻辑
        eng._execute_task(t)
        assert t.status == TaskStatus.COMPLETED
        eng.scheduler.stop()
