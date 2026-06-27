"""
Plan mode 交互式编辑测试
覆盖 enter_plan_mode / exit_plan_mode / edit_pending_plan / show_pending_plan_json。
"""
import json
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fr_cli.core import plan_mode


@pytest.fixture
def isolated_session(tmp_path, monkeypatch):
    """隔离 _plan_file_for_session 路径"""
    from fr_cli.conf import paths as paths_mod
    monkeypatch.setattr(paths_mod, "CONTEXT_FILE", tmp_path / "context.json")


# ==================== save / load / clear ====================

class TestPlanPersistence:

    def test_save_and_load(self, isolated_session):
        ok = plan_mode.save_pending_plan("sess1", {"goal": "g", "steps": []})
        assert ok is True

        loaded = plan_mode.load_pending_plan("sess1")
        assert loaded is not None
        assert loaded.get("goal") == "g"

    def test_load_nonexistent_returns_none(self, isolated_session):
        loaded = plan_mode.load_pending_plan("never_saved_xxx")
        assert loaded is None

    def test_clear_removes_file(self, isolated_session):
        plan_mode.save_pending_plan("sess1", {"goal": "x", "steps": []})
        plan_mode.clear_pending_plan("sess1")
        loaded = plan_mode.load_pending_plan("sess1")
        assert loaded is None


# ==================== render_plan_for_user ====================

class TestRenderPlanForUser:

    def test_renders_plan_with_approval_options(self):
        plan = {"goal": "test", "steps": [{"tool": "search_web"}]}
        out = plan_mode.render_plan_for_user(plan, lang="zh")
        assert "test" in out
        assert "批准" in out or "y" in out
        assert "拒绝" in out or "n" in out
        assert "编辑" in out or "e" in out

    def test_english_rendering(self):
        plan = {"goal": "english test", "steps": []}
        out = plan_mode.render_plan_for_user(plan, lang="en")
        assert "english test" in out


# ==================== show_pending_plan_json ====================

class TestShowJson:

    def test_shows_full_json(self, isolated_session):
        plan_mode.save_pending_plan("s1", {"goal": "g", "steps": [{"tool": "x"}]})
        mock_state = MagicMock()
        mock_state.session_id = "s1"

        result = plan_mode.show_pending_plan_json(mock_state)
        assert result.is_ok()
        # JSON 字符串
        text = result.unwrap()
        parsed = json.loads(text)
        assert parsed["goal"] == "g"

    def test_no_plan_returns_fail(self, isolated_session):
        mock_state = MagicMock()
        mock_state.session_id = "never"

        result = plan_mode.show_pending_plan_json(mock_state)
        assert not result.is_ok()


# ==================== enter_plan_mode (mock LLM) ====================

class TestEnterPlanMode:

    def test_enter_generates_and_saves_plan(self, isolated_session):
        plan = {"goal": "test", "steps": [{"tool": "search_web"}]}

        mock_state = MagicMock()
        mock_state.lang = "zh"
        mock_state.session_id = "sess_enter"

        with patch("fr_cli.core.plan.generator.generate_plan") as mock_gen:
            mock_gen.return_value = plan
            with patch("fr_cli.core.plan.storage.save_plan"):
                result = plan_mode.enter_plan_mode(mock_state, "搜索 fr-cli 文档")

        assert result.is_ok(), f"error: {result.error}"
        # plan 已保存
        loaded = plan_mode.load_pending_plan("sess_enter")
        assert loaded is not None
        assert loaded.get("goal") == "test"
        # state 已标记
        assert mock_state._plan_pending is True
        assert mock_state._plan_user_input == "搜索 fr-cli 文档"

    def test_enter_returns_failure_when_no_plan(self, isolated_session):
        mock_state = MagicMock()
        mock_state.lang = "zh"
        mock_state.session_id = "s1"

        with patch("fr_cli.core.plan.generator.generate_plan") as mock_gen:
            mock_gen.return_value = None
            result = plan_mode.enter_plan_mode(mock_state, "test")

        assert not result.is_ok()


# ==================== exit_plan_mode ====================

class TestExitPlanMode:

    def test_approve_executes_plan(self, isolated_session):
        plan = {"goal": "g", "steps": [{"tool": "search_web", "description": "x"}]}
        plan_mode.save_pending_plan("sess_exit", plan)

        mock_state = MagicMock()
        mock_state.lang = "zh"
        mock_state.session_id = "sess_exit"

        with patch("fr_cli.core.plan.executor.execute_plan") as mock_exec:
            mock_exec.return_value = [(True, "ok")]
            result = plan_mode.exit_plan_mode(mock_state, approved=True)

        assert result.is_ok()
        # plan 已清除
        assert plan_mode.load_pending_plan("sess_exit") is None

    def test_reject_does_not_execute(self, isolated_session):
        plan = {"goal": "g", "steps": [{"tool": "x"}]}
        plan_mode.save_pending_plan("sess_reject", plan)

        mock_state = MagicMock()
        mock_state.lang = "zh"
        mock_state.session_id = "sess_reject"

        result = plan_mode.exit_plan_mode(mock_state, approved=False)
        assert result.is_ok()
        # plan 已清除
        assert plan_mode.load_pending_plan("sess_reject") is None
        # state._plan_pending 被清除
        assert mock_state._plan_pending is False

    def test_exit_no_plan_returns_fail(self, isolated_session):
        mock_state = MagicMock()
        mock_state.lang = "zh"
        mock_state.session_id = "never"

        result = plan_mode.exit_plan_mode(mock_state, approved=True)
        assert not result.is_ok()


# ==================== edit_pending_plan ====================

class TestEditPendingPlan:

    def test_edit_with_instruction(self, isolated_session):
        original = {"goal": "original", "steps": [{"tool": "read_file"}]}
        plan_mode.save_pending_plan("sess_edit", original)

        new_plan = {"goal": "modified", "steps": [{"tool": "write_file"}]}

        mock_state = MagicMock()
        mock_state.lang = "zh"
        mock_state.session_id = "sess_edit"
        mock_state._plan_user_input = "original task"

        with patch("fr_cli.core.plan.generator.generate_plan") as mock_gen:
            mock_gen.return_value = new_plan
            result = plan_mode.edit_pending_plan(mock_state, "把 read_file 改成 write_file")

        assert result.is_ok(), f"error: {result.error}"
        # 计划已被新计划替换
        loaded = plan_mode.load_pending_plan("sess_edit")
        assert loaded.get("goal") == "modified"

    def test_edit_no_plan_returns_fail(self, isolated_session):
        mock_state = MagicMock()
        mock_state.lang = "zh"
        mock_state.session_id = "never"

        result = plan_mode.edit_pending_plan(mock_state, "change something")
        assert not result.is_ok()

    def test_edit_generation_failure(self, isolated_session):
        plan_mode.save_pending_plan("s1", {"goal": "x", "steps": []})

        mock_state = MagicMock()
        mock_state.lang = "zh"
        mock_state.session_id = "s1"

        with patch("fr_cli.core.plan.generator.generate_plan") as mock_gen:
            mock_gen.return_value = None
            result = plan_mode.edit_pending_plan(mock_state, "change")

        assert not result.is_ok()
