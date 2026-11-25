"""
Bot 集成测试：真实 generic 通道 + 真实调度器 + 真实网关

验证「入站 webhook → 验签 → 解析 → 调度 → 出站回复」的完整闭环，
中间用假的状态池与假的 AI 回路（不调真实 LLM）。
"""
import json
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from fr_cli.bot.channels import load_channels
from fr_cli.bot.core.channel import get_channel
from fr_cli.bot.core.dispatcher import BotDispatcher
from fr_cli.bot.core.router import Router
from fr_cli.bot.core.session_store import SessionStore
from fr_cli.bot.runtime.gateway import BotGateway


class _SinkHandler(BaseHTTPRequestHandler):
    """模拟平台的出站接收端"""

    received = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            _SinkHandler.received.append(json.loads(raw.decode("utf-8")))
        except Exception:
            _SinkHandler.received.append({"raw": raw.decode("utf-8", "replace")})
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")


@pytest.fixture
def sink():
    _SinkHandler.received = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SinkHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/hook"
    finally:
        server.shutdown()
        server.server_close()


class _FakeState:
    def __init__(self):
        self.lang = "zh"
        self.cfg = {}
        self.messages = []
        self.context_summary = ""
        self.last_reply = ""
        self.security = _FakeSecurity()

    def get_messages(self):
        return list(self.messages)

    def set_messages(self, msgs):
        self.messages = list(msgs)


class _FakeSecurity:
    def set_strategy(self, strategy):
        self.security_strategy = strategy


class _FakePool:
    def __init__(self):
        self.state = _FakeState()

    def acquire(self):
        from contextlib import contextmanager

        @contextmanager
        def _cm():
            yield self.state

        return _cm()

    def stats(self):
        return {}


def _post(url, payload, headers=None):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


class TestGenericChannelEndToEnd:
    def test_full_loop(self, sink, monkeypatch):
        load_channels()

        def fake_ai(state, text):
            state.last_reply = f"AI 收到: {text}"
            state.set_messages(state.get_messages() + [
                {"role": "user", "content": text},
                {"role": "assistant", "content": state.last_reply},
            ])

        monkeypatch.setattr("fr_cli.core.chat.handle_ai_chat", fake_ai)

        channel = get_channel("generic", {
            "token": "secret-token",
            "reply_url": sink,
            "field_map": {
                "text": "text",
                "chat_id": "chat_id",
                "user_id": "user_id",
                "message_id": "message_id",
            },
        })
        assert channel is not None

        dispatcher = BotDispatcher(
            state_pool=_FakePool(),
            session_store=SessionStore(),
            router=Router(require_mention_in_group=False),
        )
        gw = BotGateway(dispatcher=dispatcher, channels={"generic": channel},
                        host="127.0.0.1", port=0)
        result = gw.start()
        assert result["ok"], result
        try:
            status, data = _post(
                f"{result['url']}/bot/generic",
                {"text": "你好", "chat_id": "c1", "user_id": "u1", "message_id": "m1"},
                {"X-Bot-Token": "secret-token"},
            )
            assert status == 200, data
            assert data["ok"] is True

            # 出站是异步的，等一下
            deadline = time.time() + 5
            while time.time() < deadline and not _SinkHandler.received:
                time.sleep(0.05)

            assert _SinkHandler.received, "出站回复没送到"
            assert _SinkHandler.received[0]["text"] == "AI 收到: 你好"
            assert _SinkHandler.received[0]["chat_id"] == "c1"
        finally:
            gw.stop()

    def test_wrong_token_rejected(self, sink):
        load_channels()
        channel = get_channel("generic", {"token": "secret-token", "reply_url": sink})
        dispatcher = BotDispatcher(state_pool=_FakePool(), session_store=SessionStore(),
                                   router=Router(require_mention_in_group=False))
        gw = BotGateway(dispatcher=dispatcher, channels={"generic": channel},
                        host="127.0.0.1", port=0)
        result = gw.start()
        try:
            status, data = _post(
                f"{result['url']}/bot/generic",
                {"text": "x", "chat_id": "c1"},
                {"X-Bot-Token": "wrong"},
            )
            assert status == 401
        finally:
            gw.stop()
