"""
上下文压缩测试
"""
from unittest.mock import patch, MagicMock

import pytest


class TestEstimateTokens:
    """测试 token 启发式估算"""

    def test_estimate_text_messages(self):
        from fr_cli.memory.compress import estimate_tokens
        messages = [
            {"role": "system", "content": "a" * 40},
            {"role": "user", "content": "b" * 40},
        ]
        # 40 chars / 4 = 10 + overhead 4 each => 28
        assert estimate_tokens(messages) == 28

    def test_estimate_multimodal_message(self):
        from fr_cli.memory.compress import estimate_tokens
        messages = [
            {"role": "user", "content": [
                {"type": "text", "text": "x" * 40},
                {"type": "image_url", "image_url": {"url": "http://x"}},
            ]},
        ]
        # text 10 + image part 3 chars //4 + overhead
        assert estimate_tokens(messages, overhead=4) >= 14


class TestCompressMessages:
    """测试 compress_messages 摘要压缩"""

    @patch("fr_cli.memory.compress.stream_cnt")
    def test_compresses_old_turns(self, mock_stream):
        from fr_cli.memory.compress import compress_messages

        mock_stream.return_value = ("用户询问了天气并得到了晴天回答。", {}, 0.1, False)
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好"},
            {"role": "user", "content": "天气如何"},
            {"role": "assistant", "content": "晴天"},
            {"role": "user", "content": "现在的问题"},
            {"role": "assistant", "content": "现在的回答"},
        ]
        result = compress_messages(messages, MagicMock(), "m", lang="zh", keep_recent=1)
        # should keep system + summary + recent 1 turn
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "system"
        assert "历史摘要" in result[1]["content"]
        assert result[-2]["content"] == "现在的问题"
        assert result[-1]["content"] == "现在的回答"

    def test_no_compress_short_history(self):
        from fr_cli.memory.compress import compress_messages
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "a"},
        ]
        result = compress_messages(messages, MagicMock(), "m", keep_recent=5)
        assert result == messages


class TestMaybeCompress:
    """测试 maybe_compress 阈值判断"""

    @patch("fr_cli.memory.compress.stream_cnt")
    def test_compresses_when_over_threshold(self, mock_stream):
        from fr_cli.memory.compress import maybe_compress, estimate_tokens

        long_text = "x" * 4000  # ~1000 tokens
        messages = [{"role": "user", "content": long_text}] * 10
        before = estimate_tokens(messages)
        mock_stream.return_value = ("summary", {}, 0.1, False)
        compressed, did_compress, b, a = maybe_compress(
            messages, MagicMock(), "m", threshold=100, keep_recent=2
        )
        assert did_compress is True
        assert b == before
        assert a < b

    def test_no_compress_when_under_threshold(self):
        from fr_cli.memory.compress import maybe_compress
        messages = [{"role": "user", "content": "hi"}]
        compressed, did_compress, b, a = maybe_compress(
            messages, MagicMock(), "m", threshold=1000
        )
        assert did_compress is False
        assert b == a

    def test_disabled_when_threshold_zero(self):
        from fr_cli.memory.compress import maybe_compress
        messages = [{"role": "user", "content": "x" * 10000}] * 10
        compressed, did_compress, b, a = maybe_compress(
            messages, MagicMock(), "m", threshold=0
        )
        assert did_compress is False


class TestContextReplCommand:
    """测试 REPL /context 命令"""

    def test_threshold_set(self, capsys):
        from fr_cli.repl.commands.system import _cmd_context
        state = MagicMock()
        state.lang = "zh"
        state.context_compress_threshold = 8000
        state.context_compress_keep_recent = 5
        state.messages = []
        state.model_name = "m"
        state.client = MagicMock()

        _cmd_context(state, ["/context", "threshold", "5000"])
        state.update_context_compress_threshold.assert_called_once_with(5000)
        out = capsys.readouterr().out
        assert "5000" in out

    def test_compress_command(self, capsys):
        from fr_cli.repl.commands.system import _cmd_context
        state = MagicMock()
        state.lang = "zh"
        state.context_compress_threshold = 8000
        state.context_compress_keep_recent = 2
        state.messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c"},
            {"role": "assistant", "content": "d"},
            {"role": "user", "content": "e"},
        ]
        state.model_name = "m"
        state.client = MagicMock()

        with patch("fr_cli.repl.commands.system.context.maybe_compress") as mock_mc:
            mock_mc.return_value = ([{"role": "system", "content": "compressed"}], True, 100, 20)
            _cmd_context(state, ["/context", "compress"])

        assert len(state.messages) == 1
        out = capsys.readouterr().out
        assert "已压缩" in out
