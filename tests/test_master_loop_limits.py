"""MasterAgent ReAct 循环运行时预算回归测试（P1-6）

覆盖：
- MAX_STEPS / max_repeat_calls / step_retries 从 config 读
- 死循环检测：同一 tool+params 累计成功 N 次即收尾
- 单步失败重试
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from fr_cli.agent.master_loop import MasterAgentLoopMixin


class _FakeMaster:
    """提供 MasterAgentLoopMixin.handle() 真正用到的成员。

    注意 MRO 顺序：``_FakeMaster`` 在前，``MasterAgentLoopMixin`` 在后，
    这样 ``_execute_tool`` 走可控的假实现而不是注册表真调用。
    """

    def __init__(self, state):
        self.state = state
        self.session = {"current_task": None, "task_history": [], "context_notes": ""}
        self._status_data = {}
        self._step_count = 0
        self.calls = []
        self.tool_impl = None  # 可注入的 (tool, params) -> (result, error)

    # --- mixin 依赖 ---
    def _build_system_prompt(self, lang):
        return "系统提示"

    def _get_recent_memory(self):
        return ""

    def _get_failure_hint(self, tool):
        return ""

    def _maybe_compress_messages(self, msgs):
        return None

    def _needs_planning(self, user_input):
        return False

    def _reflect_and_evolve(self, *a, **kw):
        return None

    def _detect_artifacts(self, txt, lang, background=False):
        return None

    def _record_interaction(self, *a, **kw):
        return None

    # --- 受控的工具执行 ---
    def _execute_tool(self, tool_name, params):
        self.calls.append((tool_name, dict(params or {})))
        if self.tool_impl is not None:
            return self.tool_impl(tool_name, params)
        return f"{tool_name} ok", None


def _state(tmp_path, cfg=None):
    return SimpleNamespace(
        model_name="mock-model",
        lang="zh",
        client=SimpleNamespace(),
        provider="mock",
        limit=1000,
        messages=[],
        sn="test-session",
        auto_session_path=str(tmp_path / "session.json"),
        executor=SimpleNamespace(),
        cfg=cfg if cfg is not None else {},
    )


def _tool_call_text(tool, params=None):
    return (
        "```tool\n"
        + json.dumps({"tool": tool, "params": params or {}}, ensure_ascii=False)
        + "\n```"
    )


def _build(state):
    """按 MRO 组装出可用的 MasterAgent（假成员优先）"""
    obj = type("M", (_FakeMaster, MasterAgentLoopMixin), {})(state)
    obj.state = state
    return obj


def _run(monkeypatch, tmp_path, obj, script, tool_impl=None):
    """跑一轮 handle()。

    script: **按 LLM 调用序号**取文本的脚本（用完重复最后一个），
    这样工具调用次数不会影响 LLM 应答序列。
    """
    import fr_cli.core.stream as stream_mod

    obj.tool_impl = tool_impl
    llm_calls = []

    def fake_stream_cnt(client, model, messages, lang, custom_prefix="", max_tokens=2048, silent=True, **kw):
        llm_calls.append(list(messages))
        idx = min(len(llm_calls) - 1, len(script) - 1)
        return script[idx], None, None, None

    monkeypatch.setattr(stream_mod, "stream_cnt", fake_stream_cnt)
    monkeypatch.setattr("fr_cli.agent.master_loop._save_json", lambda *a, **kw: None)
    monkeypatch.setattr("fr_cli.agent.master_loop.save_context", lambda *a, **kw: None)

    answer, _cont = obj.handle("原始问题")
    return answer, llm_calls, obj


class TestResolveLimits:
    def test_defaults_when_cfg_missing(self, tmp_path):
        obj = _build(_state(tmp_path))
        assert obj._resolve_limits() == (
            MasterAgentLoopMixin.MAX_STEPS,
            MasterAgentLoopMixin.MAX_REPEAT_CALLS,
            MasterAgentLoopMixin.MAX_STEP_RETRIES,
        )

    def test_reads_from_cfg(self, tmp_path):
        cfg = {"master": {"max_steps": 3, "max_repeat_calls": 5, "step_retries": 0}}
        obj = _build(_state(tmp_path, cfg))
        assert obj._resolve_limits() == (3, 5, 0)

    def test_invalid_values_fall_back(self, tmp_path):
        cfg = {"master": {"max_steps": "abc", "max_repeat_calls": -1, "step_retries": -2}}
        obj = _build(_state(tmp_path, cfg))
        max_steps, repeat, retries = obj._resolve_limits()
        assert max_steps == MasterAgentLoopMixin.MAX_STEPS
        assert repeat == MasterAgentLoopMixin.MAX_REPEAT_CALLS
        assert retries == MasterAgentLoopMixin.MAX_STEP_RETRIES

    def test_step_retries_zero_is_valid(self, tmp_path):
        """step_retries=0 是合法值 —— 明确关闭重试"""
        cfg = {"master": {"max_steps": 3, "max_repeat_calls": 3, "step_retries": 0}}
        obj = _build(_state(tmp_path, cfg))
        assert obj._resolve_limits() == (3, 3, 0)

    def test_zero_max_steps_falls_back(self, tmp_path):
        """max_steps=0 无意义（一步都不走）→ 回落默认值"""
        cfg = {"master": {"max_steps": 0, "max_repeat_calls": 0, "step_retries": 0}}
        obj = _build(_state(tmp_path, cfg))
        max_steps, repeat, retries = obj._resolve_limits()
        assert max_steps == MasterAgentLoopMixin.MAX_STEPS
        assert repeat == MasterAgentLoopMixin.MAX_REPEAT_CALLS
        assert retries == 0

    def test_master_cfg_not_dict_is_ignored(self, tmp_path):
        cfg = {"master": "乱写"}
        obj = _build(_state(tmp_path, cfg))
        assert obj._resolve_limits() == (
            MasterAgentLoopMixin.MAX_STEPS,
            MasterAgentLoopMixin.MAX_REPEAT_CALLS,
            MasterAgentLoopMixin.MAX_STEP_RETRIES,
        )


class TestDeadLoopDetection:
    def test_same_tool_same_params_stops_loop(self, monkeypatch, tmp_path):
        """同一工具 + 同一参数连续成功 3 次 → 判定死循环并收尾"""
        cfg = {"master": {"max_steps": 8, "max_repeat_calls": 3, "step_retries": 0}}
        obj = _build(_state(tmp_path, cfg))
        script = [_tool_call_text("read_file", {"path": "a.txt"})]
        answer, llm_calls, bound = _run(monkeypatch, tmp_path, obj, script)

        # 3 次成功即停，不该把 8 步预算耗光
        assert len(bound.calls) == 3
        # 收尾时还会再调一次 LLM 要求总结
        assert len(llm_calls) == 4
        assert "重复" in llm_calls[-1][-1]["content"]

    def test_different_params_not_flagged(self, monkeypatch, tmp_path):
        """参数不同不算重复 —— 正常的多文件读取不该被误杀"""
        cfg = {"master": {"max_steps": 8, "max_repeat_calls": 2, "step_retries": 0}}
        obj = _build(_state(tmp_path, cfg))
        script = [
            _tool_call_text("read_file", {"path": "a.txt"}),
            _tool_call_text("read_file", {"path": "b.txt"}),
            _tool_call_text("read_file", {"path": "c.txt"}),
            "全部读完",
        ]
        answer, llm_calls, bound = _run(monkeypatch, tmp_path, obj, script)

        assert len(bound.calls) == 3
        assert answer == "全部读完"

    def test_failed_calls_do_not_count_as_loop(self, monkeypatch, tmp_path):
        """失败重试不算死循环 —— 只有成功调用才计数"""
        cfg = {"master": {"max_steps": 3, "max_repeat_calls": 2, "step_retries": 1}}
        obj = _build(_state(tmp_path, cfg))
        script = [_tool_call_text("read_file", {"path": "a.txt"})]

        def always_fail(tool_name, params):
            return None, "读不到"

        answer, llm_calls, bound = _run(monkeypatch, tmp_path, obj, script, tool_impl=always_fail)

        # 每步 1 次调用 + 1 次重试 = 2 次，共 3 步 → 6 次
        assert len(bound.calls) == 6
        # 步数走满 max_steps —— 说明没被死循环检测提前打断
        assert bound._step_count == 3

    def test_call_key_is_param_sensitive(self):
        a = MasterAgentLoopMixin._call_key("read_file", {"path": "a", "mode": "r"})
        b = MasterAgentLoopMixin._call_key("read_file", {"mode": "r", "path": "a"})
        c = MasterAgentLoopMixin._call_key("read_file", {"path": "b"})
        assert a == b  # 键序无关
        assert a != c


class TestStepRetry:
    def test_failure_is_retried_then_succeeds(self, monkeypatch, tmp_path):
        """工具第一次失败、重试成功 → 观察里应记录成功"""
        cfg = {"master": {"max_steps": 4, "max_repeat_calls": 3, "step_retries": 1}}
        obj = _build(_state(tmp_path, cfg))
        script = [_tool_call_text("read_file", {"path": "a.txt"}), "最终答案"]

        attempts = {"n": 0}

        def flaky(tool_name, params):
            attempts["n"] += 1
            if attempts["n"] == 1:
                return None, "临时故障"
            return "成功", None

        answer, llm_calls, bound = _run(monkeypatch, tmp_path, obj, script, tool_impl=flaky)

        assert len(bound.calls) == 2  # 失败 1 次 + 重试 1 次
        assert answer == "最终答案"
        steps = bound.session["task_history"][-1]["steps"]
        assert steps[-1]["success"] is True
        assert steps[-1]["retries"] == 1

    def test_no_retry_when_disabled(self, monkeypatch, tmp_path):
        """step_retries=0 → 失败不重试（每步只调用一次）"""
        cfg = {"master": {"max_steps": 3, "max_repeat_calls": 3, "step_retries": 0}}
        obj = _build(_state(tmp_path, cfg))
        script = [_tool_call_text("read_file", {"path": "a.txt"})]

        def failing(tool_name, params):
            return None, "总是失败"

        answer, llm_calls, bound = _run(monkeypatch, tmp_path, obj, script, tool_impl=failing)

        # 失败不计入死循环计数 → 步数走满 max_steps，每步只调用一次
        assert len(bound.calls) == 3
        steps = bound.session["task_history"][-1]["steps"]
        assert all(s["retries"] == 0 for s in steps)
        assert all(s["success"] is False for s in steps)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
