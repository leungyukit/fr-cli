"""TUI 语义色分层的回归测试（v2.8.7 第四阶段）

颜色即语义：
- **回答**（最终答案）→ 绿色
- **思考过程**（推理模型的 reasoning）→ 暗色（视觉上退到背景）
- **模型向用户提出的问题** → 青色（启发式：以问号结尾的行）
- **成功状态** → 绿 / **失败状态** → 红 / **等待状态** → 黄
"""
import io
from contextlib import redirect_stdout

import pytest

from fr_cli.ui.ui import CYAN, DIM, GREEN, RED


@pytest.fixture(autouse=True)
def _colors_on(monkeypatch):
    """强制打开颜色。

    pytest 是非 TTY → ``color_enabled()`` 为假 → 颜色常量被清空、
    ``print_styled`` 也会剥掉转义序列。用 ``FORCE_COLOR`` 打开环境判定，
    再把全局颜色状态置回"有色"，测完原样还原。
    """
    from fr_cli.ui import ui
    monkeypatch.setenv("FORCE_COLOR", "1")
    original = ui._NO_COLOR
    ui.set_no_color(False)
    try:
        yield
    finally:
        ui.set_no_color(original)


class TestMarkdownRendererSemanticColors:
    """markdown 流式渲染器的语义色"""

    def _render(self, text, mode="answer"):
        from fr_cli.ui.markdown_stream import StreamingMarkdownRenderer
        r = StreamingMarkdownRenderer(use_color=True)
        r.set_mode(mode)
        return r.feed(text)

    def test_answer_is_green(self):
        out = self._render("这是一段回答。\n")
        assert GREEN in out
        assert DIM not in out

    def test_reasoning_is_dim(self):
        out = self._render("这是思考过程。\n", mode="reasoning")
        assert DIM in out
        assert GREEN not in out

    def test_question_line_is_cyan(self):
        """模型向用户提问的行 → 青色（启发式）"""
        out = self._render("请问您想用哪个方案？\n")
        assert CYAN in out

    def test_question_line_english(self):
        out = self._render("Which one do you prefer?\n")
        assert CYAN in out

    def test_statement_is_not_cyan(self):
        """陈述句不该被当成提问"""
        out = self._render("这是陈述句。\n")
        assert CYAN not in out

    def test_bold_question_still_cyan(self):
        """行内 markdown 标记不该影响问句判定"""
        out = self._render("**要哪个？**\n")
        assert CYAN in out

    def test_structural_blocks_keep_own_color(self):
        """标题等结构性元素保持自己的配色"""
        out = self._render("# 标题\n")
        assert CYAN in out          # 一级标题本来就是青色系
        assert GREEN not in out


class TestStreamSemanticColors:
    """stream_cnt 层的语义色"""

    def _run(self, chunks):
        from fr_cli.core.stream import stream_cnt

        class _C:
            api_key = "sk-1234567890abcdef"

            def stream_chat(self, model, messages, max_tokens=4096, timeout=60):
                for c in chunks:
                    yield c

        buf = io.StringIO()
        with redirect_stdout(buf):
            txt, _u, _r, _i = stream_cnt(_C(), "m", [{"role": "user", "content": "hi"}], "zh")
        return buf.getvalue(), txt

    def test_reasoning_chunk_is_dim_answer_is_green(self):
        out, txt = self._run([
            {"content": "先想想", "reasoning": True},
            {"content": "最终答案"},
        ])
        assert DIM in out          # 思考是暗色
        assert GREEN in out        # 答案是绿色
        assert txt == "最终答案"   # 返回文本仍只有答案

    def test_plain_chunk_green(self):
        out, txt = self._run([{"content": "普通回答"}])
        assert GREEN in out
        assert txt == "普通回答"


class TestToolResultEcho:
    """工具执行结果回显（成功绿 / 失败红）"""

    def test_success_echo_green(self):
        from fr_cli.command.executor_dispatch import _echo_tool_result
        buf = io.StringIO()
        with redirect_stdout(buf):
            _echo_tool_result(None, "write_file", ok=True)
        out = buf.getvalue()
        assert "✓ write_file" in out
        assert GREEN in out

    def test_failure_echo_red_with_reason(self):
        from fr_cli.command.executor_dispatch import _echo_tool_result
        buf = io.StringIO()
        with redirect_stdout(buf):
            _echo_tool_result(None, "write_file", ok=False, error="路径不在允许目录内")
        out = buf.getvalue()
        assert "✗ write_file" in out
        assert "路径不在允许目录内" in out
        assert RED in out

    def test_headless_is_silent(self, monkeypatch):
        from fr_cli.command.executor_dispatch import _echo_tool_result
        state = type("S", (), {"headless": True})()
        buf = io.StringIO()
        with redirect_stdout(buf):
            _echo_tool_result(state, "write_file", ok=True)
        assert buf.getvalue() == ""

    def test_non_interactive_is_silent(self, monkeypatch):
        from fr_cli.command.executor_dispatch import _echo_tool_result
        monkeypatch.setenv("FR_CLI_NON_INTERACTIVE", "1")
        buf = io.StringIO()
        with redirect_stdout(buf):
            _echo_tool_result(None, "write_file", ok=True)
        assert buf.getvalue() == ""


class TestStatusColors:
    """状态栏语义色：等待=黄，失败=红"""

    def test_busy_is_yellow(self):
        from fr_cli.ui.prompt.status import StatusState
        st = StatusState()
        st.is_busy = True
        rendered = "".join(t for _s, t in st.render(0))
        assert "思考中" in rendered
        assert "class:status-yellow" in "".join(s for s, _t in st.render(0))

    def test_tool_error_is_red(self):
        from fr_cli.ui.prompt.status import StatusState
        st = StatusState()
        st.tool_name = "write_file"
        st.tool_started = 1.0
        st.tool_error = "失败"
        styles = [s for s, _t in st.render(0)]
        assert "class:status-red" in styles
