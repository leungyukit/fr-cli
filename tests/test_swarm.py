"""
蜂群（Swarm）多 Agent 协作测试
"""
from unittest.mock import patch, MagicMock
from types import SimpleNamespace


class TestSwarmEngine:
    """测试蜂群引擎"""

    def _make_state(self):
        state = SimpleNamespace()
        state.client = MagicMock()
        state.model_name = "glm-4-flash"
        state.lang = "zh"
        state.executor = MagicMock()
        state.plugins = {}
        state.vfs = MagicMock()
        state.vfs.cwd = "/tmp"
        state.security = None
        return state

    @patch("fr_cli.agent.swarm_resolver.call_agent")
    def test_run_parallel(self, mock_call_agent):
        from fr_cli.agent.swarm import SwarmEngine
        mock_call_agent.side_effect = lambda name, state, user_input="": (f"result-{name}", None)

        engine = SwarmEngine(self._make_state())
        result, err = engine.run_parallel(["agent:a", "agent:b", "agent:c"], "任务")

        assert err is None
        assert result["mode"] == "parallel"
        assert len(result["results"]) == 3
        assert mock_call_agent.call_count == 3
        names = [r["agent"] for r in result["results"]]
        assert names == ["agent:a", "agent:b", "agent:c"]

    @patch("fr_cli.agent.swarm_resolver.call_agent")
    def test_run_parallel_missing_agent(self, mock_call_agent):
        from fr_cli.agent.swarm import SwarmEngine

        def _side_effect(name, state, user_input=""):
            if name == "b":
                return None, "not found"
            return f"result-{name}", None

        mock_call_agent.side_effect = _side_effect

        engine = SwarmEngine(self._make_state())
        result, err = engine.run_parallel(["agent:a", "agent:b"], "任务")

        assert err is None
        assert len(result["results"]) == 2
        # 有一个 Agent 失败，另一个成功
        assert any(r["error"] for r in result["results"])
        assert any(r["error"] is None for r in result["results"])

    @patch("fr_cli.agent.swarm_resolver.call_agent")
    def test_run_council(self, mock_call_agent):
        from fr_cli.agent.swarm import SwarmEngine
        mock_call_agent.side_effect = lambda name, state, user_input="": (f"opinion-{name}", None)

        state = self._make_state()
        state.client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="综合结论"))]
        )

        engine = SwarmEngine(state)
        result, err = engine.run_council(["agent:a", "agent:b"], "任务")

        assert err is None
        assert result["mode"] == "council"
        assert len(result["individual"]) == 2
        assert "综合结论" in result["summary"]
        assert state.client.chat.completions.create.called

    @patch("fr_cli.agent.swarm_resolver.call_agent")
    def test_run_pipeline(self, mock_call_agent):
        from fr_cli.agent.swarm import SwarmEngine
        mock_call_agent.side_effect = lambda name, state, user_input="": (f"pipeline-{name}-{user_input}", None)

        engine = SwarmEngine(self._make_state())
        result, err = engine.run_pipeline(["agent:a", "agent:b"], "初始输入")

        assert err is None
        assert result["mode"] == "pipeline"
        assert len(result["results"]) == 2
        assert result["results"][0]["result"] == "pipeline-a-初始输入"
        assert result["results"][1]["result"] == "pipeline-b-pipeline-a-初始输入"

    def test_run_invalid_mode(self):
        from fr_cli.agent.swarm import SwarmEngine
        engine = SwarmEngine(self._make_state())
        result, err = engine.run("invalid", ["a"], "任务")
        assert err is not None


class TestSwarmRegistry:
    """测试注册表解析"""

    def test_parse_swarm_args(self):
        from fr_cli.command.registry import get_registry
        reg = get_registry()
        kwargs = reg._parse_cmd_args(
            ["/swarm", "parallel", "a,b,c", "任务描述"],
            {"name": "swarm_run"},
            None,
        )
        assert kwargs == {"mode": "parallel", "names": ["a", "b", "c"], "user_input": "任务描述"}

    def test_parse_swarm_args_council(self):
        from fr_cli.command.registry import get_registry
        reg = get_registry()
        kwargs = reg._parse_cmd_args(
            ["/swarm", "council", "x,y", "讨论一下"],
            {"name": "swarm_run"},
            None,
        )
        assert kwargs["mode"] == "council"
        assert kwargs["names"] == ["x", "y"]
        assert kwargs["user_input"] == "讨论一下"


class TestSwarmTool:
    """测试注册表工具调用"""

    @patch("fr_cli.agent.swarm.run_swarm")
    def test_swarm_run_tool(self, mock_run_swarm):
        from fr_cli.command.registered.swarm import _swarm_run
        mock_run_swarm.return_value = ({"mode": "parallel", "results": []}, None)

        deps = SimpleNamespace()
        result, err = _swarm_run(deps, mode="parallel", names=["a", "b"], user_input="任务")

        assert err is None
        mock_run_swarm.assert_called_once_with("parallel", ["a", "b"], deps, "任务", max_workers=5)

    @patch("fr_cli.agent.swarm.run_swarm")
    def test_swarm_run_tool_string_names(self, mock_run_swarm):
        from fr_cli.command.registered.swarm import _swarm_run
        mock_run_swarm.return_value = ({"mode": "parallel", "results": []}, None)

        deps = SimpleNamespace()
        result, err = _swarm_run(deps, mode="parallel", names="a,b", user_input="任务")

        assert err is None
        mock_run_swarm.assert_called_once_with("parallel", ["a", "b"], deps, "任务", max_workers=5)


