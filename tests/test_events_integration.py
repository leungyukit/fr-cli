"""
集成测试:v2 关键事件流(bootstrap → command_executor → agent)

模拟一个完整会话:
1. bootstrap 触发 app.starting / app.started
2. tool invocations 触发 tool.invoked / tool.succeeded / tool.failed
3. agent invocations 触发 agent.invoked / agent.responded
4. LLM calls 触发 llm.requested / llm.responded

并验证:
- v3 监听者能看到 v2 全部事件(双向互通)
- 不影响主流程返回值
- 异常 handler 不阻断
"""
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from fr_cli.core.events import (
    V2Events, dispatch_event, subscribe_event, get_event_bus,
)
from fr_cli.v3.core.events import EventBus


@pytest.fixture(autouse=True)
def reset_bus():
    EventBus.reset()
    bus = EventBus.instance()
    bus.clear()
    yield
    bus.clear()


# ==================== 端到端事件流 ====================

class TestEndToEndEventFlow:
    def test_all_v2_events_flow_through_v3_bus(self):
        """模拟一个完整会话,验证全部 v2 事件都流过 v3 bus"""
        bus = get_event_bus()
        events_log = []

        # v3 端 wildcard 监听(等价于全局审计日志)
        bus.on("*", lambda e: events_log.append({
            "type": e.type,
            "source": e.source,
            "data": e.data,
        }))

        # ===== app lifecycle =====
        dispatch_event(V2Events.APP_STARTING, data={"show_banner": True}, source="bootstrap")
        dispatch_event(V2Events.APP_STARTED, data={"model": "glm-4-flash"}, source="bootstrap")

        # ===== session =====
        dispatch_event(V2Events.SESSION_CREATED, data={"sid": "s1"}, source="chat")
        dispatch_event(V2Events.SESSION_MESSAGE_ADDED, data={"role": "user"}, source="chat")

        # ===== llm =====
        dispatch_event(V2Events.LLM_REQUESTED, data={"model": "glm-4-flash"}, source="chat")
        dispatch_event(V2Events.LLM_RESPONDED, data={"usage": {"total_tokens": 100}}, source="chat")

        # ===== tool =====
        dispatch_event(V2Events.TOOL_INVOKED, data={"name": "read_file", "args": {"path": "/tmp/a"}}, source="command_executor")
        dispatch_event(V2Events.TOOL_SUCCEEDED, data={"name": "read_file", "result": "content"}, source="command_executor")

        # ===== command =====
        dispatch_event(V2Events.COMMAND_EXECUTED, data={"cmd": "/ls"}, source="router")

        # ===== agent =====
        dispatch_event(V2Events.AGENT_INVOKED, data={"name": "coder"}, source="agent_executor")
        dispatch_event(V2Events.AGENT_RESPONDED, data={"name": "coder", "ok": True}, source="agent_executor")

        # ===== 验证 =====
        types = [e["type"] for e in events_log]
        assert V2Events.APP_STARTING in types
        assert V2Events.APP_STARTED in types
        assert V2Events.SESSION_CREATED in types
        assert V2Events.LLM_REQUESTED in types
        assert V2Events.LLM_RESPONDED in types
        assert V2Events.TOOL_INVOKED in types
        assert V2Events.TOOL_SUCCEEDED in types
        assert V2Events.COMMAND_EXECUTED in types
        assert V2Events.AGENT_INVOKED in types
        assert V2Events.AGENT_RESPONDED in types

    def test_observers_can_decorate_without_changing_main_flow(self):
        """观测者装饰主流程,不影响返回值"""
        # 模拟一个 fake tool 调用
        main_flow_log = []

        def my_main_flow():
            dispatch_event(V2Events.TOOL_INVOKED, data={"name": "fake"}, source="main")
            main_flow_log.append("before")
            return "main_result"
            main_flow_log.append("after")  # noqa

        # 监听者 1:统计调用次数
        counter = {"n": 0}
        subscribe_event(V2Events.TOOL_INVOKED, lambda e: counter.__setitem__("n", counter["n"] + 1))

        # 监听者 2:抛错(异常隔离)
        def bad_handler(e):
            raise RuntimeError("ignored")
        subscribe_event(V2Events.TOOL_INVOKED, bad_handler)

        result = my_main_flow()
        assert result == "main_result"
        assert counter["n"] == 1  # 计数正确
        assert main_flow_log == ["before"]  # 主流程完整跑完,异常不影响

    def test_v3_plugin_can_listen_to_v2_events(self):
        """v3 plugin 风格的 listener 能听到 v2 事件"""
        from fr_cli.v3.core.plugin import Plugin  # noqa: F401

        received = []

        class V2ListenerPlugin(Plugin):
            name = "v2_listener"
            version = "1.0.0"
            description = "监听 v2 事件"

            def setup(self):
                pass

        # 手动订阅 v2 事件(plugin 只是占位,实际订阅用 bus.on)
        _ = V2ListenerPlugin()  # 实例化以触发 Plugin 基类检查
        bus = get_event_bus()
        bus.on(V2Events.LLM_RESPONDED, lambda e: received.append(e.data))

        dispatch_event(V2Events.LLM_RESPONDED, data={"tokens": 100})

        assert received == [{"tokens": 100}]


# ==================== executor 真实路径 ====================

class TestExecutorEmitsEvents:
    def test_command_executor_emits_events(self):
        """直接调用 invoke_tool 时,事件会被发出"""
        from fr_cli.command.executor import CommandExecutor

        received = []
        subscribe_event(V2Events.TOOL_INVOKED, lambda e: received.append({"type": "invoked", "name": e.data.get("name")}))
        subscribe_event(V2Events.TOOL_SUCCEEDED, lambda e: received.append({"type": "succeeded", "name": e.data.get("name")}))

        # 构造最小 state
        state = MagicMock()
        state.vfs = None
        state.mail_c = None
        state.web_c = None
        state.disk_c = None
        state.plugins = {}
        state.lang = "zh"
        state.security = MagicMock()
        state.cfg = {}
        state.client = None
        state.model_name = "test"
        state.mcp = None

        executor = CommandExecutor(state)

        # 调用一个不存在的工具 → 应发出 TOOL_INVOKED + TOOL_FAILED
        try:
            executor.invoke_tool("non_existent_tool_xxx", {})
        except Exception:
            pass

        # 至少有 invoked 事件
        types = [r["type"] for r in received]
        assert "invoked" in types
        assert any(r["name"] == "non_existent_tool_xxx" for r in received)
