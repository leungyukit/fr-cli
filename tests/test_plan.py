"""
计划模式测试

测试目标：
1. ThinkingEngine 支持 plan 模式
2. 计划生成、解析、渲染、执行、汇总
3. 计划持久化
"""
import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def sample_plan():
    return {
        "goal": "读取项目 README 并搜索相关文档",
        "steps": [
            {
                "description": "读取 README.md",
                "tool": "read_file",
                "params": {"path": "README.md"},
                "reasoning": "了解项目基本信息",
            },
            {
                "description": "搜索 Python 教程",
                "tool": "search_web",
                "params": {"query": "Python 教程"},
                "reasoning": "获取最新资料",
            },
            {
                "description": "总结信息",
                "tool": None,
                "params": {},
                "reasoning": "无需工具，等待汇总",
            },
        ],
        "summary": "先读本地文件再联网搜索",
    }


@pytest.fixture
def mock_state(tmp_path):
    """构造一个最小可用的 AppState mock"""
    state = MagicMock()
    state.lang = "zh"
    state.model_name = "glm-4-flash"
    state.limit = 4096
    state.vfs.cwd = str(tmp_path)
    state.session_id = "test-session-id"
    state.weapon_tools = [
        {"name": "read_file", "description": "读取文件", "commands": []},
        {"name": "write_file", "description": "写入文件", "commands": []},
        {"name": "search_web", "description": "网页搜索", "commands": []},
    ]
    state.plugins = {}
    state.mcp = None
    from fr_cli.core.result import Result
    state.executor = MagicMock()
    state.executor.invoke_tool = MagicMock(return_value=Result.ok("file content"))
    state.executor.execute = MagicMock(return_value=Result.ok("command result"))
    state.messages = []
    state.context_summary = ""
    state.auto_session_path = None
    state.active_plan = None
    state.plan_step_idx = 0
    state.active_plan_total_steps = 0
    state.client = MagicMock()
    return state


class TestThinkingEnginePlanMode:
    """测试思维引擎支持 plan 模式"""

    def test_modes_contains_plan(self):
        from fr_cli.core.thinking import ThinkingEngine

        assert "plan" in ThinkingEngine.MODES

    def test_is_valid_mode_plan(self):
        from fr_cli.core.thinking import ThinkingEngine

        assert ThinkingEngine.is_valid_mode("plan") is True

    def test_analyze_plan_returns_none(self):
        """plan 模式由 chat.py 接管，analyze 返回 None"""
        from fr_cli.core.thinking import ThinkingEngine

        engine = ThinkingEngine()
        state = MagicMock()
        result = engine.analyze(state, "hello", "plan", "CHAT", "zh")
        assert result is None


class TestPlanGeneration:
    """测试计划生成与解析"""

    def test_generate_plan_parses_json(self, mock_state, sample_plan):
        from fr_cli.core.plan import generate_plan

        with patch("fr_cli.core.plan.generator.stream_cnt") as mock_stream:
            mock_stream.return_value = (json.dumps(sample_plan), {}, 0.1, False)
            plan = generate_plan(mock_state, "帮我了解一下这个项目", "zh")

        assert plan is not None
        assert plan["goal"] == sample_plan["goal"]
        assert len(plan["steps"]) == 3
        assert plan["steps"][0]["tool"] == "read_file"

    def test_generate_plan_with_markdown_code_block(self, mock_state, sample_plan):
        from fr_cli.core.plan import generate_plan

        wrapped = f"```json\n{json.dumps(sample_plan)}\n```"
        with patch("fr_cli.core.plan.generator.stream_cnt") as mock_stream:
            mock_stream.return_value = (wrapped, {}, 0.1, False)
            plan = generate_plan(mock_state, "帮我了解一下这个项目", "zh")

        assert plan is not None
        assert len(plan["steps"]) == 3

    def test_generate_plan_invalid_json_returns_none(self, mock_state):
        from fr_cli.core.plan import generate_plan

        with patch("fr_cli.core.plan.stream_cnt") as mock_stream:
            mock_stream.return_value = ("这不是 JSON", {}, 0.1, False)
            plan = generate_plan(mock_state, "test", "zh")

        assert plan is None

    def test_generate_plan_missing_steps_returns_none(self, mock_state):
        from fr_cli.core.plan import generate_plan

        bad_plan = {"goal": "test", "summary": "test"}
        with patch("fr_cli.core.plan.stream_cnt") as mock_stream:
            mock_stream.return_value = (json.dumps(bad_plan), {}, 0.1, False)
            plan = generate_plan(mock_state, "test", "zh")

        assert plan is None


