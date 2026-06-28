"""
v2 dispatch_event / subscribe_event 表面测试

覆盖:
- V2Events / V2HookEvents 常量
- dispatch_event / subscribe_event / unsubscribe_event 基本用法
- 与 v3 EventBus 互通:v2 listener 能听到 v3 emit,v3 listener 能听到 v2 emit
- HookManager 触发后 v3 bus 收到通知
- 异常隔离:handler 抛错不影响主流程
- 禁用开关:set_dispatch_enabled(False) 后全部 no-op
- HOOK_EVENTS 向后兼容
"""
import os
import sys
import time
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from fr_cli.core.events import (
    V2Events,
    V2HookEvents,
    HOOK_EVENTS,
    dispatch_event,
    subscribe_event,
    unsubscribe_event,
    get_event_bus,
    set_dispatch_enabled,
    reset_for_testing,
)
from fr_cli.v3.core.events import EventBus, Events as V3Events


@pytest.fixture(autouse=True)
def reset_bus():
    """每个测试清空 v3 bus + 重置 dispatch 开关"""
    EventBus.reset()
    EventBus.instance()  # 触发重建
    EventBus.instance().clear()
    reset_for_testing()
    yield
    EventBus.instance().clear()
    reset_for_testing()


# ==================== 常量 ====================

class TestConstants:
    def test_v2_events_basic(self):
        assert V2Events.APP_STARTING == "app.starting"
        assert V2Events.APP_STARTED == "app.started"
        assert V2Events.SESSION_CREATED == "session.created"
        assert V2Events.LLM_REQUESTED == "llm.requested"
        assert V2Events.TOOL_INVOKED == "tool.invoked"
        assert V2Events.COMMAND_EXECUTED == "command.executed"
        assert V2Events.AGENT_INVOKED == "agent.invoked"
        assert V2Events.CONFIG_CHANGED == "config.changed"

    def test_v2_hook_events(self):
        assert V2HookEvents.PRE_TOOL_USE == "PreToolUse"
        assert V2HookEvents.POST_TOOL_USE == "PostToolUse"
        assert V2HookEvents.USER_PROMPT_SUBMIT == "UserPromptSubmit"
        assert V2HookEvents.SESSION_START == "SessionStart"

    def test_hook_events_constant_backward_compat(self):
        # 老的 HOOK_EVENTS 列表仍然存在并包含全部 6 个事件
        assert "PreToolUse" in HOOK_EVENTS
        assert "PostToolUse" in HOOK_EVENTS
        assert "UserPromptSubmit" in HOOK_EVENTS
        assert "SessionStart" in HOOK_EVENTS
        assert "SessionEnd" in HOOK_EVENTS
        assert "Notification" in HOOK_EVENTS
        assert len(HOOK_EVENTS) == 6


# ==================== dispatch_event 基本用法 ====================

class TestDispatchEvent:
    def test_dispatch_returns_none_when_disabled(self):
        set_dispatch_enabled(False)
        assert dispatch_event(V2Events.APP_STARTING) is None
        assert dispatch_event(V2Events.APP_STARTING, data={"x": 1}) is None

    def test_dispatch_emits_to_v3_bus(self):
        received = []
        subscribe_event(V2Events.TOOL_INVOKED, lambda e: received.append(e.data))
        dispatch_event(V2Events.TOOL_INVOKED, data={"name": "write_file"})
        assert received == [{"name": "write_file"}]

    def test_dispatch_with_source(self):
        received = []
        subscribe_event(V2Events.APP_STARTED, lambda e: received.append(e.source))
        dispatch_event(V2Events.APP_STARTED, source="bootstrap")
        assert received == ["bootstrap"]

    def test_dispatch_no_handlers(self):
        # 没订阅时,不抛错,返回 Event 对象
        event = dispatch_event("some.unused.event", data={"x": 1})
        assert event is not None
        assert event.type == "some.unused.event"
        assert event.data == {"x": 1}


# ==================== subscribe_event / unsubscribe_event ====================

class TestSubscribeUnsubscribe:
    def test_subscribe_returns_handler(self):
        def handler(e): pass
        result = subscribe_event(V2Events.LLM_RESPONDED, handler)
        assert result is handler

    def test_unsubscribe_removes_handler(self):
        received = []
        def handler(e): received.append(e.data)

        subscribe_event(V2Events.LLM_REQUESTED, handler)
        dispatch_event(V2Events.LLM_REQUESTED, data={"x": 1})
        assert received == [{"x": 1}]

        # 取消订阅
        ok = unsubscribe_event(V2Events.LLM_REQUESTED, handler)
        assert ok is True
        dispatch_event(V2Events.LLM_REQUESTED, data={"x": 2})
        assert received == [{"x": 1}]  # 没增加

    def test_unsubscribe_not_subscribed(self):
        def handler(e): pass
        ok = unsubscribe_event(V2Events.LLM_REQUESTED, handler)
        assert ok is False

    def test_priority_ordering(self):
        # 数字大的先执行
        order = []
        subscribe_event(V2Events.TOOL_INVOKED, lambda e: order.append("low"), priority=0)
        subscribe_event(V2Events.TOOL_INVOKED, lambda e: order.append("high"), priority=10)
        dispatch_event(V2Events.TOOL_INVOKED)
        assert order == ["high", "low"]


