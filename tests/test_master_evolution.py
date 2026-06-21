"""
MasterAgent 失败驱动自我学习测试
"""
import json
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def master_env(tmp_path, monkeypatch):
    """将 MasterAgent 配置文件隔离到临时目录"""
    import fr_cli.agent.master as master_mod
    import fr_cli.agent.master_storage as storage_mod

    paths_map = {
        "MASTER_DIR": tmp_path,
        "PERSONA_FILE": tmp_path / "persona.md",
        "SKILLS_FILE": tmp_path / "skills.md",
        "MEMORY_FILE": tmp_path / "memory.json",
        "EVOLUTION_FILE": tmp_path / "evolution.json",
        "SESSION_FILE": tmp_path / "session.json",
        "STATUS_FILE": tmp_path / "status.json",
    }
    # 持久化层（master_storage）才是真正读取这些路径的模块，必须同时打补丁
    for mod in (master_mod, storage_mod):
        for name, value in paths_map.items():
            if hasattr(mod, name):
                monkeypatch.setattr(mod, name, value)
    return tmp_path


@pytest.fixture
def mock_state():
    return SimpleNamespace(
        client=MagicMock(),
        model_name="glm-4-flash",
        lang="zh",
        messages=[],
        context_summary="",
        sn="test",
        auto_session_path=None,
        session_id=None,
    )


class TestErrorClassification:
    """测试错误归类"""

    def test_classify_file_not_found(self, master_env):
        from fr_cli.agent.master import _classify_error
        assert _classify_error("File not found: /tmp/x") == "FileNotFound"

    def test_classify_permission(self, master_env):
        from fr_cli.agent.master import _classify_error
        assert _classify_error("Permission denied") == "PermissionDenied"

    def test_classify_timeout(self, master_env):
        from fr_cli.agent.master import _classify_error
        assert _classify_error("request timeout") == "Timeout"


class TestFailureDrivenEvolution:
    """测试失败模式记录、反思与进化提示"""

    def test_record_interaction_includes_error_type(self, master_env, mock_state):
        from fr_cli.agent.master import MasterAgent

        agent = MasterAgent(mock_state)
        agent._record_interaction("read /tmp/x", "read_file", False, "File not found", tool_params={"path": "/tmp/x"})
        last = agent.memory["interactions"][-1]
        assert last["tool"] == "read_file"
        assert last["error_type"] == "FileNotFound"
        assert last["tool_params"] == {"path": "/tmp/x"}

    @patch("fr_cli.core.stream.stream_cnt")
    def test_reflect_and_evolve_generates_hints(self, mock_stream, master_env, mock_state):
        from fr_cli.agent.master import MasterAgent, _classify_error

        agent = MasterAgent(mock_state)
        # 构造 10 次 read_file 失败，触发反思
        for i in range(10):
            agent._record_interaction(f"read /tmp/{i}", "read_file", False, "File not found")

        mock_stream.return_value = (
            json.dumps({
                "prompt_addon": "调用 read_file 前先用 list_dir 确认路径存在。",
                "failure_hints": [
                    {"tool": "read_file", "error_type": "FileNotFound", "hint": "先 list_dir 确认路径。"}
                ]
            }),
            {}, 0.1, False,
        )

        agent._reflect_and_evolve("task", [], "result")

        assert agent.evolution["prompt_addon"]
        assert len(agent.evolution["failure_hints"]) > 0
        hint = agent.evolution["failure_hints"][0]
        assert hint["tool"] == "read_file"
        assert hint["error_type"] == "FileNotFound"
        assert "list_dir" in hint["hint"]

    def test_build_system_prompt_includes_failure_hints(self, master_env, mock_state):
        from fr_cli.agent.master import MasterAgent

        agent = MasterAgent(mock_state)
        agent.evolution["failure_hints"] = [
            {"tool": "read_file", "error_type": "FileNotFound", "hint": "先确认路径。"}
        ]
        prompt = agent._build_system_prompt("zh")
        assert "[高频失败与恢复提示]" in prompt
        assert "read_file" in prompt
        assert "FileNotFound" in prompt

    def test_get_failure_hint(self, master_env, mock_state):
        from fr_cli.agent.master import MasterAgent

        agent = MasterAgent(mock_state)
        agent.evolution["failure_hints"] = [
            {"tool": "read_file", "error_type": "FileNotFound", "hint": "先确认路径。"}
        ]
        hint = agent._get_failure_hint("read_file")
        assert "FileNotFound" in hint
        assert agent._get_failure_hint("search_web") == ""