class TestSwarmUniversalResolver:
    """测试蜂群统一解析器：支持 Agent、工具、命令、MCP、插件"""

    def _make_state(self):
        state = SimpleNamespace()
        state.client = MagicMock()
        state.model_name = "glm-4-flash"
        state.lang = "zh"
        from fr_cli.core.result import Result
        state.executor = MagicMock()
        state.executor.execute = MagicMock(return_value=Result.ok("cmd-result"))
        state.plugins = {}
        state.vfs = MagicMock()
        state.vfs.cwd = "/tmp"
        state.security = None
        state.mcp = None
        return state

    def test_resolve_explicit_agent_prefix(self):
        from fr_cli.agent.swarm_resolver import SwarmTaskResolver
        resolver = SwarmTaskResolver(self._make_state())
        kind, target, _ = resolver.resolve("agent:myagent")
        assert kind == "agent"
        assert target == "myagent"

    def test_resolve_explicit_builtin_prefix(self):
        from fr_cli.agent.swarm_resolver import SwarmTaskResolver
        resolver = SwarmTaskResolver(self._make_state())
        kind, target, _ = resolver.resolve("@local")
        assert kind == "builtin"
        assert target == "local"

    def test_resolve_explicit_tool_prefix(self):
        from fr_cli.agent.swarm_resolver import SwarmTaskResolver
        resolver = SwarmTaskResolver(self._make_state())
        kind, target, _ = resolver.resolve("tool:search_web")
        assert kind == "tool"
        assert target == "search_web"

    def test_resolve_explicit_cmd_prefix(self):
        from fr_cli.agent.swarm_resolver import SwarmTaskResolver
        resolver = SwarmTaskResolver(self._make_state())
        kind, target, _ = resolver.resolve("cmd:/web 搜索")
        assert kind == "cmd"
        assert target == "/web 搜索"

    def test_resolve_explicit_mcp_prefix(self):
        from fr_cli.agent.swarm_resolver import SwarmTaskResolver
        resolver = SwarmTaskResolver(self._make_state())
        kind, target, _ = resolver.resolve("mcp:fs/read_file")
        assert kind == "mcp"
        assert target == "fs/read_file"

    def test_resolve_command_auto(self):
        from fr_cli.agent.swarm_resolver import SwarmTaskResolver
        resolver = SwarmTaskResolver(self._make_state())
        kind, target, _ = resolver.resolve("/ls")
        assert kind == "cmd"

    def test_call_command(self):
        from fr_cli.agent.swarm_resolver import SwarmTaskResolver
        state = self._make_state()
        resolver = SwarmTaskResolver(state)
        result, err = resolver.call("/ls", "")
        assert err is None
        assert result == "cmd-result"
        state.executor.execute.assert_called_once_with("/ls")

    def test_call_command_with_user_input(self):
        from fr_cli.agent.swarm_resolver import SwarmTaskResolver
        state = self._make_state()
        resolver = SwarmTaskResolver(state)
        result, err = resolver.call("/web", "Python 教程")
        assert err is None
        state.executor.execute.assert_called_once_with("/web Python 教程")

    @patch("fr_cli.agent.swarm_resolver.call_agent")
    def test_call_agent(self, mock_call_agent):
        from fr_cli.agent.swarm_resolver import SwarmTaskResolver
        mock_call_agent.return_value = ("agent-result", None)
        resolver = SwarmTaskResolver(self._make_state())
        result, err = resolver.call("agent:test", "任务")
        assert err is None
        assert result == "agent-result"
        mock_call_agent.assert_called_once()

    @patch("fr_cli.agent.client.call_builtin_agent")
    def test_call_builtin(self, mock_builtin):
        from fr_cli.agent.swarm_resolver import SwarmTaskResolver
        mock_builtin.return_value = ("builtin-result", None)
        resolver = SwarmTaskResolver(self._make_state())
        result, err = resolver.call("@local", "查看目录")
        assert err is None
        assert result == "builtin-result"
        mock_builtin.assert_called_once()

    def test_call_tool_search_web(self):
        from fr_cli.agent.swarm_resolver import SwarmTaskResolver
        resolver = SwarmTaskResolver(self._make_state())
        kind, _, _ = resolver.resolve("search_web")
        assert kind == "tool"

    @patch("fr_cli.command.registry.ToolRegistry.dispatch")
    def test_call_tool_dispatch(self, mock_dispatch):
        from fr_cli.agent.swarm_resolver import SwarmTaskResolver
        mock_dispatch.return_value = ("web-result", None)
        resolver = SwarmTaskResolver(self._make_state())
        result, err = resolver.call("search_web", "Python")
        assert err is None
        assert result == "web-result"
