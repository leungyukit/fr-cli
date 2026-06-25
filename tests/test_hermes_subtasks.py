"""
Hermes 目标分解与子任务依赖测试
覆盖：目标自动分解、链式执行、依赖 DAG、循环检测。
"""
import json
import time
from unittest.mock import MagicMock

import pytest

from fr_cli.agent.hermes import (
    TaskStatus,
    HermesEngine,
)
from fr_cli.conf import paths as paths_module


@pytest.fixture
def engine(tmp_path, monkeypatch):
    import fr_cli.agent.hermes.managers as _managers_mod
    import fr_cli.agent.hermes.engine as _engine_mod
    hermes_dir = tmp_path / "hermes"
    hermes_dir.mkdir()
    paths_map = {
        "HERMES_DIR": hermes_dir,
        "HERMES_TASKS_FILE": hermes_dir / "tasks.json",
        "HERMES_GOALS_FILE": hermes_dir / "goals.json",
        "HERMES_ANALYTICS_FILE": hermes_dir / "analytics.json",
        "HERMES_LOG_FILE": hermes_dir / "hermes.log",
        "HERMES_MEMORY_FILE": hermes_dir / "memory.json",
    }
    for mod in (paths_module, _managers_mod, _engine_mod):
        for name, value in paths_map.items():
            if hasattr(mod, name):
                monkeypatch.setattr(mod, name, value)

    state = MagicMock()
    state.model_name = "mock-model"
    state.messages = []
    state.lang = "zh"
    state.client = MagicMock()
    state.master_agent = MagicMock()
    state.master_agent.handle = MagicMock(return_value=("done", True))

    def _fake_stream_cnt(client, model, messages, lang, custom_prefix=None, max_tokens=None, silent=False):
        return json.dumps({"steps": ["搜索资料", "整理笔记", "生成报告"]}), {}, 0.0, False

    monkeypatch.setattr("fr_cli.agent.hermes.engine.stream_cnt", _fake_stream_cnt)

    eng = HermesEngine(state_provider=lambda: state)
    eng.scheduler.stop()
    yield eng
    eng.scheduler.stop()


class TestHermesDecomposition:
    def test_decompose_goal_creates_parent_and_children(self, engine):
        parent = engine.decompose_goal("写一份 AI 报告")
        assert parent is not None
        assert parent.task_type == "goal"
        assert parent.description == "写一份 AI 报告"
        assert len(parent.children_ids) == 3

        children = [engine.get_task(cid) for cid in parent.children_ids]
        assert all(c is not None for c in children)
        assert [c.description for c in children] == ["搜索资料", "整理笔记", "生成报告"]
        assert all(c.task_type == "goal_step" for c in children)
        assert all(c.parent_id == parent.id for c in children)

    def test_decompose_goal_links_chain_next(self, engine):
        parent = engine.decompose_goal("写一份 AI 报告")
        children = [engine.get_task(cid) for cid in parent.children_ids]
        assert children[0].chain_next == children[1].id
        assert children[1].chain_next == children[2].id
        assert children[2].chain_next is None


class TestHermesChainExecution:
    def test_scheduler_runs_chain_in_order_and_completes_parent(self, engine):
        parent = engine.decompose_goal("写一份 AI 报告")
        children = [engine.get_task(cid) for cid in parent.children_ids]
        assert children[0].scheduled_at is not None

        # 模拟调度器循环，直到没有可执行任务
        for _ in range(10):
            now = time.time()
            pending = [
                t for t in engine.task_manager.list_tasks()
                if t.status == TaskStatus.PENDING
                and (t.scheduled_at is None or t.scheduled_at <= now)
                and engine._dependencies_satisfied(t)
            ]
            pending.sort(key=lambda t: (-t.priority.value, t.created_at))
            if not pending:
                break
            task = pending[0]
            if engine._has_cycle(task.id):
                engine._fail_task(task, "依赖存在循环")
                continue
            engine._execute_task(task)

        for child in children:
            assert child.status == TaskStatus.COMPLETED
        parent = engine.get_task(parent.id)
        assert parent.status == TaskStatus.COMPLETED


class TestHermesDependencyDAG:
    def test_dependency_dag_respects_completion_order(self, engine):
        a = engine.task_manager.create("任务 A")
        b = engine.task_manager.create("任务 B", dependencies=[a.id])
        c = engine.task_manager.create("任务 C", dependencies=[a.id, b.id])

        assert engine._dependencies_satisfied(a) is True
        assert engine._dependencies_satisfied(b) is False
        assert engine._dependencies_satisfied(c) is False

        a.status = TaskStatus.COMPLETED
        engine.task_manager.update(a)

        assert engine._dependencies_satisfied(b) is True
        assert engine._dependencies_satisfied(c) is False

        b.status = TaskStatus.COMPLETED
        engine.task_manager.update(b)

        assert engine._dependencies_satisfied(c) is True

    def test_dependency_dag_execution_order(self, engine):
        a = engine.task_manager.create("任务 A")
        b = engine.task_manager.create("任务 B", dependencies=[a.id])
        c = engine.task_manager.create("任务 C", dependencies=[a.id, b.id])

        a.status = TaskStatus.COMPLETED
        engine.task_manager.update(a)

        engine._execute_task(b)
        assert b.status == TaskStatus.COMPLETED

        engine._execute_task(c)
        assert c.status == TaskStatus.COMPLETED


class TestHermesCycleDetection:
    def test_has_cycle_detects_self_dependency(self, engine):
        a = engine.task_manager.create("循环任务 A")
        a.dependencies = [a.id]
        engine.task_manager.update(a)
        assert engine._has_cycle(a.id) is True

    def test_has_cycle_detects_mutual_dependency(self, engine):
        a = engine.task_manager.create("任务 A")
        b = engine.task_manager.create("任务 B")
        a.dependencies = [b.id]
        b.dependencies = [a.id]
        engine.task_manager.update(a)
        engine.task_manager.update(b)
        assert engine._has_cycle(a.id) is True
        assert engine._has_cycle(b.id) is True

    def test_scheduler_marks_cyclic_task_failed(self, engine):
        # 构造一个依赖已完成但自身成环的任务
        a = engine.task_manager.create("已完成任务 A")
        a.status = TaskStatus.COMPLETED
        a.dependencies = []  # A 依赖 C，形成循环
        c = engine.task_manager.create("循环任务 C", dependencies=[a.id])
        a.dependencies = [c.id]
        engine.task_manager.update(a)
        engine.task_manager.update(c)

        assert engine._dependencies_satisfied(c) is True
        assert engine._has_cycle(c.id) is True

        # 模拟调度器处理 C
        if engine._has_cycle(c.id):
            engine._fail_task(c, "依赖存在循环")

        assert c.status == TaskStatus.FAILED
        assert "循环" in (c.error or "")
