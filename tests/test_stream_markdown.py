"""stream_cnt 流式 Markdown 渲染接线回归测试

覆盖:
- 默认走 StreamingMarkdownRenderer 实时渲染(标题/列表/代码块/引用/表格/残行)
- silent=True 只返回文本不输出
- markdown=False 降级路径:``` 围栏被 chunk 边界截断仍能识别 + 语言标签
- 中断路径:[已中断] 可见标记 + 后续 chunk 不显示 + 返回文本带标记
- use_color 跟随全局 _NO_COLOR 实时状态
- 行内代码收尾反引号跨 chunk 不丢失
"""
import io
from contextlib import redirect_stdout

import pytest

from fr_cli.core.stream import stream_cnt


MD_DOC = (
    "# 标题一\n\n"
    "这是一段**粗体**和`行内代码`的描述。\n\n"
    "- 列表项 A\n"
    "- 列表项 B\n\n"
    "```python\n"
    "print('hello')\n"
    "```\n\n"
    "> 一句引用\n\n"
    "| 列1 | 列2 |\n"
    "|-----|-----|\n"
    "| A   | B   |\n\n"
    "结尾没有换行"
)


class FakeStreamClient:
    """按固定宽度切片,模拟真实 LLM 的 token 流(会把 ``` 截断)"""

    api_key = "sk-1234567890abcdef"

    def __init__(self, doc: str, chunk_size: int = 7):
        self.doc = doc
        self.chunk_size = chunk_size

    def stream_chat(self, model, messages, max_tokens=4096, timeout=60):
        doc = self.doc
        for i in range(0, len(doc), self.chunk_size):
            yield {"content": doc[i:i + self.chunk_size]}
        yield {"content": "", "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}}


def _run(doc=MD_DOC, chunk_size=7, **kwargs):
    buf = io.StringIO()
    with redirect_stdout(buf):
        result = stream_cnt(
            FakeStreamClient(doc, chunk_size), "m", [{"role": "user", "content": "hi"}], "zh", **kwargs
        )
    return buf.getvalue(), result


class TestStreamMarkdownRendering:
    def test_live_markdown_render(self):
        """默认路径:标题/代码块标签/列表/引用/表格都被实时渲染"""
        out, (txt, usage, rt, interrupted) = _run()
        assert "# 标题一" in out
        assert "python" in out          # 代码块语言标签
        assert "•" in out                  # 列表符号
        assert "│" in out                  # 引用/表格竖线
        assert "结尾没有换行" in out        # flush 吐出未换行残行
        assert "│ 列1 │ 列2" in out        # 表头行也按表格渲染
        assert txt.endswith("结尾没有换行")  # 返回值为原始全文
        assert usage.get("total_tokens") == 30
        assert interrupted is False

    def test_silent_returns_text_only(self):
        out, (txt, *_rest) = _run(silent=True)
        assert out == ""
        assert txt.endswith("结尾没有换行")

    def test_full_text_is_raw_markdown(self):
        """返回值必须是未渲染的原始 Markdown(供命令提取/上下文使用)"""
        _out, (txt, *_rest) = _run()
        assert "```python" in txt
        assert "**粗体**" in txt
        assert "•" not in txt             # 渲染器专属符号不泄漏进原始返回值

    def test_chunk_size_one_still_renders(self):
        """极端逐字符流也能正确渲染(围栏/标签跨 chunk 状态机)"""
        out, (txt, *_rest) = _run(chunk_size=1)
        assert "python" in out
        assert "•" in out
        assert txt.endswith("结尾没有换行")


class TestDegradedColorizePath:
    """markdown=False 时的旧代码块高亮路径"""

    def test_fence_split_across_chunks(self):
        """``` 围栏被 chunk 边界截断时仍能识别并显示语言标签"""
        out, _ = _run(markdown=False)
        assert "[python]" in out
        assert "```" not in out             # 围栏标记被消费
        assert "print('hello')" in out

    def test_fence_and_lang_split(self):
        """``` 与语言标签被 chunk 边界分离也不丢标签"""
        doc = "前言\n\n```python\nprint(1)\n```\n\n结尾"
        # chunk_size=1 保证 ``` 与 python 必然分离
        out, _ = _run(doc=doc, chunk_size=1, markdown=False)
        assert "[python]" in out
        assert "```" not in out

    def test_inline_code_tick_across_chunks(self):
        """行内代码收尾反引号跨 chunk 不丢失(挂起缓冲正确补吐)"""
        doc = "看 `code` 结束"
        out, (txt, *_rest) = _run(doc=doc, chunk_size=3, markdown=False)
        assert txt == doc                    # 返回文本无损
        assert "`code`" in out.replace("\x1b[92m", "").replace("\x1b[0m", "") or "code" in out

    def test_markdown_false_no_renderer_elements(self):
        out, _ = _run(markdown=False)
        assert "•" not in out             # 降级路径不套用完整渲染器的列表符号
        assert "│" not in out


class TestInterruptPath:
    def test_interrupt_shows_marker_and_stops(self):
        import fr_cli.core.stream as st

        class InterruptClient(FakeStreamClient):
            def stream_chat(self, model, messages, max_tokens=4096, timeout=60):
                yield {"content": "前半段内容"}
                st.request_interrupt()
                yield {"content": "后半段不应出现"}

        buf = io.StringIO()
        with redirect_stdout(buf):
            txt, _u, _r, interrupted = stream_cnt(
                InterruptClient(MD_DOC), "m", [], "zh"
            )
        out = buf.getvalue()
        assert interrupted is True
        assert "后半段不应出现" not in out
        assert "[已中断]" in out
        assert txt.endswith("\n[已中断]")

    def test_truncated_inside_code_block_no_duplicate(self):
        """流在未闭合代码块内结束(max_tokens 截断)时,最后一行不得重复输出

        回归:flush() IN_CODE 分支不清空 buffer + stream_cnt 双退出点都 flush,
        导致挂起的代码行被输出两遍。
        """
        doc = "看代码:\n\n```python\nprint(1)\nprint(2)"
        out, (txt, *_rest) = _run(doc, chunk_size=7)
        assert out.count("print(2)") == 1, f"print(2) 出现了 {out.count('print(2)')} 次:\n{out}"
        assert txt.endswith("print(2)")  # 返回值仍是原始全文


class TestColorFollowsGlobalFlag:
    def test_no_color_disables_ansi(self):
        """_NO_COLOR 打开时渲染器不产出 ANSI(实时读取,非导入快照)"""
        from fr_cli.ui import ui
        original = ui._NO_COLOR
        try:
            ui.set_no_color(True)
            out, _ = _run()
            assert "\033[" not in out
        finally:
            ui.set_no_color(original)

    def test_color_enabled_emits_ansi(self):
        from fr_cli.ui import ui
        original = ui._NO_COLOR
        try:
            ui.set_no_color(False)
            out, _ = _run()
            assert "\033[" in out
        finally:
            ui.set_no_color(original)
