"""
Bot 统一适配层核心测试

覆盖：消息模型 / 路由 / 去重 / 会话隔离 / 确认代理 / 状态池 / 调度器。
"""
import threading
import time

import pytest

from fr_cli.bot.core.channel import Channel, get_channel_class, list_channel_classes, register_channel
from fr_cli.bot.core.confirm import BotConfirmStrategy, format_confirm_question
from fr_cli.bot.core.confirm_broker import ConfirmBroker
from fr_cli.bot.core.dispatcher import BotDispatcher
from fr_cli.bot.core.idempotency import IdempotencyGuard
from fr_cli.bot.core.message import BotMessage, BotReply
from fr_cli.bot.core.router import RouteRule, Router
from fr_cli.bot.core.session_store import SessionStore
from fr_cli.bot.core.state_pool import StatePool


# ------------------------------------------------------------------
# 消息模型
# ------------------------------------------------------------------

class TestBotMessage:
    def test_session_key_includes_thread(self):
        m = BotMessage(channel="lark", chat_id="oc_1", thread_id="t1")
        assert m.session_key == "lark:oc_1:t1"

    def test_session_key_differs_per_thread(self):
        a = BotMessage(channel="lark", chat_id="oc_1", thread_id="t1")
        b = BotMessage(channel="lark", chat_id="oc_1", thread_id="t2")
        assert a.session_key != b.session_key

    def test_dedup_key_uses_message_id(self):
        m = BotMessage(channel="lark", chat_id="c", message_id="m1")
        assert m.dedup_key == "lark:m1"

    def test_dedup_key_falls_back_to_hash(self):
        m = BotMessage(channel="lark", chat_id="c", text="hi", ts=100.0)
        assert m.dedup_key.startswith("lark:anon:")

    def test_is_private(self):
        assert BotMessage(channel="lark", chat_id="u1", user_id="u1").is_private
        assert not BotMessage(channel="lark", chat_id="oc", user_id="u1").is_private

    def test_with_text_keeps_other_fields(self):
        m = BotMessage(channel="lark", chat_id="c", user_id="u", text="@bot hi")
        n = m.with_text("hi")
        assert n.text == "hi"
        assert n.user_id == "u"
        assert m.text == "@bot hi"  # 原对象不变


class TestBotReply:
    def test_ok_property(self):
        assert BotReply(chat_id="c", text="x").ok is True
        assert BotReply(chat_id="c", text="x", error="boom").ok is False


# ------------------------------------------------------------------
# 通道抽象
# ------------------------------------------------------------------

class TestChannelRegistry:
    def test_register_and_list(self):
        @register_channel
        class _TmpChannel(Channel):
            name = "_tmp_test_channel"
        try:
            assert "_tmp_test_channel" in list_channel_classes()
            assert get_channel_class("_tmp_test_channel") is _TmpChannel
        finally:
            from fr_cli.bot.core.channel import _channel_classes
            _channel_classes.pop("_tmp_test_channel", None)

    def test_register_requires_name(self):
        with pytest.raises(ValueError):
            @register_channel
            class _Bad(Channel):
                pass

    def test_base_parse_not_implemented(self):
        with pytest.raises(NotImplementedError):
            Channel().parse({}, {})

    def test_default_verify_passes(self):
        assert Channel().verify({}, {}) is True

    def test_send_stream_falls_back_to_send(self):
        calls = []

        class _C(Channel):
            name = "_tmp_stream"

            def send(self, reply):
                calls.append(reply.text)
                return reply

        c = _C()
        c.send_stream("chat", ["a", "b", "c"])
        assert calls == ["abc"]


# ------------------------------------------------------------------
# 路由
# ------------------------------------------------------------------

