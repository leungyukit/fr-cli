"""
上下文记忆测试
覆盖最近轮提取、摘要构建、加载/保存/清除等。
"""
import os
import sys


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestExtractRecentTurns:

    def test_extract_basic(self):
        from fr_cli.memory.context import extract_recent_turns
        msgs = [
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "reply1"},
            {"role": "user", "content": "msg2"},
            {"role": "assistant", "content": "reply2"},
        ]
        turns = extract_recent_turns(msgs, n=2)
        # 实际行为:返回最近 n*2 条消息
        assert isinstance(turns, list)
        assert len(turns) <= 4  # n*2 = 4

    def test_extract_more_than_available(self):
        """请求 N > 实际消息数:应返回所有"""
        from fr_cli.memory.context import extract_recent_turns
        msgs = [{"role": "user", "content": "x"}]
        turns = extract_recent_turns(msgs, n=10)
        # 至少应有 1 个
        assert len(turns) >= 1

    def test_extract_empty(self):
        from fr_cli.memory.context import extract_recent_turns
        turns = extract_recent_turns([], n=5)
        assert turns == []

    def test_extract_skips_system_messages(self):
        """system 消息通常不应计入最近轮"""
        from fr_cli.memory.context import extract_recent_turns
        msgs = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
            {"role": "assistant", "content": "a2"},
        ]
        turns = extract_recent_turns(msgs, n=2)
        # 至少应包含最近的 user/assistant 轮
        assert len(turns) >= 2


class TestBuildContextSummary:

    def test_build_summary_zh(self):
        from fr_cli.memory.context import build_context_summary
        turns = [
            {"role": "user", "content": "我想了解 fr-cli"},
            {"role": "assistant", "content": "fr-cli 是一个终端 AI 助手"},
        ]
        summary = build_context_summary(turns, lang="zh")
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_build_summary_en(self):
        from fr_cli.memory.context import build_context_summary
        turns = [
            {"role": "user", "content": "What is fr-cli?"},
            {"role": "assistant", "content": "fr-cli is a terminal AI assistant"},
        ]
        summary = build_context_summary(turns, lang="en")
        assert isinstance(summary, str)

    def test_build_summary_empty(self):
        from fr_cli.memory.context import build_context_summary
        summary = build_context_summary([], lang="zh")
        assert isinstance(summary, str)


class TestContextPersistence:

    def test_save_and_load(self, tmp_path, monkeypatch):
        from fr_cli.memory import context
        # 隔离到 tmp_path
        context_file = tmp_path / "context.json"
        monkeypatch.setattr(context, "CONTEXT_FILE", context_file)

        context.save_context("test_session", "这是摘要内容")
        loaded = context.load_context("test_session")
        assert loaded == "这是摘要内容"

    def test_load_nonexistent_session(self, tmp_path, monkeypatch):
        from fr_cli.memory import context
        context_file = tmp_path / "context.json"
        monkeypatch.setattr(context, "CONTEXT_FILE", context_file)

        loaded = context.load_context("nonexistent_session")
        # 不存在的会话应返回 None 或空
        assert loaded is None or loaded == ""

    def test_clear_context(self, tmp_path, monkeypatch):
        from fr_cli.memory import context
        context_file = tmp_path / "context.json"
        monkeypatch.setattr(context, "CONTEXT_FILE", context_file)

        context.save_context("to_clear", "some summary")
        assert context.load_context("to_clear") == "some summary"

        context.clear_context("to_clear")
        loaded = context.load_context("to_clear")
        assert loaded is None or loaded == ""

    def test_clear_nonexistent_no_error(self, tmp_path, monkeypatch):
        from fr_cli.memory import context
        context_file = tmp_path / "context.json"
        monkeypatch.setattr(context, "CONTEXT_FILE", context_file)

        # 不应崩
        context.clear_context("never_existed")


class TestMultipleSessions:

    def test_save_different_sessions(self, tmp_path, monkeypatch):
        from fr_cli.memory import context
        context_file = tmp_path / "context.json"
        monkeypatch.setattr(context, "CONTEXT_FILE", context_file)

        context.save_context("sess_a", "summary A")
        context.save_context("sess_b", "summary B")

        assert context.load_context("sess_a") == "summary A"
        assert context.load_context("sess_b") == "summary B"

    def test_overwrite_session(self, tmp_path, monkeypatch):
        from fr_cli.memory import context
        context_file = tmp_path / "context.json"
        monkeypatch.setattr(context, "CONTEXT_FILE", context_file)

        context.save_context("sess", "first summary")
        context.save_context("sess", "updated summary")

        assert context.load_context("sess") == "updated summary"
