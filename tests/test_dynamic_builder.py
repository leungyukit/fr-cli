"""
动态构建系统测试
"""
import json
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def tmp_dynamic_dir(tmp_path):
    with patch("fr_cli.dynamic_builder.registry_manager.DYNAMIC_TOOLS_DIR", tmp_path / "dynamic_tools"):
        yield tmp_path / "dynamic_tools"


@pytest.fixture
def mock_state():
    state = SimpleNamespace()
    state.client = MagicMock()
    state.model_name = "glm-4-flash"
    state.lang = "zh"
    state.cfg = {}
    state.vfs = MagicMock()
    state.vfs.cwd = "/tmp"
    state.mail_c = None
    state.web_c = None
    state.disk_c = None
    state.security = None
    state.plugins = {}
    return state


class TestDependencyManager:
    """测试依赖管理"""

    def test_is_installed_stdlib(self):
        from fr_cli.dynamic_builder.dependency_manager import is_installed
        assert is_installed("os") is True

    def test_check_dependencies(self):
        from fr_cli.dynamic_builder.dependency_manager import check_dependencies
        installed, missing = check_dependencies(["os", "this_package_does_not_exist_12345"])
        assert "os" in installed
        assert len(missing) == 1

    @patch("fr_cli.dynamic_builder.dependency_manager.subprocess.run")
    def test_install_dependency_success(self, mock_run):
        from fr_cli.dynamic_builder.dependency_manager import install_dependency
        mock_run.return_value = MagicMock(returncode=0)
        with patch("fr_cli.dynamic_builder.dependency_manager.is_installed", side_effect=[False, True]):
            result = install_dependency("pillow", lang="zh", confirm=False)
        assert result.is_ok()


class TestCodeGenerator:
    """测试代码生成"""

    @patch("fr_cli.dynamic_builder.code_generator.stream_cnt")
    def test_generate_tool_code(self, mock_stream):
        from fr_cli.dynamic_builder.code_generator import generate_tool_code

        mock_stream.return_value = ("def run(deps, **kwargs):\n    return 'ok', None", {}, 0.1, False)
        code = generate_tool_code("生成一个测试工具", MagicMock(), "zh")
        assert "def run(" in code

    def test_extract_tool_name_run(self):
        from fr_cli.dynamic_builder.code_generator import extract_tool_name
        code = "def run(deps, **kwargs):\n    pass"
        assert extract_tool_name(code) == "run"

    def test_extract_tool_name_fallback(self):
        from fr_cli.dynamic_builder.code_generator import extract_tool_name
        code = "def my_tool(deps, **kwargs):\n    pass"
        assert extract_tool_name(code) == "my_tool"


class TestRegistryManager:
    """测试注册表管理"""

    def test_save_and_list_dynamic_tool(self, tmp_dynamic_dir):
        from fr_cli.dynamic_builder.registry_manager import save_dynamic_tool, list_dynamic_tools

        result = save_dynamic_tool(
            "test_tool",
            "def run(deps, **kwargs): return 'ok', None",
            description="测试工具",
            params={"path": str},
            aliases=["/test_tool"],
        )
        assert result.is_ok()
        tools = list_dynamic_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "test_tool"

    def test_invalid_name(self, tmp_dynamic_dir):
        from fr_cli.dynamic_builder.registry_manager import save_dynamic_tool
        result = save_dynamic_tool("123bad", "code")
        assert result.is_fail()

    def test_register_dynamic_tool(self, tmp_dynamic_dir):
        from fr_cli.dynamic_builder.registry_manager import register_dynamic_tool, get_registry

        code = "def run(deps, **kwargs):\n    return 'ok', None"
        result = register_dynamic_tool("reg_tool", code, {"description": "测试", "params": {}})
        assert result.is_ok()
        reg = get_registry()
        assert "reg_tool" in reg._tools


class TestPlanner:
    """测试规划器"""

    @patch("fr_cli.dynamic_builder.planner.stream_cnt")
    def test_plan_build_parses_json(self, mock_stream):
        from fr_cli.dynamic_builder.planner import plan_build

        plan_json = json.dumps({
            "need_build": True,
            "tool_name": "qr_tool",
            "description": "二维码工具",
            "dependencies": ["qrcode"],
            "params": {"text": "str"},
            "aliases": ["/qr"],
            "triggers": ["二维码"],
            "reasoning": "需要生成二维码",
        })
        mock_stream.return_value = (plan_json, {}, 0.1, False)

        plan = plan_build("生成二维码工具", MagicMock(), "zh")
        assert plan["need_build"] is True
        assert plan["tool_name"] == "qr_tool"

    def test_plan_build_invalid_json(self):
        from fr_cli.dynamic_builder.planner import plan_build
        with patch("fr_cli.dynamic_builder.planner.stream_cnt") as mock_stream:
            mock_stream.return_value = ("不是 JSON", {}, 0.1, False)
            plan = plan_build("test", MagicMock(), "zh")
        assert "error" in plan


class TestRunner:
    """测试主流程编排"""

    @patch("fr_cli.dynamic_builder.runner.plan_build")
    @patch("fr_cli.dynamic_builder.runner.generate_tool_code")
    @patch("fr_cli.dynamic_builder.runner.ensure_dependencies")
    @patch("fr_cli.dynamic_builder.runner.save_dynamic_tool")
    @patch("fr_cli.dynamic_builder.runner.register_dynamic_tool")
    @patch("fr_cli.dynamic_builder.runner.get_registry")
    def test_build_tool_success(self, mock_get_registry, mock_register, mock_save, mock_deps, mock_gen, mock_plan, mock_state, tmp_dynamic_dir):
        from fr_cli.dynamic_builder.runner import build_tool
        from fr_cli.core.result import Result

        mock_plan.return_value = {
            "need_build": True,
            "tool_name": "qr_tool",
            "description": "二维码工具",
            "dependencies": ["qrcode"],
            "params": {"text": "str"},
            "aliases": ["/qr"],
            "triggers": ["二维码"],
            "reasoning": "需要生成二维码",
        }
        mock_deps.return_value = Result.ok([])
        mock_gen.return_value = "def run(deps, **kwargs):\n    return 'ok', None"
        mock_save.return_value = Result.ok("saved")
        mock_register.return_value = Result.ok("registered")
        mock_get_registry.return_value.dispatch.return_value = Result.ok("self-test ok")

        result = build_tool("生成二维码工具", mock_state, lang="zh", confirm=False)
        assert result.is_ok()
        msg = result.unwrap()
        assert "qr_tool" in msg
        mock_register.assert_called_once()
        mock_get_registry.return_value.dispatch.assert_called_once()

    def test_build_tool_no_model(self, mock_state):
        from fr_cli.dynamic_builder.runner import build_tool
        mock_state.model_name = None
        result = build_tool("test", mock_state)
        assert result.is_fail()
        assert "模型" in result.error

    @patch("fr_cli.dynamic_builder.runner.plan_build")
    def test_build_tool_already_covered(self, mock_plan, mock_state):
        from fr_cli.dynamic_builder.runner import build_tool
        mock_plan.return_value = {"need_build": False, "reasoning": "已覆盖"}
        result = build_tool("读取文件", mock_state, confirm=False)
        assert result.is_ok()
