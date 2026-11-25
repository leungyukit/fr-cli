"""推理模型「思考过程」与「最终答案」分离的回归测试

背景(v2.8.7 第四阶段):
stepfun step-5 / GLM thinking 系 / 火山方舟 thinking 系把思考过程下发到
``delta.reasoning_content``、把最终答案下发到 ``delta.content``。两者混在一起时,
思考会被当成答案写进历史/记忆,并污染二次提问的上下文。

覆盖:
- ``BaseLLMClient._yield_chunks``:content 语义不变,只有取自 reasoning_content
  的分片才追加 ``reasoning: True`` 标记(无推理时 chunk 形状零变化)
- 同一 delta 同时带 content 与 reasoning_content 时以 content 为准(答案通道)
- ``stream_cnt``:思考不计入返回文本,但仍照常显示
- 兜底:答案只出现在 reasoning_content(火山方舟 coding endpoint)时,思考内容
  作为答案返回,避免「答非所问」
"""
import io
from contextlib import redirect_stdout
from types import SimpleNamespace

from fr_cli.core.llm.base import BaseLLMClient
from fr_cli.core.stream import stream_cnt


def _make_chunk(content=None, reasoning_content=None, usage=None):
    """构造一个假的 OpenAI streaming chunk"""
    delta = SimpleNamespace(
        content=content,
        reasoning_content=reasoning_content,
        role="assistant",
    )
    chunk = SimpleNamespace(choices=[SimpleNamespace(delta=delta, index=0)], usage=usage)
    return chunk


class TestYieldChunksReasoningMark:
    """_yield_chunks 的推理标记"""

    def test_reasoning_chunk_is_marked(self):
        """content 为空、reasoning_content 有值 → 标记 reasoning=True"""
        chunks = [
            _make_chunk(content="", reasoning_content="我在想"),
            _make_chunk(content="", reasoning_content="答案"),
        ]
        result = list(BaseLLMClient._yield_chunks(iter(chunks)))
        # content 语义保持不变(既有调用方与测试不受影响)
        assert [r["content"] for r in result] == ["我在想", "答案"]
        # 思考分片带标记
        assert result[0].get("reasoning") is True
        assert result[1].get("reasoning") is True

    def test_answer_chunk_has_no_reasoning_key(self):
        """答案分片不带 reasoning 键 —— chunk 形状零变化"""
        chunks = [_make_chunk(content="你好"), _make_chunk(content="")]
        result = list(BaseLLMClient._yield_chunks(iter(chunks)))
        assert "reasoning" not in result[0]
        assert "reasoning" not in result[1]
        assert result[0] == {"content": "你好", "usage": None}

    def test_content_wins_when_both_present(self):
        """同包并存时以 content 为准(content 才是答案)"""
        chunks = [_make_chunk(content="修仙是凡人", reasoning_content="。")]
        result = list(BaseLLMClient._yield_chunks(iter(chunks)))
        assert result[0]["content"] == "修仙是凡人"
        assert "reasoning" not in result[0]

    def test_empty_chunk_shape_unchanged(self):
        """既有的空 chunk 形状断言保持不变"""
        result = list(BaseLLMClient._yield_chunks(iter([_make_chunk(content=None, reasoning_content=None)])))
        assert result == [{"content": "", "usage": None}]


class ReasoningStreamClient:
    """按序下发 reasoning / content 分片的假客户端"""

    api_key = "sk-1234567890abcdef"

    def __init__(self, chunks):
        self.chunks = chunks

    def stream_chat(self, model, messages, max_tokens=4096, timeout=60):
        for chunk in self.chunks:
            yield chunk


def _run(chunks, **kwargs):
    buf = io.StringIO()
    with redirect_stdout(buf):
        result = stream_cnt(
            ReasoningStreamClient(chunks), "m", [{"role": "user", "content": "hi"}], "zh",
            **kwargs,
        )
    return buf.getvalue(), result


class TestStreamCntSeparation:
    """stream_cnt 的思考/答案分离"""

    def test_reasoning_not_in_returned_text(self):
        """思考不进返回文本,答案才进"""
        out, (txt, *_rest) = _run([
            {"content": "先想想", "reasoning": True},
            {"content": "再想想", "reasoning": True},
            {"content": "最终答案"},
        ])
        assert txt == "最终答案"
        assert "先想想" not in txt
        assert "再想想" not in txt

    def test_reasoning_still_displayed(self):
        """思考照常显示在终端(渲染体验与之前一致)"""
        out, _ = _run([
            {"content": "先想想", "reasoning": True},
            {"content": "最终答案"},
        ])
        assert "先想想" in out
        assert "最终答案" in out

    def test_silent_mode_separates_too(self):
        """silent=True 同样分离(返回值语义与显示无关)"""
        out, (txt, *_rest) = _run([
            {"content": "思考中", "reasoning": True},
            {"content": "答案"},
        ], silent=True)
        assert out == ""
        assert txt == "答案"

    def test_answer_only_reasoning_falls_back(self):
        """兜底:答案只在 reasoning_content 里 → 把思考当答案返回(火山方舟)"""
        out, (txt, *_rest) = _run([
            {"content": "答案是42", "reasoning": True},
        ])
        assert txt == "答案是42"

    def test_mixed_reasoning_then_content(self):
        """混合模式:思考一段后切到答案 —— 只有答案进返回值"""
        out, (txt, *_rest) = _run([
            {"content": "思考1", "reasoning": True},
            {"content": "答案"},
        ])
        assert txt == "答案"
        assert "思考1" in out

    def test_no_reasoning_behavior_unchanged(self):
        """普通模型(无 reasoning 标记)行为完全不变"""
        out, (txt, usage, rt, interrupted) = _run([
            {"content": "你好"},
            {"content": "世界"},
        ])
        assert txt == "你好世界"
        assert interrupted is False
