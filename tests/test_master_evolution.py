"""
MasterAgent 失败驱动自我学习测试
"""
import builtins
import json
import os as real_os
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
        from fr_cli.agent.master_storage import _classify_error
        assert _classify_error("File not found: /tmp/x") == "FileNotFound"

    def test_classify_permission(self, master_env):
        from fr_cli.agent.master_storage import _classify_error
        assert _classify_error("Permission denied") == "PermissionDenied"

    def test_classify_timeout(self, master_env):
        from fr_cli.agent.master_storage import _classify_error
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
        from fr_cli.agent.master import MasterAgent

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


class TestAtomicPersistence:
    """v3.1：MasterAgent 落盘原子化 —— 写入中断不会破坏原文件"""

    def test_save_json_keeps_original_when_write_fails(self, master_env, monkeypatch):
        """写到临时文件阶段失败：原文件内容必须完好"""
        import fr_cli.agent.master_storage as storage_mod

        path = master_env / "memory.json"
        path.write_text('{"interactions": []}', encoding="utf-8")

        real_open = builtins.open

        class _BrokenFile:
            """模拟写到一半磁盘/IO 失败"""

            def write(self, data):
                raise OSError("模拟磁盘写入失败")

            def flush(self):
                pass

            def fileno(self):
                raise OSError("no fileno")

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake_open(file, mode="r", *args, **kwargs):
            if "w" in mode and str(file).endswith(".tmp"):
                return _BrokenFile()
            return real_open(file, mode, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", fake_open)

        with pytest.raises(RuntimeError) as exc:
            storage_mod._save_json(path, {"interactions": [{"tool": "read_file"}]})

        assert "写入" in str(exc.value)
        # 原文件完好
        assert path.read_text(encoding="utf-8") == '{"interactions": []}'
        # 临时文件已清理
        assert not (master_env / "memory.json.tmp").exists()

    def test_save_json_keeps_original_when_replace_fails(self, master_env, monkeypatch):
        """原子替换阶段失败：原文件内容必须完好，临时文件被清理"""
        import fr_cli.agent.master_storage as storage_mod

        path = master_env / "session.json"
        path.write_text('{"current_task": null}', encoding="utf-8")

        class _FakeOS:
            """只让 os.replace 失败，其余（fsync）照常"""

            def __init__(self, real):
                self._real = real

            def fsync(self, fd):
                return self._real.fsync(fd)

            def replace(self, *args, **kwargs):
                raise OSError("模拟原子替换失败")

        monkeypatch.setattr(storage_mod, "os", _FakeOS(real_os))

        with pytest.raises(RuntimeError):
            storage_mod._save_json(path, {"current_task": "写任务"})

        assert path.read_text(encoding="utf-8") == '{"current_task": null}'
        assert not (master_env / "session.json.tmp").exists()

    def test_save_json_writes_atomically(self, master_env):
        """正常写入：内容完整、可被重新读回，且不残留临时文件"""
        import fr_cli.agent.master_storage as storage_mod

        path = master_env / "evolution.json"
        storage_mod._save_json(path, {"success": ["read_file"], "failure": []})

        assert storage_mod._load_json(path)["success"] == ["read_file"]
        assert not (master_env / "evolution.json.tmp").exists()

    def test_load_json_raises_on_corrupt_file(self, master_env):
        """损坏文件仍然 raise（不静默回落默认值，避免把"文件损坏"掩盖成"默认状态"）"""
        import fr_cli.agent.master_storage as storage_mod

        path = master_env / "evolution.json"
        path.write_text("{ 这不是合法 JSON", encoding="utf-8")

        with pytest.raises(RuntimeError) as exc:
            storage_mod._load_json(path)
        assert "读取" in str(exc.value)

    def test_save_text_is_atomic_and_silent(self, master_env, monkeypatch):
        """_save_text：原子写 + 保持既有的静默失败语义"""
        import fr_cli.agent.master_storage as storage_mod

        path = master_env / "persona.md"
        path.write_text("旧人设", encoding="utf-8")

        class _FakeOS:
            def __init__(self, real):
                self._real = real

            def fsync(self, fd):
                return self._real.fsync(fd)

            def replace(self, *args, **kwargs):
                raise OSError("模拟原子替换失败")

        monkeypatch.setattr(storage_mod, "os", _FakeOS(real_os))

        # 写失败保持静默（不抛异常），且原文件不被破坏
        storage_mod._save_text(path, "新人设")
        assert path.read_text(encoding="utf-8") == "旧人设"

        # 恢复正常后可以正常落盘
        monkeypatch.undo()
        storage_mod._save_text(path, "新人设")
        assert path.read_text(encoding="utf-8") == "新人设"
        assert not (master_env / "persona.md.tmp").exists()