class TestPlanRendering:
    """测试计划展示渲染"""

    def test_render_plan_zh(self, sample_plan):
        from fr_cli.core.plan import render_plan

        text = render_plan(sample_plan, "zh")
        assert "目标" in text
        assert "read_file" in text
        assert "搜索 Python 教程" in text
        assert "无需工具" in text

    def test_render_plan_en(self, sample_plan):
        from fr_cli.core.plan import render_plan

        text = render_plan(sample_plan, "en")
        assert "Goal" in text
        assert "read_file" in text


class TestPlanExecution:
    """测试计划执行"""

    def test_execute_step_tool_success(self, mock_state, sample_plan):
        from fr_cli.core.plan import execute_step

        step = sample_plan["steps"][0]
        ok, result = execute_step(mock_state, step, 0, [], "zh")

        assert ok is True
        assert "file content" in result
        mock_state.executor.invoke_tool.assert_called_once_with("read_file", {"path": "README.md"})

    def test_execute_step_no_tool(self, mock_state, sample_plan):
        from fr_cli.core.plan import execute_step

        step = sample_plan["steps"][2]
        ok, result = execute_step(mock_state, step, 2, [], "zh")

        assert ok is True
        assert "无需工具" in result or "info" in result
        mock_state.executor.invoke_tool.assert_not_called()

    def test_execute_step_command(self, mock_state):
        from fr_cli.core.plan import execute_step

        step = {
            "description": "写文件",
            "tool": "/write",
            "params": {"path": "a.md", "content": "hello"},
            "reasoning": "测试命令",
        }
        ok, result = execute_step(mock_state, step, 0, [], "zh")

        assert ok is True
        mock_state.executor.execute.assert_called_once()

    def test_execute_plan_all_steps(self, mock_state, sample_plan):
        from fr_cli.core.plan import execute_plan

        results = execute_plan(mock_state, sample_plan, "zh")

        assert len(results) == 3
        assert all(ok for ok, _ in results[:2])
        assert results[2][0] is True

    def test_execute_plan_dependency_backfill(self, mock_state):
        from fr_cli.core.plan import execute_plan

        plan = {
            "goal": "测试依赖回填",
            "steps": [
                {
                    "description": "第一步",
                    "tool": "read_file",
                    "params": {"path": "a.md"},
                    "reasoning": "",
                },
                {
                    "description": "第二步使用第一步结果",
                    "tool": "write_file",
                    "params": {"depends_on_step": 1, "path": "b.md"},
                    "reasoning": "",
                },
            ],
            "summary": "",
        }
        results = execute_plan(mock_state, plan, "zh")

        assert len(results) == 2
        # 第二步 params 应被回填 content
        call_args = mock_state.executor.invoke_tool.call_args_list
        second_call = call_args[1]
        assert "content" in second_call.kwargs or "content" in second_call.args[1]


class TestPlanSummarization:
    """测试结果汇总"""

    def test_summarize_execution(self, mock_state, sample_plan):
        from fr_cli.core.plan import summarize_execution

        with patch("fr_cli.core.plan.executor.stream_cnt") as mock_stream:
            mock_stream.return_value = ("这是最终总结", {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}, 0.1, False)
            summary, usage = summarize_execution(
                mock_state, "test", sample_plan,
                [(True, "file content"), (True, "search result"), (True, "done")], "zh"
            )

        assert "最终总结" in summary
        assert usage["total_tokens"] == 15


class TestPlanPersistence:
    """测试计划持久化"""

    def test_save_and_load_plan(self, mock_state, sample_plan, tmp_path):
        from fr_cli.core.plan import save_plan, load_plan

        # 临时替换 plans 目录避免污染真实环境
        with patch("fr_cli.core.plan.PLANS_DIR", tmp_path / "plans"):
            save_plan(mock_state, sample_plan)
            loaded = load_plan(mock_state)

        assert loaded is not None
        assert loaded["goal"] == sample_plan["goal"]

    def test_save_plan_no_session_returns_none(self, mock_state, sample_plan):
        from fr_cli.core.plan import save_plan

        mock_state.session_id = None
        path = save_plan(mock_state, sample_plan)
        assert path is None


class TestPlanPromptExamples:
    """测试提示词模板格式安全"""

    def test_plan_prompt_zh_format_no_key_error(self):
        from fr_cli.core.plan import PLAN_PROMPT_ZH

        try:
            result = PLAN_PROMPT_ZH.format(tools="- tool1", user_input="hello")
            assert result is not None
            assert "tool1" in result
            assert "hello" in result
        except KeyError as e:
            pytest.fail(f"中文计划提示词格式化 KeyError: {e}")

    def test_plan_prompt_en_format_no_key_error(self):
        from fr_cli.core.plan import PLAN_PROMPT_EN

        try:
            result = PLAN_PROMPT_EN.format(tools="- tool1", user_input="hello")
            assert result is not None
        except KeyError as e:
            pytest.fail(f"英文计划提示词格式化 KeyError: {e}")
