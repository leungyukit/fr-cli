"""
Agent 工作流引擎测试 —— 解析、循环依赖检测、步骤超时、DAG 并行执行。
"""
import threading
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


# ------------------------------------------------------------------
# v3.1：DAG 分层并行执行 / 按步骤编号解析依赖 / 失败保留部分结果
# ------------------------------------------------------------------

def _make_state():
    state = MagicMock()
    state.resolve_agent_llm.return_value = (MagicMock(), "zhipu", "glm-4-flash")
    state.lang = "zh"
    state.executor = MagicMock()
    return state


def test_build_layers_respects_dependencies():
    """依赖图分层：互不依赖的步骤落在同一层"""
    from fr_cli.agent.workflow import _build_layers

    steps = [
        {"num": 1, "action": "ai", "params": {}},
        {"num": 2, "action": "ai", "params": {"prompt": "{{step1.result}}"}},
        {"num": 3, "action": "ai", "params": {}},
    ]
    layers = _build_layers(steps)
    assert [[s["num"] for s in layer] for layer in layers] == [[1, 3], [2]]


def test_dependency_graph_uses_step_numbers():
    """依赖图按步骤编号建表（步骤号可以不连续）"""
    from fr_cli.agent.workflow import _build_dependency_graph

    steps = [
        {"num": 2, "action": "ai", "params": {}},
        {"num": 3, "action": "ai", "params": {"prompt": "{{step2.result}}"}},
    ]
    graph = _build_dependency_graph(steps)
    assert graph[3] == {2}
    assert graph[2] == set()


def test_parallel_layer_runs_concurrently(tmp_agents_dir, monkeypatch):
    """同层步骤真正并行执行（耗时有重叠，总耗时接近单步）"""
    _write_workflow(tmp_agents_dir, "par", """# wf
## 步骤1：A
- **action**: ai_generate
- **params**:
  - prompt: "A"
## 步骤2：B
- **action**: ai_generate
- **params**:
  - prompt: "B"
""")

    spans = []
    lock = threading.Lock()

    def fake_stream_cnt(*args, **kwargs):
        start = time.monotonic()
        time.sleep(0.2)
        end = time.monotonic()
        with lock:
            spans.append((start, end))
        return ("out", None, None, None)

    monkeypatch.setattr("fr_cli.core.stream.stream_cnt", fake_stream_cnt)

    state = _make_state()
    started = time.monotonic()
    result = run_workflow("par", state)
    elapsed = time.monotonic() - started

    assert result.is_ok()
    assert len(spans) == 2
    spans.sort()
    # 两个同层步骤的耗时有重叠
    assert spans[1][0] < spans[0][1]
    # 并行总耗时接近单步耗时，而不是两倍
    assert elapsed < 0.35


def test_dependency_resolved_by_step_number(tmp_agents_dir, monkeypatch):
    """{{stepN.result}} 按步骤编号取值，而不是按下标"""
    _write_workflow(tmp_agents_dir, "numdep", """# wf
## 步骤2: 生成
- **action**: ai_generate
- **params**:
  - prompt: "生成"
## 步骤3: 保存
- **action**: save_memory
- **params**:
  - content: {{step2.result}}
""")

    def fake_stream_cnt(*args, **kwargs):
        return ("VALUE-2", None, None, None)

    monkeypatch.setattr("fr_cli.core.stream.stream_cnt", fake_stream_cnt)

    result = run_workflow("numdep", _make_state())
    assert result.is_ok()
    final, steps = result.unwrap()
    # step_results 按步骤编号有序落位
    assert [s["step"] for s in steps] == [2, 3]
    assert steps[0]["result"] == "VALUE-2"
    mem = (tmp_agents_dir / "numdep" / "memory.md").read_text(encoding="utf-8")
    assert "VALUE-2" in mem
    assert "{step2.result}" not in mem


def test_step_failure_keeps_previous_results(tmp_agents_dir, monkeypatch):
    """步骤失败时，已成功步骤的结果必须保留在 Result.data 里"""
    _write_workflow(tmp_agents_dir, "fail", """# wf
## 步骤1：生成
- **action**: ai_generate
- **params**:
  - prompt: "hello"
## 步骤2：炸掉
- **action**: unknown_action
- **params**:
  - foo: bar
""")

    def fake_stream_cnt(*args, **kwargs):
        return ("world", None, None, None)

    monkeypatch.setattr("fr_cli.core.stream.stream_cnt", fake_stream_cnt)

    result = run_workflow("fail", _make_state())
    assert result.is_fail()
    assert "未知动作" in result.error
    assert result.data is not None
    final, steps = result.data
    assert final == "world"
    assert len(steps) == 2
    assert steps[0]["step"] == 1
    assert steps[0]["result"] == "world"
    assert steps[1]["error"]


def test_run_workflow_timeout_returns_quickly(tmp_agents_dir, monkeypatch):
    """步骤超时的墙钟必须受 timeout 约束（旧实现会等挂起线程跑完）"""
    _write_workflow(tmp_agents_dir, "to2", """# wf
## 步骤1：慢生成
- **action**: ai_generate
- **params**:
  - prompt: "hello"
  - timeout: 0.05
""")

    def slow_stream_cnt(*args, **kwargs):
        time.sleep(1.0)
        return ("done", None, None, None)

    monkeypatch.setattr("fr_cli.core.stream.stream_cnt", slow_stream_cnt)

    started = time.monotonic()
    result = run_workflow("to2", _make_state())
    elapsed = time.monotonic() - started

    assert result.is_fail()
    assert "超时" in result.error
    assert elapsed < 0.5


def test_run_workflow_cycle_still_fails_whole(tmp_agents_dir):
    """环检测仍然整体 fail，且不含部分结果"""
    _write_workflow(tmp_agents_dir, "cyc2", """# wf
## 步骤1：A
- **action**: ai_generate
- **params**:
  - prompt: "{{step2.result}}"
## 步骤2：B
- **action**: ai_generate
- **params**:
  - prompt: "{{step1.result}}"
""")
    result = run_workflow("cyc2", _make_state())
    assert result.is_fail()
    assert "循环依赖" in result.error
    assert result.data is None

