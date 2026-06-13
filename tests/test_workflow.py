"""
Agent 工作流引擎测试 —— 解析、循环依赖检测、步骤超时。
"""
import time
from unittest.mock import MagicMock

import pytest

from fr_cli.agent.workflow import parse_workflow, run_workflow, _detect_cycle
from fr_cli import agent as agent_module
from fr_cli.agent import manager as manager_module


@pytest.fixture
def tmp_agents_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(manager_module, "AGENTS_DIR", tmp_path)
    monkeypatch.setattr(agent_module, "AGENTS_DIR", tmp_path)
    return tmp_path


def _write_workflow(tmp_agents_dir, name, content):
    d = tmp_agents_dir / name
    d.mkdir()
    (d / "workflow.md").write_text(content, encoding="utf-8")


def test_parse_workflow():
    text = """# workflow
## 步骤1：问好
- **action**: ai_generate
- **params**:
  - prompt: "你好"
## 步骤2：总结
- **action**: save_memory
- **params**:
  - content: "{{step1.result}}"
"""
    steps = parse_workflow(text)
    assert len(steps) == 2
    assert steps[0]["num"] == 1
    assert steps[0]["action"] == "ai_generate"
    assert steps[1]["action"] == "save_memory"
    assert steps[1]["params"]["content"] == '"{{step1.result}}"'


def test_detect_cycle_direct():
    steps = [
        {"num": 1, "action": "ai_generate", "params": {"prompt": "{{step2.result}}"}},
        {"num": 2, "action": "ai_generate", "params": {"prompt": "{{step1.result}}"}},
    ]
    cycle = _detect_cycle(steps)
    assert cycle is not None
    assert 0 in cycle and 1 in cycle


def test_detect_cycle_indirect():
    steps = [
        {"num": 1, "action": "ai", "params": {"prompt": "{{step2.result}}"}},
        {"num": 2, "action": "ai", "params": {"prompt": "{{step3.result}}"}},
        {"num": 3, "action": "ai", "params": {"prompt": "{{step1.result}}"}},
    ]
    cycle = _detect_cycle(steps)
    assert cycle is not None
    assert set(cycle) == {0, 1, 2}


def test_detect_no_cycle():
    steps = [
        {"num": 1, "action": "ai", "params": {"prompt": "hi"}},
        {"num": 2, "action": "ai", "params": {"prompt": "{{step1.result}}"}},
    ]
    assert _detect_cycle(steps) is None


def test_run_workflow_cycle(tmp_agents_dir):
    _write_workflow(tmp_agents_dir, "cyc", """# wf
## 步骤1：A
- **action**: ai_generate
- **params**:
  - prompt: "{{step2.result}}"
## 步骤2：B
- **action**: ai_generate
- **params**:
  - prompt: "{{step1.result}}"
""")
    state = MagicMock()
    state.resolve_agent_llm.return_value = (MagicMock(), "zhipu", "glm-4-flash")
    state.lang = "zh"
    state.executor = MagicMock()
    result = run_workflow("cyc", state)
    assert result.is_fail()
    assert "循环依赖" in result.error


def test_run_workflow_timeout(tmp_agents_dir, monkeypatch):
    _write_workflow(tmp_agents_dir, "to", """# wf
## 步骤1：慢生成
- **action**: ai_generate
- **params**:
  - prompt: "hello"
  - timeout: 0.05
""")

    def slow_stream_cnt(*args, **kwargs):
        time.sleep(0.2)
        return ("done", None, None, None)

    monkeypatch.setattr("fr_cli.core.stream.stream_cnt", slow_stream_cnt)
    state = MagicMock()
    state.resolve_agent_llm.return_value = (MagicMock(), "zhipu", "glm-4-flash")
    state.lang = "zh"
    state.executor = MagicMock()
    result = run_workflow("to", state)
    assert result.is_fail()
    assert "超时" in result.error


def test_run_workflow_success(tmp_agents_dir, monkeypatch):
    _write_workflow(tmp_agents_dir, "ok", """# wf
## 步骤1：生成
- **action**: ai_generate
- **params**:
  - prompt: "hello"
## 步骤2：保存
- **action**: save_memory
- **params**:
  - content: "{{step1.result}}"
""")

    def fake_stream_cnt(*args, **kwargs):
        return ("world", None, None, None)

    monkeypatch.setattr("fr_cli.core.stream.stream_cnt", fake_stream_cnt)
    state = MagicMock()
    state.resolve_agent_llm.return_value = (MagicMock(), "zhipu", "glm-4-flash")
    state.lang = "zh"
    state.executor = MagicMock()
    result = run_workflow("ok", state)
    assert result.is_ok()
    final, steps = result.unwrap()
    assert final == "记忆已更新"
    assert steps[0]["result"] == "world"
    assert "world" in (tmp_agents_dir / "ok" / "memory.md").read_text(encoding="utf-8")