class TestRouter:
    def _router(self, **kw):
        kw.setdefault("bot_names", ["凡人"])
        return Router(**kw)

    def test_group_without_mention_ignored(self):
        r = self._router()
        m = BotMessage(channel="lark", chat_id="oc_1", user_id="u1", text="闲聊")
        d = r.route(m)
        assert d.handled is False
        assert "未被 @" in d.reason

    def test_group_with_mention_answered(self):
        r = self._router()
        m = BotMessage(channel="lark", chat_id="oc_1", user_id="u1",
                        text="@凡人 帮我看下", mentioned=True)
        d = r.route(m)
        assert d.handled is True
        assert d.action == "chat"
        assert d.text == "帮我看下"

    def test_private_message_answered(self):
        r = self._router()
        m = BotMessage(channel="lark", chat_id="u1", user_id="u1", text="你好")
        d = r.route(m)
        assert d.handled is True
        assert d.text == "你好"

    def test_command_prefix(self):
        r = self._router()
        m = BotMessage(channel="lark", chat_id="u1", user_id="u1", text="/status")
        d = r.route(m)
        assert d.action == "command"

    def test_group_whitelist_blocks_other_groups(self):
        r = self._router(group_whitelist=["oc_ok"])
        m = BotMessage(channel="lark", chat_id="oc_bad", user_id="u1",
                        text="@凡人 hi", mentioned=True)
        assert r.route(m).handled is False

    def test_strip_mention_with_colon(self):
        r = self._router()
        m = BotMessage(channel="lark", chat_id="u1", user_id="u1",
                        text="@凡人: 帮我查天气", mentioned=True)
        assert r.route(m).text == "帮我查天气"

    def test_empty_message_ignored(self):
        r = self._router()
        assert r.route(BotMessage(channel="lark", chat_id="u1", user_id="u1", text="  ")).handled is False

    def test_custom_rule_priority(self):
        r = self._router()
        r.add_rule(RouteRule(name="always", matcher=lambda m: True,
                             action="ignore", priority=1))
        m = BotMessage(channel="lark", chat_id="u1", user_id="u1", text="hi")
        assert r.route(m).handled is False


# ------------------------------------------------------------------
# 去重
# ------------------------------------------------------------------

class TestIdempotencyGuard:
    def test_duplicate_detected(self):
        g = IdempotencyGuard(ttl=60)
        assert g.check_and_mark("k1") is False   # 首次
        assert g.check_and_mark("k1") is True    # 重复

    def test_ttl_expiry(self):
        g = IdempotencyGuard(ttl=1)
        g.check_and_mark("k1", now=100.0)
        assert g.check_and_mark("k1", now=102.0) is False

    def test_forget(self):
        g = IdempotencyGuard()
        g.check_and_mark("k1")
        g.forget("k1")
        assert g.check_and_mark("k1") is False

    def test_stats(self):
        g = IdempotencyGuard()
        g.check_and_mark("k1")
        g.check_and_mark("k1")
        st = g.stats()
        assert st["duplicates"] == 1
        assert st["accepted"] == 1

    def test_thread_safety(self):
        g = IdempotencyGuard()
        results = []

        def worker():
            results.append(g.check_and_mark("same"))

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert results.count(False) == 1   # 只有一个线程抢到首次
        assert results.count(True) == 19


# ------------------------------------------------------------------
# 会话隔离
# ------------------------------------------------------------------

class TestSessionStore:
    def test_messages_isolated_per_session(self):
        store = SessionStore()
        store.set_messages("A", [{"role": "user", "content": "a"}])
        store.set_messages("B", [{"role": "user", "content": "b"}])
        assert store.get_messages("A")[0]["content"] == "a"
        assert store.get_messages("B")[0]["content"] == "b"

    def test_summary_isolated_per_session(self):
        store = SessionStore()
        store.set_summary("A", "摘要A")
        store.set_summary("B", "摘要B")
        assert store.get_summary("A") == "摘要A"
        assert store.get_summary("B") == "摘要B"

    def test_clear(self):
        store = SessionStore()
        store.set_messages("A", [{"role": "user", "content": "a"}])
        store.clear("A")
        assert store.get_messages("A") == []

    def test_persist_roundtrip(self, tmp_path):
        store = SessionStore(persist_dir=tmp_path)
        store.set_messages("A", [{"role": "user", "content": "hello"}])
        store.set_summary("A", "摘要")
        fresh = SessionStore(persist_dir=tmp_path)
        assert fresh.get_messages("A")[0]["content"] == "hello"
        assert fresh.get_summary("A") == "摘要"


