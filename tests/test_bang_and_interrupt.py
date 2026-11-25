"""! shell 直执行 / 管道模式 + Ctrl+C 中断流式 回归测试"""
import io
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import MagicMock

from fr_cli.repl.bang import handle_bang


class _FakeQueue:
    def __init__(self, processing=False):
        self.is_processing = processing
        self.processed = []

    def process(self, u):
        self.processed.append(u)


def _state(**kw):
    st = SimpleNamespace(lang="zh", messages=[], _queue_mgr=_FakeQueue())
    for k, v in kw.items():
        setattr(st, k, v)
    return st


class TestBangPlainMode:
    def test_empty_shows_usage(self):
        out = io.StringIO()
        with redirect_stdout(out):
            assert handle_bang(_state(), "  ") is True
        assert "用法" in out.getvalue()

    def test_pipe_without_command_shows_warning(self):
        out = io.StringIO()
        with redirect_stdout(out):
            assert handle_bang(_state(), "  | 分析一下") is True
        assert "需要跟命令" in out.getvalue()

    def test_executes_and_displays(self):
        out = io.StringIO()
        with redirect_stdout(out):
            assert handle_bang(_state(), "echo hello-bang") is True
        text = out.getvalue()
        assert "hello-bang" in text
        # 普通模式不进上下文
        st = _state()
        with redirect_stdout(io.StringIO()):
            handle_bang(st, "echo x")
        assert st.messages == []

    def test_nonzero_exit_code_shown(self):
        out = io.StringIO()
        with redirect_stdout(out):
            handle_bang(_state(), "exit 3")
        assert "退出码 3" in out.getvalue()


class TestBangPipeMode:
    def test_pipe_feeds_ai_context_and_queue(self):
        st = _state()
        out = io.StringIO()
        with redirect_stdout(out):
            assert handle_bang(st, "echo pipe-data | 总结这段输出") is True
        # 输出作为 user 消息进入上下文
        assert len(st.messages) == 1
        msg = st.messages[0]
        assert msg["role"] == "user"
        assert "pipe-data" in msg["content"]
        assert "echo pipe-data" in msg["content"]
        # 问题入队
        assert st._queue_mgr.processed == ["总结这段输出"]
        # 管道模式不直接回显输出
        assert "pipe-data" not in out.getvalue()

    def test_pipe_when_busy_shows_queue_hint(self):
        st = _state(_queue_mgr=_FakeQueue(processing=True))
        out = io.StringIO()
        with redirect_stdout(out):
            handle_bang(st, "echo x | 问题")
        assert "已加入队列" in out.getvalue()
        assert st._queue_mgr.processed == ["问题"]

    def test_pipe_truncates_long_output(self):
        st = _state()
        with redirect_stdout(io.StringIO()):
            handle_bang(st, "python3 -c \"print('a'*5000)\" | 总结")
        content = st.messages[0]["content"]
        assert "已截断" in content
        assert len(content) < 4200


class TestCtrlCInterruptBinding:
    def test_ctrl_c_requests_interrupt_when_processing(self):
        """Ctrl+C 在 AI 回答中应请求中断流式输出，且**保留草稿**"""
        import fr_cli.core.stream as stream_mod
        from fr_cli.ui.prompt.tui import FanRenPrompt

        stream_mod._current_interrupt.reset()
        st = SimpleNamespace(_queue_mgr=SimpleNamespace(is_processing=True))
        prompt = FanRenPrompt(st)
        try:
            binding = next(
                b for b in prompt._kb.bindings if b.keys == ("c-c",)
            )
            event = MagicMock()
            binding.handler(event)
            assert stream_mod._current_interrupt.is_set() is True
            # v2.8.7(UX)：生成中按 Ctrl+C 只打断，**不清空草稿**
            # （用户多半是"等太久了"，草稿被误清是伤人的）
            event.current_buffer.reset.assert_not_called()
            event.app.renderer.erase.assert_not_called()
        finally:
            stream_mod._current_interrupt.reset()

    def test_ctrl_c_no_interrupt_when_idle(self):
        """空闲时 Ctrl+C 只清输入,不设中断标志"""
        import fr_cli.core.stream as stream_mod
        from fr_cli.ui.prompt.tui import FanRenPrompt

        stream_mod._current_interrupt.reset()
        st = SimpleNamespace(_queue_mgr=SimpleNamespace(is_processing=False))
        prompt = FanRenPrompt(st)
        try:
            binding = next(
                b for b in prompt._kb.bindings if b.keys == ("c-c",)
            )
            event = MagicMock()
            binding.handler(event)
            assert stream_mod._current_interrupt.is_set() is False
            # 空闲时保持传统语义:清空输入 + 擦除渲染
            event.current_buffer.reset.assert_called_once()
            event.app.renderer.erase.assert_called_once()
        finally:
            stream_mod._current_interrupt.reset()

    def test_ctrl_c_without_queue_mgr_clears_buffer(self):
        """没有队列管理器(极简模式)时 Ctrl+C 仍应清空输入"""
        import fr_cli.core.stream as stream_mod
        from fr_cli.ui.prompt.tui import FanRenPrompt

        stream_mod._current_interrupt.reset()
        prompt = FanRenPrompt(SimpleNamespace())
        try:
            binding = next(
                b for b in prompt._kb.bindings if b.keys == ("c-c",)
            )
            event = MagicMock()
            binding.handler(event)
            assert stream_mod._current_interrupt.is_set() is False
            event.current_buffer.reset.assert_called_once()
        finally:
            stream_mod._current_interrupt.reset()
