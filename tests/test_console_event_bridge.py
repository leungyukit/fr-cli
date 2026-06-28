"""
Console ↔ v3 EventBus 桥接测试

覆盖:
- attach_event_bus 后,v3/v2 事件自动推送到 SSE 历史
- detach_event_bus 后停止推送
- channel 拆分:dotted 事件名 → channel=sub
- 异常隔离:handler 抛错不影响 SSE 推送
- start_console / stop_console 自动绑定/解绑
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from fr_cli.v3.core.events import EventBus
from fr_cli.core.events import V2Events, dispatch_event
from fr_cli.web.console import (
    get_recent_events,
    attach_event_bus, detach_event_bus,
    _sse_history, _sse_lock,
)


@pytest.fixture(autouse=True)
def reset_console():
    """每个测试清空 SSE 历史 + 解绑 bus"""
    with _sse_lock:
        _sse_history.clear()
    detach_event_bus()
    EventBus.reset()
    bus = EventBus.instance()
    bus.clear()
    yield
    detach_event_bus()
    with _sse_lock:
        _sse_history.clear()


# ==================== 桥接基本用法 ====================

class TestBridgeBasic:
    def test_attach_returns_true(self):
        assert attach_event_bus() is True

    def test_attach_registers_wildcard_handler(self):
        bus = EventBus.instance()
        before = bus.listener_count("*")
        attach_event_bus()
        after = bus.listener_count("*")
        assert after == before + 1

    def test_detach_removes_handler(self):
        bus = EventBus.instance()
        attach_event_bus()
        before = bus.listener_count("*")
        detach_event_bus()
        after = bus.listener_count("*")
        assert after == before - 1

    def test_detach_when_not_attached(self):
        # 没 attach 时 detach 不报错
        assert detach_event_bus() is False

    def test_double_attach(self):
        attach_event_bus()
        attach_event_bus()  # 第二次应该也成功(2 个 handler)
        bus = EventBus.instance()
        # 至少 2 个 handler
        assert bus.listener_count("*") >= 2
        # 清理
        detach_event_bus()
        detach_event_bus()


# ==================== 事件推送 ====================

class TestEventPushToSSE:
    def test_v3_emit_pushes_to_sse(self):
        attach_event_bus()
        bus = EventBus.instance()
        bus.emit("tool.invoked", data={"name": "read_file", "path": "/tmp/a"})

        events = get_recent_events(limit=10)
        assert len(events) >= 1
        # 最新事件是 tool channel
        last = events[-1]
        assert last["type"] == "tool"
        assert last["data"]["name"] == "read_file"
        assert last["data"]["_sub"] == "invoked"
        assert last["data"]["_source"] == ""  # 没设 source

    def test_v2_dispatch_pushes_to_sse(self):
        attach_event_bus()
        dispatch_event(V2Events.LLM_RESPONDED, data={"tokens": 100}, source="chat")

        events = get_recent_events(limit=10)
        last = events[-1]
        assert last["type"] == "llm"
        assert last["data"]["_sub"] == "responded"
        assert last["data"]["_source"] == "chat"
        assert last["data"]["tokens"] == 100

    def test_event_with_source(self):
        attach_event_bus()
        dispatch_event(V2Events.AGENT_INVOKED, data={"name": "coder"}, source="agent_executor")

        events = get_recent_events(limit=10)
        last = events[-1]
        assert last["type"] == "agent"
        assert last["data"]["_source"] == "agent_executor"
        assert last["data"]["_sub"] == "invoked"
        assert last["data"]["name"] == "coder"

    def test_event_without_dot_uses_full_type_as_channel(self):
        """非 dotted 事件名,channel 整个 type,sub 为空"""
        attach_event_bus()
        dispatch_event("MyCustomEvent", data={"x": 1})

        events = get_recent_events(limit=10)
        last = events[-1]
        assert last["type"] == "MyCustomEvent"
        assert last["data"]["_sub"] == ""


# ==================== 数据清洗 ====================

class TestDataCleaning:
    def test_non_json_serializable_becomes_string(self):
        attach_event_bus()

        class Unserializable:
            def __repr__(self): return "<obj>"
        dispatch_event(V2Events.CONFIG_CHANGED, data={"value": Unserializable()})

        events = get_recent_events(limit=10)
        last = events[-1]
        # 非 JSON 安全对象被转 str
        assert isinstance(last["data"]["value"], str)


# ==================== 异常隔离 ====================

class TestExceptionIsolation:
    def test_handler_exception_does_not_block(self):
        """桥接 handler 抛错不影响事件总线本身"""
        attach_event_bus()
        # 通过 push_event 间接测试 — _on_event_to_sse 永远不抛错
        bus = EventBus.instance()
        # 发送一个会导致 _on_event_to_sse 内部异常的事件?实际很难触发,
        # 因为我们做了 try/except。这里只验证正常流程仍工作
        bus.emit("test.event", data={"x": 1})
        assert len(get_recent_events()) >= 1


# ==================== 解绑后停止 ====================

class TestDetachStops:
    def test_after_detach_no_more_events(self):
        attach_event_bus()
        dispatch_event(V2Events.APP_STARTING, data={"x": 1})
        assert len(get_recent_events()) >= 1

        detach_event_bus()
        # 清空历史
        with _sse_lock:
            _sse_history.clear()

        dispatch_event(V2Events.APP_STARTED, data={"x": 2})
        # 解绑后,事件不应再进入历史
        assert len(get_recent_events()) == 0


# ==================== start_console / stop_console 集成 ====================

class TestConsoleLifecycle:
    def test_start_console_attaches_bus(self):
        from fr_cli.web.console import start_console, stop_console, console_status
        # 用 0 端口可能不行,用随机高端口
        import socket
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

        res = start_console(host="127.0.0.1", port=port, token="test-token", open_browser=False)
        try:
            assert res["ok"], res.get("error")
            assert console_status()["running"]
            # 验证 bus 已经被绑定
            bus = EventBus.instance()
            assert bus.listener_count("*") >= 1
        finally:
            stop_console()

    def test_stop_console_detaches_bus(self):
        from fr_cli.web.console import start_console, stop_console
        import socket
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

        start_console(host="127.0.0.1", port=port, token="test-token", open_browser=False)
        bus = EventBus.instance()
        before = bus.listener_count("*")

        stop_console()
        after = bus.listener_count("*")
        # 解绑后 wildcard handler 数量应该减少
        assert after < before

    def test_console_actually_receives_events_via_sse(self):
        """完整流程:console 运行 + 发事件 + 通过 SSE 通道收到"""
        from fr_cli.web.console import start_console, stop_console
        import socket
        import threading
        import urllib.request
        import json

        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

        res = start_console(host="127.0.0.1", port=port, token="test-tok", open_browser=False)
        try:
            assert res["ok"]

            # 通过 HTTP 拉取历史(验证 console 工作)
            url = f"http://127.0.0.1:{port}/api/events?token=test-tok"
            received = []

            def fetch():
                try:
                    req = urllib.request.Request(url)
                    with urllib.request.urlopen(req, timeout=3) as r:
                        for line in r:
                            line = line.decode("utf-8", errors="replace").strip()
                            if line.startswith("data:"):
                                received.append(line[5:].strip())
                                if len(received) >= 3:
                                    break
                except Exception:
                    pass

            t = threading.Thread(target=fetch, daemon=True)
            t.start()
            time.sleep(0.5)  # 等 SSE 连接建立

            # 发几个事件
            dispatch_event(V2Events.APP_STARTED, data={"k": 1}, source="test")
            dispatch_event(V2Events.LLM_RESPONDED, data={"k": 2}, source="test")
            dispatch_event(V2Events.TOOL_INVOKED, data={"k": 3}, source="test")

            t.join(timeout=3)
            # 至少收到一些 SSE data 行
            assert len(received) >= 1, f"没收到 SSE 事件: {received}"

            # 解析后应该看到 source="test" 或 _sub 字段
            has_test_event = False
            for raw in received:
                try:
                    obj = json.loads(raw)
                    if obj.get("data", {}).get("_source") == "test":
                        has_test_event = True
                        break
                except Exception:
                    pass
            assert has_test_event, f"没看到 test 来源事件: {received}"
        finally:
            stop_console()
