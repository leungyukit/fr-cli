"""
Hermes 跨任务记忆测试
"""
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def hermes_env(tmp_path, monkeypatch):
    """将 Hermes 持久化路径隔离到临时目录"""
    import fr_cli.conf.paths as paths_mod

    monkeypatch.setattr(paths_mod, "HERMES_DIR", tmp_path)
    monkeypatch.setattr(paths_mod, "HERMES_TASKS_FILE", tmp_path / "tasks.json")
    monkeypatch.setattr(paths_mod, "HERMES_GOALS_FILE", tmp_path / "goals.json")
    monkeypatch.setattr(paths_mod, "HERMES_ANALYTICS_FILE", tmp_path / "analytics.json")
    monkeypatch.setattr(paths_mod, "HERMES_MEMORY_FILE", tmp_path / "memory.json")
    monkeypatch.setattr(paths_mod, "HERMES_LOG_FILE", tmp_path / "hermes.log")
    return tmp_path


class TestHermesMemoryStore:
    """测试 HermesMemoryStore"""

    def test_record_and_find_relevant(self, hermes_env):
        from fr_cli.agent.hermes import HermesMemoryStore

        store = HermesMemoryStore()
        store.record("t1", "summary task", "result one", ["project:fr-cli"])
        store.record("t2", "another task", "result two", ["project:fr-cli", "task:refactor"])
        store.record("t3", "unrelated", "result three", ["task:ui"])

        relevant = store.find_relevant(["project:fr-cli"], limit=2)
        assert len(relevant) == 2
        assert relevant[0]["task_id"] == "t2"  # more tags overlap, newer first

    def test_find_relevant_empty_tags(self, hermes_env):
        from fr_cli.agent.hermes import HermesMemoryStore

        store = HermesMemoryStore()
        store.record("t1", "task", "result", ["tag"])
        assert store.find_relevant([], limit=3) == []


class TestHermesTaskMemoryInjection:
    """测试 Hermes 任务执行时注入历史记忆"""

    def test_execute_task_injects_memory_hints(self, hermes_env, monkeypatch):
        from fr_cli.agent.hermes import HermesEngine, Task, TaskStatus

        engine = HermesEngine(state_provider=lambda: None)
        engine.scheduler.stop()

        # 预置一条历史记忆
        engine.memory_store.record("prev", "previous refactor", "moved files", ["project:fr-cli"])

        master = MagicMock()
        master.handle.return_value = ("done", True)
        state = SimpleNamespace(model_name="glm-4-flash", messages=[], master_agent=master)
        engine.state_provider = lambda: state

        task = engine.task_manager.create(
            description="refactor module",
            task_type="adhoc",
            context_tags=["project:fr-cli"],
        )
        engine._execute_task(task)

        assert task.status == TaskStatus.COMPLETED
        call_kwargs = master.handle.call_args.kwargs
        assert "memory_hints" in call_kwargs
        assert "previous refactor" in call_kwargs["memory_hints"]

    def test_execute_task_no_tags_no_hints(self, hermes_env, monkeypatch):
        from fr_cli.agent.hermes import HermesEngine, TaskStatus

        engine = HermesEngine(state_provider=lambda: None)
        engine.scheduler.stop()

        engine.memory_store.record("prev", "previous task", "result", ["tag"])

        master = MagicMock()
        master.handle.return_value = ("done", True)
        state = SimpleNamespace(model_name="glm-4-flash", messages=[], master_agent=master)
        engine.state_provider = lambda: state

        task = engine.task_manager.create(description="no tags task")
        engine._execute_task(task)

        assert task.status == TaskStatus.COMPLETED
        call_kwargs = master.handle.call_args.kwargs
        assert not call_kwargs.get("memory_hints")
