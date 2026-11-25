"""流式期间可交互(steering)回归测试

覆盖三块：
1. ``fr_cli.core.steering`` —— 暂存/取走的纯逻辑
2. TUI 键位 —— Ctrl+S 注入、Ctrl+C 语义拆分、状态栏队列/转向计数
3. 对话流水线 / MasterAgent ReAct 循环 —— 转向指令真的被注入当前轮
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from fr_cli.core.steering import (
    MAX_STEER_MESSAGES,
    clear_steer,
    drain_steer,
    format_steer_notice,
    peek_steer,
    push_steer,
    steer_count,
)


# ============================================================
# 1. core/steering.py 纯逻辑
# ============================================================


class TestSteeringStore:
    def test_push_and_drain_roundtrip(self):
        st = SimpleNamespace()
        assert push_steer(st, "改成用 Python 实现") == 1
        assert push_steer(st, "再加上单元测试") == 2
        assert steer_count(st) == 2
        assert drain_steer(st) == ["改成用 Python 实现", "再加上单元测试"]
        # 取走后清空
        assert steer_count(st) == 0
        assert drain_steer(st) == []

    def test_push_ignores_blank(self):
        st = SimpleNamespace()
        assert push_steer(st, "") == 0
        assert push_steer(st, "   \n\t ") == 0
        assert push_steer(st, None) == 0
        assert steer_count(st) == 0

    def test_push_trims_whitespace(self):
        st = SimpleNamespace()
        push_steer(st, "  帮我查一下天气  ")
        assert peek_steer(st) == ["帮我查一下天气"]

    def test_peek_does_not_consume(self):
        st = SimpleNamespace()
        push_steer(st, "a")
        assert peek_steer(st) == ["a"]
        assert peek_steer(st) == ["a"]
        assert steer_count(st) == 1

    def test_clear(self):
        st = SimpleNamespace()
        push_steer(st, "a")
        push_steer(st, "b")
        clear_steer(st)
        assert steer_count(st) == 0

    def test_max_messages_cap_keeps_newest(self):
        st = SimpleNamespace()
        for i in range(MAX_STEER_MESSAGES + 5):
            push_steer(st, f"msg-{i}")
        assert steer_count(st) == MAX_STEER_MESSAGES
        kept = drain_steer(st)
        # 保留的是最新的若干条
        assert kept[-1] == f"msg-{MAX_STEER_MESSAGES + 4}"
        assert "msg-0" not in kept

    def test_states_are_isolated(self):
        a, b = SimpleNamespace(), SimpleNamespace()
        push_steer(a, "只给 A")
        assert steer_count(a) == 1
        assert steer_count(b) == 0

    def test_format_notice(self):
        assert format_steer_notice(0) == ""
        assert "2" in format_steer_notice(2)


# ============================================================
# 2. TUI 键位
# ============================================================


class TestCtrlSBinding:
    def _binding(self, prompt, key="c-s"):
        return next(b for b in prompt._kb.bindings if b.keys == (key,))

    def test_ctrl_s_injects_steer_and_clears_buffer(self):
        from fr_cli.ui.prompt.tui import FanRenPrompt

        st = SimpleNamespace(_queue_mgr=SimpleNamespace(is_processing=True))
        prompt = FanRenPrompt(st)
        event = MagicMock()
        event.current_buffer.text = "改成用 Rust 写"

        self._binding(prompt).handler(event)

        assert drain_steer(st) == ["改成用 Rust 写"]
        # 输入框内容取走，避免和 Enter 语义重复
        event.current_buffer.reset.assert_called_once()
        event.app.renderer.erase.assert_called_once()

    def test_ctrl_s_when_idle_does_not_inject(self):
        """空闲时没有正在跑的对话，无处可注入 —— 不应污染 steering 区"""
        from fr_cli.ui.prompt.tui import FanRenPrompt

        st = SimpleNamespace(_queue_mgr=SimpleNamespace(is_processing=False))
        prompt = FanRenPrompt(st)
        event = MagicMock()
        event.current_buffer.text = "普通提问"

        self._binding(prompt).handler(event)

        assert steer_count(st) == 0
        event.current_buffer.reset.assert_not_called()

    def test_ctrl_s_with_empty_buffer_is_noop(self):
        from fr_cli.ui.prompt.tui import FanRenPrompt

        st = SimpleNamespace(_queue_mgr=SimpleNamespace(is_processing=True))
        prompt = FanRenPrompt(st)
        event = MagicMock()
        event.current_buffer.text = "   "

        self._binding(prompt).handler(event)

        assert steer_count(st) == 0
        event.current_buffer.reset.assert_not_called()

    def test_ctrl_s_without_queue_mgr_is_noop(self):
        from fr_cli.ui.prompt.tui import FanRenPrompt

        st = SimpleNamespace()
        prompt = FanRenPrompt(st)
        event = MagicMock()
        event.current_buffer.text = "随便写点"

        self._binding(prompt).handler(event)

        assert steer_count(st) == 0


class TestStatusBar:
    def test_queue_depth_and_steer_pending_rendered(self):
        from fr_cli.ui.prompt.status import StatusState

        st = StatusState()
        assert not any("队列" in t for _, t in st.render())

        st.queue_depth = 3
        st.steer_pending = 2
        texts = [t for _, t in st.render()]
        assert any("队列 3" in t for t in texts)
        assert any("↯" in t and "2" in t for t in texts)

    def test_sync_dynamic_status_reads_queue_and_steer(self):
        from fr_cli.ui.prompt.tui import FanRenPrompt

        st = SimpleNamespace(_queue_mgr=SimpleNamespace(is_processing=True, depth=lambda: 4))
        prompt = FanRenPrompt(st)
        push_steer(st, "插一句")

        prompt._sync_dynamic_status()

        assert prompt.status.queue_depth == 4
        assert prompt.status.steer_pending == 1


class TestQueueDepth:
    def test_depth_and_is_busy(self):
        from fr_cli.repl.queue import ChatQueueManager

        mgr = ChatQueueManager(SimpleNamespace(), MagicMock())
        assert mgr.depth() == 0
        assert mgr.is_busy() is False
        mgr.add("问题一")
        assert mgr.depth() == 1
        assert mgr.is_busy() is True
        mgr.clear()
        assert mgr.depth() == 0


# ============================================================
# 3. 对话流水线注入
# ============================================================


def _pipeline_state():
    """造一个够 _stream_and_respond / _run_steer_rounds 用的最小 state"""
    return SimpleNamespace(
        cfg={},
        client=SimpleNamespace(),
        model_name="mock-model",
        provider="mock",
        limit=1000,
        lang="zh",
        messages=[],
        executor=SimpleNamespace(
            process_ai_commands=lambda txt, msgs: (txt, []),
            invoke_tool=lambda name, args: SimpleNamespace(
                is_ok=lambda: True, unwrap=lambda: "ok", error=None,
            ),
        ),
    )


class TestPipelineSteerRounds:
    def test_no_steer_means_no_extra_llm_call(self, monkeypatch):
        from fr_cli.core.chat import pipeline_respond

        calls = []

        def fake_stream_cnt(*a, **kw):
            calls.append(kw)
            return "回答", None, 0.1, False

        monkeypatch.setattr(pipeline_respond, "stream_cnt", fake_stream_cnt)

        st = _pipeline_state()
        msgs = [{"role": "user", "content": "问题"}]
        txt, usage, rt = pipeline_respond._run_steer_rounds(
            st, msgs, "zh", True, None, None, None, "回答", None, 0.1,
        )

        assert calls == []
        assert txt == "回答"
        assert len(msgs) == 1  # 没有注入任何 user 消息

    def test_steer_is_injected_and_llm_reruns(self, monkeypatch):
        from fr_cli.core.chat import pipeline_respond

        calls = []

        def fake_stream_cnt(*a, **kw):
            calls.append(kw)
            return f"回答{len(calls)}", None, 0.1, False

        monkeypatch.setattr(pipeline_respond, "stream_cnt", fake_stream_cnt)

        st = _pipeline_state()
        push_steer(st, "补充：要中文")
        msgs = [{"role": "user", "content": "问题"}]

        txt, usage, rt = pipeline_respond._run_steer_rounds(
            st, msgs, "zh", True, None, None, None, "回答0", None, 0.1,
        )

        assert len(calls) == 1
        assert txt == "回答1"
        # 转向指令以 user 消息身份进入本轮历史
        assert msgs[1] == {"role": "user", "content": "补充：要中文"}
        assert msgs[2]["role"] == "assistant"

    def test_multiple_steer_messages_share_one_round(self, monkeypatch):
        from fr_cli.core.chat import pipeline_respond

        calls = []

        def fake_stream_cnt(*a, **kw):
            calls.append(kw)
            return "x", None, 0.1, False

        monkeypatch.setattr(pipeline_respond, "stream_cnt", fake_stream_cnt)

        st = _pipeline_state()
        push_steer(st, "第一条")
        push_steer(st, "第二条")
        msgs = [{"role": "user", "content": "问题"}]

        pipeline_respond._run_steer_rounds(
            st, msgs, "zh", True, None, None, None, "x", None, 0.1,
        )

        assert len(calls) == 1
        assert [m["content"] for m in msgs if m["role"] == "user"] == [
            "问题", "第一条", "第二条",
        ]

    def test_steer_rounds_are_capped(self, monkeypatch):
        from fr_cli.core.chat import pipeline_respond

        calls = []

        def fake_stream_cnt(*a, **kw):
            calls.append(kw)
            # 每次 LLM 调用后再塞一条新的转向指令 —— 模拟用户狂按 Ctrl+S
            push_steer(st, "再来一条")
            return "x", None, 0.1, False

        monkeypatch.setattr(pipeline_respond, "stream_cnt", fake_stream_cnt)

        st = _pipeline_state()
        push_steer(st, "第一条")
        msgs = [{"role": "user", "content": "问题"}]

        pipeline_respond._run_steer_rounds(
            st, msgs, "zh", True, None, None, None, "x", None, 0.1,
        )

        assert len(calls) == pipeline_respond.MAX_STEER_ROUNDS

    def test_steer_failure_keeps_previous_text(self, monkeypatch):
        from fr_cli.core.chat import pipeline_respond

        def fake_stream_cnt(*a, **kw):
            raise RuntimeError("模型炸了")

        monkeypatch.setattr(pipeline_respond, "stream_cnt", fake_stream_cnt)

        st = _pipeline_state()
        push_steer(st, "改需求")
        msgs = [{"role": "user", "content": "问题"}]

        txt, usage, rt = pipeline_respond._run_steer_rounds(
            st, msgs, "zh", True, None, None, None, "原回答", None, 0.1,
        )

        assert txt == "原回答"


# ============================================================
# 4. MasterAgent ReAct 循环注入
# ============================================================


class _FakeMaster:
    """只提供 MasterAgentLoopMixin.handle() 真正用到的那几个成员"""

    def __init__(self, state):
        self.state = state
        self.session = {"current_task": None, "task_history": [], "context_notes": ""}
        self._status_data = {}
        self._step_count = 0

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


class TestMasterLoopSteering:
    def test_steer_during_generation_is_injected_into_same_turn(self, monkeypatch, tmp_path):
        import fr_cli.core.stream as stream_mod
        from fr_cli.agent.master_loop import MasterAgentLoopMixin

        state = SimpleNamespace(
            model_name="mock-model",
            lang="zh",
            client=SimpleNamespace(),
            provider="mock",
            limit=1000,
            messages=[],
            sn="test-session",
            auto_session_path=str(tmp_path / "session.json"),
            executor=SimpleNamespace(),
        )

        calls = []

        def fake_stream_cnt(client, model, messages, lang, custom_prefix="", max_tokens=2048, silent=True, **kw):
            calls.append(list(messages))
            if len(calls) == 1:
                # 模拟"用户趁模型还在生成时按了 Ctrl+S"
                push_steer(state, "改用 TypeScript")
                return "第一次回答", None, None, None
            return "第二次回答", None, None, None

        monkeypatch.setattr(stream_mod, "stream_cnt", fake_stream_cnt)
        monkeypatch.setattr("fr_cli.agent.master_loop._save_json", lambda *a, **kw: None)
        monkeypatch.setattr("fr_cli.agent.master_loop.save_context", lambda *a, **kw: None)

        master = _FakeMaster(state)
        master.__class__ = type(
            "M", (MasterAgentLoopMixin, _FakeMaster), {}
        )

        answer, cont = master.handle("原始问题")

        assert answer == "第二次回答"
        # 转向指令进入了本轮历史（assistant → user 的顺序正确）
        second_round = calls[1]
        assert second_round[-2]["role"] == "assistant"
        assert second_round[-2]["content"] == "第一次回答"
        assert second_round[-1] == {"role": "user", "content": "改用 TypeScript"}

    def test_steer_without_steer_messages_keeps_single_round(self, monkeypatch, tmp_path):
        import fr_cli.core.stream as stream_mod
        from fr_cli.agent.master_loop import MasterAgentLoopMixin

        state = SimpleNamespace(
            model_name="mock-model",
            lang="zh",
            client=SimpleNamespace(),
            provider="mock",
            limit=1000,
            messages=[],
            sn="test-session",
            auto_session_path=str(tmp_path / "session.json"),
            executor=SimpleNamespace(),
        )

        calls = []

        def fake_stream_cnt(client, model, messages, lang, custom_prefix="", max_tokens=2048, silent=True, **kw):
            calls.append(list(messages))
            return "唯一回答", None, None, None

        monkeypatch.setattr(stream_mod, "stream_cnt", fake_stream_cnt)
        monkeypatch.setattr("fr_cli.agent.master_loop._save_json", lambda *a, **kw: None)
        monkeypatch.setattr("fr_cli.agent.master_loop.save_context", lambda *a, **kw: None)

        master = _FakeMaster(state)
        master.__class__ = type(
            "M", (MasterAgentLoopMixin, _FakeMaster), {}
        )

        answer, cont = master.handle("原始问题")

        assert answer == "唯一回答"
        assert len(calls) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