# ==================== v2 ↔ v3 互通 ====================

class TestV2V3Interop:
    def test_v3_listener_hears_v2_emit(self):
        # 用 v3 API 订阅一个事件,用 v2 API 发射
        received = []
        bus = get_event_bus()
        bus.on(V2Events.SESSION_CREATED, lambda e: received.append(e.data))

        dispatch_event(V2Events.SESSION_CREATED, data={"sid": "abc"})
        assert received == [{"sid": "abc"}]

    def test_v2_listener_hears_v3_emit(self):
        # 用 v2 API 订阅一个 v3 标准事件,用 v3 API 发射
        received = []
        subscribe_event(V3Events.TOOL_INVOKED, lambda e: received.append(e.data))

        bus = get_event_bus()
        bus.emit(V3Events.TOOL_INVOKED, data={"name": "read_file"})

        assert received == [{"name": "read_file"}]

    def test_stats_increment(self):
        bus = get_event_bus()
        bus.reset_stats()
        dispatch_event(V2Events.TOOL_INVOKED, data={})
        dispatch_event(V2Events.TOOL_INVOKED, data={})
        dispatch_event(V2Events.TOOL_FAILED, data={})
        stats = bus.stats()
        assert stats.get(V2Events.TOOL_INVOKED) == 2
        assert stats.get(V2Events.TOOL_FAILED) == 1


# ==================== 异常隔离 ====================

class TestExceptionIsolation:
    def test_handler_exception_does_not_propagate(self):
        def bad_handler(e):
            raise RuntimeError("oops")

        received = []
        subscribe_event(V2Events.APP_STARTED, bad_handler)
        subscribe_event(V2Events.APP_STARTED, lambda e: received.append(e.type))

        # 不应抛错
        dispatch_event(V2Events.APP_STARTED)
        assert received == ["app.started"]  # 第二个 handler 仍然跑


# ==================== 异步 ====================

class TestAsyncDispatch:
    def test_sync_flag(self):
        received = []
        evt = threading.Event()
        def slow(e):
            time.sleep(0.05)
            received.append(e.data)
            evt.set()

        subscribe_event(V2Events.AGENT_INVOKED, slow)
        dispatch_event(V2Events.AGENT_INVOKED, data={"name": "x"}, sync=False)
        # 异步,可能未完成
        evt.wait(timeout=2)
        assert received == [{"name": "x"}]


# ==================== HookManager → v3 bus 联动 ====================

class TestHookManagerIntegration:
    def test_pre_tool_use_publishes_to_bus(self):
        """PreToolUse hook 触发后,v3 bus 收到通知"""
        from fr_cli.agent.hooks import (
            HookManager, reset_hook_manager,
        )
        reset_hook_manager()

        # 注册一个空 hook,匹配所有工具
        cfg = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "", "type": "command", "command": "echo pre",
                     "description": "echo"}
                ]
            }
        }
        mgr = HookManager(cfg=cfg)

        received = []
        subscribe_event(V2HookEvents.PRE_TOOL_USE, lambda e: received.append(e.data))

        result = mgr.run_pre_tool_use("write_file", {"path": "/tmp/a"})
        # hook 已跑完
        assert result.blocked is False
        # v3 bus 也收到通知
        assert len(received) == 1
        assert received[0]["tool_name"] == "write_file"
        assert received[0]["tool_args"] == {"path": "/tmp/a"}
        assert received[0]["blocked"] is False
        assert received[0]["matched_count"] >= 1

        reset_hook_manager()

    def test_post_tool_use_publishes_to_bus(self):
        from fr_cli.agent.hooks import HookManager, reset_hook_manager
        reset_hook_manager()

        cfg = {
            "hooks": {
                "PostToolUse": [
                    {"matcher": "", "type": "command", "command": "echo post",
                     "description": "echo"}
                ]
            }
        }
        mgr = HookManager(cfg=cfg)

        received = []
        subscribe_event(V2HookEvents.POST_TOOL_USE, lambda e: received.append(e.data))

        mgr.run_post_tool_use("write_file", {"path": "/tmp/a"}, "result")
        assert len(received) == 1
        assert received[0]["tool_name"] == "write_file"

        reset_hook_manager()

    def test_user_prompt_submit_publishes_to_bus(self):
        from fr_cli.agent.hooks import HookManager, reset_hook_manager
        reset_hook_manager()

        cfg = {
            "hooks": {
                "UserPromptSubmit": [
                    {"matcher": "", "type": "command", "command": "echo ups",
                     "description": "echo"}
                ]
            }
        }
        mgr = HookManager(cfg=cfg)

        received = []
        subscribe_event(V2HookEvents.USER_PROMPT_SUBMIT, lambda e: received.append(e.data))

        mgr.run_user_prompt_submit("hello world")
        assert len(received) == 1
        assert received[0]["user_input"] == "hello world"

        reset_hook_manager()


# ==================== 环境变量禁用 ====================

class TestEnvDisable:
    def test_env_disable(self, monkeypatch):
        monkeypatch.setenv("FR_CLI_NO_EVENTS", "1")
        received = []
        subscribe_event(V2Events.APP_STARTING, lambda e: received.append(1))
        dispatch_event(V2Events.APP_STARTING)
        assert received == []  # 环境变量禁用