# ------------------------------------------------------------------
# 确认代理
# ------------------------------------------------------------------

class TestConfirmBroker:
    @staticmethod
    def _wait_pending(broker, channel, chat_id, timeout=2.0):
        """等到待应答请求注册上（避免竞态）"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if broker.has_pending(channel, chat_id):
                return True
            time.sleep(0.005)
        return False

    def test_ask_and_deliver(self):
        broker = ConfirmBroker(default_timeout=5)
        got = {}

        def asker():
            self._wait_pending(broker, "lark", "c1")
            got["ok"] = broker.deliver("lark", "c1", "y")

        t = threading.Thread(target=asker)
        t.start()
        answer = broker.ask("lark", "c1", "需要确认？")
        t.join()
        assert answer == "y"
        assert got["ok"] is True

    def test_timeout_returns_empty(self):
        broker = ConfirmBroker(default_timeout=1)
        assert broker.ask("lark", "c1", "问题") == ""

    def test_deliver_without_pending_returns_false(self):
        broker = ConfirmBroker()
        assert broker.deliver("lark", "c1", "y") is False

    def test_has_pending(self):
        broker = ConfirmBroker(default_timeout=5)
        seen = {}

        def asker():
            seen["pending"] = self._wait_pending(broker, "lark", "c1")
            broker.deliver("lark", "c1", "n")

        t = threading.Thread(target=asker)
        t.start()
        broker.ask("lark", "c1", "q")
        t.join()
        assert seen["pending"] is True


class TestBotConfirmStrategy:
    def test_answer_y_allows(self):
        s = BotConfirmStrategy(lambda q, t: "y")
        d = s.check("sec_write", "/a")
        assert d.allowed is True
        assert d.scope == "once"

    def test_answer_n_denies(self):
        s = BotConfirmStrategy(lambda q, t: "n")
        assert s.check("sec_write", "/a").allowed is False

    def test_empty_answer_denies(self):
        """超时按拒绝处理（fail-closed）"""
        s = BotConfirmStrategy(lambda q, t: "")
        assert s.check("sec_shell", "rm -rf /").allowed is False

    def test_exception_denies(self):
        def boom(q, t):
            raise RuntimeError("down")

        s = BotConfirmStrategy(boom)
        assert s.check("sec_shell", "x").allowed is False

    def test_question_contains_target(self):
        q = format_confirm_question("sec_write", "/etc/passwd", "write_file")
        assert "/etc/passwd" in q
        assert "write_file" in q


# ------------------------------------------------------------------
# 状态池
# ------------------------------------------------------------------

class TestStatePool:
    def test_reuses_states(self):
        pool = StatePool({}, size=2, factory=lambda cfg: {"id": id(cfg)})
        with pool.acquire():
            pass
        with pool.acquire():
            pass
        assert pool.stats()["created"] == 1

    def test_creates_up_to_size(self):
        pool = StatePool({}, size=3, factory=lambda cfg: {})
        with pool.acquire() as a:
            with pool.acquire() as b:
                assert a is not b
        assert pool.stats()["created"] <= 3

    def test_headless_flag_injected(self):
        pool = StatePool({}, size=1, factory=lambda cfg: cfg)
        with pool.acquire() as cfg:
            assert cfg["headless"] is True

    def test_closed_pool_raises(self):
        pool = StatePool({}, size=1, factory=lambda cfg: {})
        pool.close()
        with pytest.raises(RuntimeError):
            with pool.acquire():
                pass


# ------------------------------------------------------------------
# 调度器
# ------------------------------------------------------------------

class _FakeState:
    """最小化的 AppState 替身"""

    def __init__(self):
        self.lang = "zh"
        self.cfg = {}
        self.messages = []
        self.context_summary = ""
        self.last_reply = ""
        self.security = _FakeSecurity()
        self.executor = None

    def get_messages(self):
        return list(self.messages)

    def set_messages(self, msgs):
        self.messages = list(msgs)

    def set_strategy(self, strategy):
        self.security.strategy = strategy


class _FakeSecurity:
    def __init__(self):
        self.strategy = None

    def set_strategy(self, strategy):
        self.strategy = strategy


class TestBotDispatcher:
    def _dispatcher(self, **kw):
        pool = StatePool({}, size=2, factory=lambda cfg: _FakeState())
        return BotDispatcher(state_pool=pool, **kw)

    @staticmethod
    def _fake_ai(state, text):
        """假的 AI 回路 —— 绝不能真的调 LLM"""
        state.last_reply = "AI 的回答"
        state.set_messages(state.get_messages() + [
            {"role": "user", "content": text},
            {"role": "assistant", "content": "AI 的回答"},
        ])
        state.context_summary = "摘要"

    def test_ignored_message_returns_not_handled(self):
        d = self._dispatcher(router=Router(bot_names=["凡人"]))
        m = BotMessage(channel="lark", chat_id="oc", user_id="u1", text="闲聊")
        result = d.handle(m)
        assert result.handled is False
        assert result.action == "ignore"

    def test_duplicate_message_ignored(self, monkeypatch):
        monkeypatch.setattr("fr_cli.core.chat.handle_ai_chat", self._fake_ai)
        d = self._dispatcher(router=Router(require_mention_in_group=False))
        m = BotMessage(channel="lark", chat_id="u1", user_id="u1",
                        text="hi", message_id="m1")
        first = d.handle(m)
        second = d.handle(m)
        assert first.handled is True
        assert first.reply == "AI 的回答"
        assert second.handled is False   # 重复被去重

    def test_chat_path_saves_session(self, monkeypatch):
        monkeypatch.setattr("fr_cli.core.chat.handle_ai_chat", self._fake_ai)
        store = SessionStore()
        d = self._dispatcher(session_store=store,
                             router=Router(require_mention_in_group=False))
        m = BotMessage(channel="lark", chat_id="u1", user_id="u1", text="你好")
        result = d.handle(m)

        assert result.reply == "AI 的回答"
        assert store.get_messages("lark:u1:")
        assert store.get_summary("lark:u1:") == "摘要"

    def test_sessions_do_not_leak_into_each_other(self, monkeypatch):
        """A 用户的上下文绝不能进 B 用户的会话"""
        monkeypatch.setattr("fr_cli.core.chat.handle_ai_chat", self._fake_ai)
        store = SessionStore()
        d = self._dispatcher(session_store=store,
                             router=Router(require_mention_in_group=False))
        d.handle(BotMessage(channel="lark", chat_id="A", user_id="A", text="问A"))
        d.handle(BotMessage(channel="lark", chat_id="B", user_id="B", text="问B"))

        a_msgs = store.get_messages("lark:A:")
        b_msgs = store.get_messages("lark:B:")
        assert any(m.get("content") == "问A" for m in a_msgs)
        assert not any(m.get("content") == "问A" for m in b_msgs)

    def test_deliver_answer_consumes_confirmation(self):
        broker = ConfirmBroker(default_timeout=5)
        d = self._dispatcher(confirm_broker=broker)
        m = BotMessage(channel="lark", chat_id="u1", user_id="u1", text="y")
        assert d.deliver_answer(m) is False   # 没有待应答的请求

    def test_stats_shape(self):
        d = self._dispatcher()
        st = d.stats()
        assert "pool" in st and "sessions" in st and "idempotency" in st
