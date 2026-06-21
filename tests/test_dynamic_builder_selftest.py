"""
动态构建 —— 自测与回滚测试
"""
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

from fr_cli.core.result import Result


@pytest.fixture
def tmp_dynamic_dir(tmp_path):
    with patch("fr_cli.dynamic_builder.registry_manager.DYNAMIC_TOOLS_DIR", tmp_path / "dynamic_tools"):
        yield tmp_path / "dynamic_tools"


@pytest.fixture
def mock_state():
    return SimpleNamespace(
        client=MagicMock(),
        model_name="glm-4-flash",
        lang="zh",
        cfg={},
        vfs=MagicMock(),
        mail_c=None,
        web_c=None,
        disk_c=None,
        security=None,
        plugins={},
    )


class TestDynamicBuilderSelfTest:
    """测试动态工具构建后的自测与回滚"""

    @patch("fr_cli.dynamic_builder.runner.plan_build")
    @patch("fr_cli.dynamic_builder.runner.generate_tool_code")
    @patch("fr_cli.dynamic_builder.runner.ensure_dependencies")
    def test_selftest_pass(self, mock_ensure, mock_gen, mock_plan, mock_state, tmp_dynamic_dir):
        from fr_cli.dynamic_builder.runner import build_tool
        from fr_cli.dynamic_builder.registry_manager import list_dynamic_tools, delete_dynamic_tool

        mock_plan.return_value = {
            "need_build": True,
            "tool_name": "hello_tool",
            "description": "测试工具",
            "dependencies": [],
            "params": {"name": "str"},
            "test_params": {"name": "world"},
            "aliases": [],
            "triggers": [],
            "reasoning": "测试自测通过",
        }
        mock_ensure.return_value = Result.ok([])
        mock_gen.return_value = "def run(deps, name=''):\n    return f'hello {name}', None"

        result = build_tool("创建测试工具", mock_state, confirm=False)
        assert result.is_ok(), result.error
        tools = list_dynamic_tools()
        assert any(t["name"] == "hello_tool" for t in tools)
        # 清理，避免污染全局注册表
        delete_dynamic_tool("hello_tool")

    @patch("fr_cli.dynamic_builder.runner.plan_build")
    @patch("fr_cli.dynamic_builder.runner.generate_tool_code")
    @patch("fr_cli.dynamic_builder.runner.ensure_dependencies")
    def test_selftest_fail_rollback(self, mock_ensure, mock_gen, mock_plan, mock_state, tmp_dynamic_dir):
        from fr_cli.dynamic_builder.runner import build_tool
        from fr_cli.dynamic_builder.registry_manager import list_dynamic_tools

        mock_plan.return_value = {
            "need_build": True,
            "tool_name": "bad_tool",
            "description": "一定失败的工具",
            "dependencies": [],
            "params": {"name": "str"},
            "aliases": [],
            "triggers": [],
            "reasoning": "测试自测失败回滚",
        }
        mock_ensure.return_value = Result.ok([])
        mock_gen.return_value = "def run(deps, name=''):\n    raise RuntimeError('boom')"

        result = build_tool("创建失败工具", mock_state, confirm=False)
        assert result.is_fail()
        assert "自测失败" in result.error
        tools = list_dynamic_tools()
        assert not any(t["name"] == "bad_tool" for t in tools)
