"""
Bot HTTP 网关端到端测试

用假通道验证：入站 → 验签 → 解析 → 调度 → 回复 的完整链路。
"""
import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from fr_cli.bot.core.channel import Channel
from fr_cli.bot.core.message import BotMessage
from fr_cli.bot.runtime.gateway import BotGateway


class _FakeChannel(Channel):
    """记录收到的消息与发出的回复"""

    name = "_fake_gateway_channel"

    def __init__(self, config=None):
        super().__init__(config or {})
        self.received = []
        self.sent = []
        self._lock = threading.Lock()

    def verify(self, headers, payload):
        return headers.get("x-fake-token") == "ok"

    def parse(self, headers, payload):
        if not isinstance(payload, dict):
            return None
        chat_id = payload.get("chat_id")
        if not chat_id:
            return None
        return BotMessage(
            channel=self.name,
            chat_id=str(chat_id),
            user_id=str(payload.get("user_id") or ""),
            text=str(payload.get("text") or ""),
            message_id=str(payload.get("message_id") or ""),
        )

    def send(self, reply):
        with self._lock:
            self.sent.append(reply)
        return reply


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
        pass


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
        return {"size": 1, "created": 1, "in_use": 0, "idle": 1}


class _FakeDispatcher:
    def __init__(self):
        self.calls = []

    def handle(self, message):
        self.calls.append(message)
        from fr_cli.bot.core.dispatcher import BotResult
        return BotResult(reply=f"回声: {message.text}", handled=True, action="chat")

    def deliver_answer(self, message):
        return False

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


def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


@pytest.fixture
def gateway():
    channel = _FakeChannel()
    dispatcher = _FakeDispatcher()
    gw = BotGateway(dispatcher=dispatcher, channels={channel.name: channel},
                    host="127.0.0.1", port=0)
    result = gw.start()
    assert result["ok"], result
    # port=0 → 实际端口由系统分配
    gw.port = gw._server.server_address[1]
    try:
        yield gw, channel, dispatcher, result
    finally:
        gw.stop()


class TestBotGateway:
    def test_start_and_health(self, gateway):
        gw, _, _, result = gateway
        status, data = _get(f"{result['url']}/bot/health")
        assert status == 200
        assert data["ok"] is True

    def test_inbound_message_is_processed_and_answered(self, gateway):
        gw, channel, dispatcher, result = gateway
        status, data = _post(
            f"{result['url']}/bot/{channel.name}",
            {"chat_id": "c1", "user_id": "u1", "text": "你好", "message_id": "m1"},
            {"X-Fake-Token": "ok"},
        )
        assert status == 200
        assert data["ok"] is True

        # 后台线程处理是异步的，等一下
        deadline = time.time() + 5
        while time.time() < deadline and not channel.sent:
            time.sleep(0.05)

        assert dispatcher.calls, "调度器没收到消息"
        assert dispatcher.calls[0].text == "你好"
        assert channel.sent, "回复没发出去"
        assert channel.sent[0].text == "回声: 你好"
        assert channel.sent[0].chat_id == "c1"

    def test_verify_failure_returns_401(self, gateway):
        gw, channel, dispatcher, result = gateway
        status, data = _post(
            f"{result['url']}/bot/{channel.name}",
            {"chat_id": "c1", "text": "x"},
            {"X-Fake-Token": "wrong"},
        )
        assert status == 401
        assert data["ok"] is False

    def test_unknown_channel_returns_404(self, gateway):
        gw, _, _, result = gateway
        status, data = _post(f"{result['url']}/bot/nope", {"chat_id": "c1"})
        assert status == 404

    def test_status_requires_token(self, gateway):
        gw, _, _, result = gateway
        status, _ = _get(f"{result['url']}/bot/status")
        assert status == 401
        status, data = _get(f"{result['url']}/bot/status?token={result['token']}")
        assert status == 200
        assert data["ok"] is True

    def test_send_endpoint(self, gateway):
        gw, channel, _, result = gateway
        status, data = _post(
            f"{result['url']}/bot/send",
            {"channel": channel.name, "chat_id": "c9", "text": "主动推送"},
            {"Authorization": f"Bearer {result['token']}"},
        )
        assert status == 200
        assert data["ok"] is True
        assert channel.sent[-1].text == "主动推送"

    def test_stop_is_idempotent(self, gateway):
        gw, _, _, result = gateway
        assert gw.stop()["ok"] is True
        assert gw.stop()["ok"] is False


class TestBotEngineWiring:
    def test_engine_builds_with_no_channels(self, tmp_path, monkeypatch):
        """没配置任何通道时也要能装配（不能崩）"""
        monkeypatch.setattr("fr_cli.conf.paths.BOT_CONFIG_FILE",
                            str(tmp_path / "bot.json"), raising=False)
        from fr_cli.bot.runtime.engine import BotEngine
        engine = BotEngine({}, {"channels": {}})
        dispatcher, gateway = engine.build()
        assert dispatcher is not None
        assert gateway is not None
        assert gateway.channels == {}

    def test_config_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr("fr_cli.conf.paths.BOT_CONFIG_FILE",
                            str(tmp_path / "bot.json"), raising=False)
        from fr_cli.bot.runtime import engine as engine_mod
        cfg = engine_mod.load_bot_config()
        cfg["bot_names"] = ["凡人"]
        assert engine_mod.save_bot_config(cfg) is True
        again = engine_mod.load_bot_config()
        assert again["bot_names"] == ["凡人"]
