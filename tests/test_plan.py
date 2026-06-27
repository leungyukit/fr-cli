"""
Plan mode 测试
覆盖 JSON 解析/清理、文本折叠、参数解析、计划存储等核心逻辑。
"""
import json
import os
import sys
from unittest.mock import patch, MagicMock


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ==================== JSON 解析 ====================

class TestCleanJsonText:

    def test_clean_plain_json(self):
        from fr_cli.core.plan.generator import _clean_json_text
        assert _clean_json_text('{"a": 1}') == '{"a": 1}'

    def test_clean_markdown_json_block(self):
        from fr_cli.core.plan.generator import _clean_json_text
        text = '```json\n{"a": 1}\n```'
        result = _clean_json_text(text)
        assert '"a": 1' in result
        assert "```" not in result

    def test_clean_markdown_no_language(self):
        from fr_cli.core.plan.generator import _clean_json_text
        text = '```\n{"b": 2}\n```'
        result = _clean_json_text(text)
        assert '"b": 2' in result
        assert "```" not in result

    def test_clean_with_whitespace(self):
        from fr_cli.core.plan.generator import _clean_json_text
        text = '  \n {"x": 1}  \n'
        result = _clean_json_text(text)
        assert result == '{"x": 1}'


class TestTryParseJson:

    def test_parse_valid_json(self):
        from fr_cli.core.plan.generator import _try_parse_json
        result = _try_parse_json('{"a": 1, "b": 2}')
        assert result == {"a": 1, "b": 2}

    def test_parse_markdown_json(self):
        from fr_cli.core.plan.generator import _try_parse_json
        result = _try_parse_json('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_parse_invalid_returns_none(self):
        from fr_cli.core.plan.generator import _try_parse_json
        assert _try_parse_json("not json at all") is None

    def test_parse_empty_returns_none(self):
        from fr_cli.core.plan.generator import _try_parse_json
        assert _try_parse_json("") is None

    def test_parse_array(self):
        """数组也是合法 JSON"""
        from fr_cli.core.plan.generator import _try_parse_json
        result = _try_parse_json('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_parse_nested(self):
        from fr_cli.core.plan.generator import _try_parse_json
        result = _try_parse_json('{"a": {"b": [1, 2]}}')
        assert result == {"a": {"b": [1, 2]}}


class TestRenderPlan:

    def test_render_empty_plan(self):
        from fr_cli.core.plan.generator import render_plan
        result = render_plan({}, "zh")
        assert isinstance(result, str)

    def test_render_plan_with_steps(self):
        from fr_cli.core.plan.generator import render_plan
        plan = {
            "goal": "Test goal",
            "steps": [
                {"tool": "search_web", "description": "搜索资料"},
                {"tool": "write_file", "description": "保存结果"},
            ],
        }
        result = render_plan(plan, "zh")
        assert "Test goal" in result or "搜索" in result or "保存" in result

    def test_render_plan_english(self):
        from fr_cli.core.plan.generator import render_plan
        plan = {"goal": "English goal", "steps": [{"tool": "search_web", "description": "search"}]}
        result = render_plan(plan, "en")
        assert isinstance(result, str)


# ==================== 文本折叠 ====================

class TestFoldText:

    def test_short_text_not_folded(self):
        from fr_cli.core.plan.executor import _fold_text
        text = "line1\nline2\nline3"
        result = _fold_text(text)
        assert result == text

    def test_long_text_folded(self):
        from fr_cli.core.plan.executor import _fold_text
        lines = [f"line{i}" for i in range(100)]
        text = "\n".join(lines)
        result = _fold_text(text, max_lines=30, head=15, tail=5)
        # 应包含 head + tail + 中间的 omitted 提示
        assert "omitted" in result or "省略" in result
        # head 行应包含
        assert "line0" in result
        assert "line14" in result
        # tail 行应包含
        assert "line99" in result
        # 中间的不应有
        assert "line50" not in result

    def test_fold_with_custom_params(self):
        from fr_cli.core.plan.executor import _fold_text
        text = "\n".join(f"x{i}" for i in range(50))
        result = _fold_text(text, max_lines=10, head=3, tail=2)
        assert "x0" in result
        assert "x2" in result
        assert "x49" in result

    def test_fold_empty(self):
        from fr_cli.core.plan.executor import _fold_text
        assert _fold_text("") == ""

    def test_fold_single_line(self):
        from fr_cli.core.plan.executor import _fold_text
        assert _fold_text("single") == "single"


# ==================== 参数解析 ====================

class TestResolveStepParams:

    def test_empty_params(self):
        from fr_cli.core.plan.executor import _resolve_step_params
        step = {"params": {}}
        result = _resolve_step_params(step, [])
        assert result == {}

    def test_step_without_params(self):
        from fr_cli.core.plan.executor import _resolve_step_params
        step = {}
        result = _resolve_step_params(step, [])
        assert result == {}

    def test_resolve_depends_on_step(self):
        from fr_cli.core.plan.executor import _resolve_step_params
        step = {
            "params": {
                "query": "hello",
                "depends_on_step": 0,
            }
        }
        step_results = [(True, "previous result")]
        result = _resolve_step_params(step, step_results)
        # depends_on_step 应被处理
        assert "query" in result
        assert "previous result" in str(result) or result.get("query") == "hello"


# ==================== 计划存储 ====================

class TestPlanStorage:

    def test_plan_file_path(self):
        from fr_cli.core.plan.storage import _plan_file_path
        path = _plan_file_path("test_session_123")
        assert "test_session_123" in str(path)
        assert str(path).endswith(".json") or "plans" in str(path)

    def test_save_and_load_plan(self, tmp_path, monkeypatch):
        """保存和加载计划"""
        from fr_cli.core.plan import storage

        # 隔离 PLANS_DIR
        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()
        monkeypatch.setattr(storage, "PLANS_DIR", plans_dir)

        mock_state = MagicMock()
        mock_state.session_id = "test_session_xyz"

        plan = {
            "goal": "test goal",
            "steps": [{"tool": "search_web", "description": "x"}],
        }

        result = storage.save_plan(mock_state, plan)
        assert result is not None
        assert "test_session_xyz" in str(result)

        # 加载(load_plan 直接返回 plan 字段内容)
        loaded = storage.load_plan(mock_state)
        assert loaded is not None
        assert loaded.get("goal") == "test goal"

    def test_save_plan_no_session_id_returns_none(self, tmp_path, monkeypatch):
        from fr_cli.core.plan import storage
        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()
        monkeypatch.setattr(storage, "PLANS_DIR", plans_dir)

        mock_state = MagicMock(spec=[])  # 没有 session_id
        plan = {"goal": "x", "steps": []}
        result = storage.save_plan(mock_state, plan)
        assert result is None

    def test_save_plan_empty_plan_returns_none(self, tmp_path, monkeypatch):
        from fr_cli.core.plan import storage
        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()
        monkeypatch.setattr(storage, "PLANS_DIR", plans_dir)

        mock_state = MagicMock()
        mock_state.session_id = "s1"
        result = storage.save_plan(mock_state, {})
        assert result is None

    def test_load_plan_nonexistent(self, tmp_path, monkeypatch):
        from fr_cli.core.plan import storage
        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()
        monkeypatch.setattr(storage, "PLANS_DIR", plans_dir)

        mock_state = MagicMock()
        mock_state.session_id = "never_saved_xxx"
        result = storage.load_plan(mock_state)
        assert result is None


# ==================== Generate Plan (mock LLM) ====================

class TestGeneratePlan:

    def test_generate_plan_with_mock(self):
        """Mock stream_cnt 返回 LLM 输出"""
        from fr_cli.core.plan.generator import generate_plan

        mock_state = MagicMock()
        mock_state.model_name = "test-model"
        mock_state.lang = "zh"
        mock_state.cfg = {}

        plan_json = json.dumps({
            "goal": "test",
            "steps": [{"tool": "search_web", "description": "search"}],
            "summary": "summary",
        })

        with patch("fr_cli.core.plan.generator.stream_cnt") as mock_stream:
            mock_stream.return_value = (plan_json, {}, 0.1, False)
            with patch("fr_cli.core.plan.generator._get_tools_text", return_value="tools"):
                result = generate_plan(mock_state, "user input", lang="zh")

        assert result is not None
        assert result.get("goal") == "test"
        assert len(result.get("steps", [])) == 1

    def test_generate_plan_invalid_json_returns_none(self):
        from fr_cli.core.plan.generator import generate_plan

        mock_state = MagicMock()
        mock_state.model_name = "test-model"
        mock_state.lang = "zh"
        mock_state.cfg = {}

        with patch("fr_cli.core.plan.generator.stream_cnt") as mock_stream:
            mock_stream.return_value = ("not json", {}, 0.1, False)
            with patch("fr_cli.core.plan.generator._get_tools_text", return_value="tools"):
                result = generate_plan(mock_state, "user input", lang="zh")
        assert result is None

    def test_generate_plan_markdown_json(self):
        """LLM 经常返回 ```json``` 包裹"""
        from fr_cli.core.plan.generator import generate_plan

        mock_state = MagicMock()
        mock_state.model_name = "test-model"
        mock_state.lang = "zh"
        mock_state.cfg = {}

        markdown = '```json\n{"goal": "g", "steps": []}\n```'

        with patch("fr_cli.core.plan.generator.stream_cnt") as mock_stream:
            mock_stream.return_value = (markdown, {}, 0.1, False)
            with patch("fr_cli.core.plan.generator._get_tools_text", return_value="tools"):
                result = generate_plan(mock_state, "input", lang="zh")
        assert result is not None
        assert result.get("goal") == "g"
