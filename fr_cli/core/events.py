"""
v2 事件分发表面 (dispatch_event / subscribe_event)

设计目标:
  - 给 v2 提供一个简洁的事件 API,内部走 v3 EventBus
  - 老的 HookManager(PreToolUse / PostToolUse / UserPromptSubmit)也通过 v3 bus 分发
  - 任何 v3 listener 自动能看到 v2 发布的事件,实现"全应用解耦"

v2 事件名规范:subject.action
  - session.created / session.message_added / session.saved
  - llm.requested / llm.responded / llm.chunk
  - tool.invoked / tool.succeeded / tool.failed / tool.blocked
  - command.executed
  - agent.invoked / agent.responded
  - app.starting / app.started / app.stopping / app.stopped
  - config.changed

v2 Hook 事件(沿用 Claude Code 风格,大写驼峰):
  - PreToolUse / PostToolUse / UserPromptSubmit / SessionStart / SessionEnd / Notification

这些 Hook 事件和 v3 通用事件是两套并行体系:
  - Hook 事件由 HookManager 解析,可以阻止/修改(走 subprocess,语义强)
  - 通用事件是只读的"发生了什么"广播(走 EventBus,语义弱)
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Callable, Dict, Optional

log = logging.getLogger(__name__)

# ---------------- 事件名常量 ----------------

class V2Events:
    """v2 通用事件名(dotted.subject.action 风格)"""
    # App
    APP_STARTING = "app.starting"
    APP_STARTED = "app.started"
    APP_STOPPING = "app.stopping"
    APP_STOPPED = "app.stopped"

    # Session
    SESSION_CREATED = "session.created"
    SESSION_MESSAGE_ADDED = "session.message_added"
    SESSION_SAVED = "session.saved"
    SESSION_LOADED = "session.loaded"

    # LLM
    LLM_REQUESTED = "llm.requested"
    LLM_RESPONDED = "llm.responded"
    LLM_CHUNK = "llm.chunk"
    LLM_FAILED = "llm.failed"

    # Tool
    TOOL_INVOKED = "tool.invoked"
    TOOL_SUCCEEDED = "tool.succeeded"
    TOOL_FAILED = "tool.failed"
    TOOL_BLOCKED = "tool.blocked"

    # Command(/xxx 命令)
    COMMAND_EXECUTED = "command.executed"

    # Agent 分身
    AGENT_INVOKED = "agent.invoked"
    AGENT_RESPONDED = "agent.responded"
    AGENT_FAILED = "agent.failed"

    # Config
    CONFIG_CHANGED = "config.changed"

    # Usage / 计量
    USAGE_RECORDED = "usage.recorded"

    # Error / 错误集中报告
    ERROR_OCCURRED = "error.occurred"


class V2HookEvents:
    """v2 Hook 事件名(Claude Code 风格)"""
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    SESSION_START = "SessionStart"
    SESSION_END = "SessionEnd"
    NOTIFICATION = "Notification"


# 向后兼容:导出旧的 HOOK_EVENTS 常量
HOOK_EVENTS = [
    V2HookEvents.PRE_TOOL_USE,
    V2HookEvents.POST_TOOL_USE,
    V2HookEvents.USER_PROMPT_SUBMIT,
    V2HookEvents.SESSION_START,
    V2HookEvents.SESSION_END,
    V2HookEvents.NOTIFICATION,
]


# ---------------- 事件分发表面 ----------------

# 全局开关(可通过环境变量或 set_dispatch_enabled 关闭,用于极简模式)
_dispatch_enabled = True
_dispatch_lock = threading.Lock()


def is_dispatch_enabled() -> bool:
    """事件分发是否启用"""
    return _dispatch_enabled


def set_dispatch_enabled(enabled: bool):
    """启用/禁用事件分发(用于极简模式或测试)"""
    global _dispatch_enabled
    with _dispatch_lock:
        _dispatch_enabled = enabled


def dispatch_event(event_type: str,
                   data: Optional[Dict[str, Any]] = None,
                   source: Optional[str] = None,
                   sync: bool = True) -> Any:
    """发布一个 v2 事件(底层走 v3 EventBus)

    Args:
        event_type: 事件名(V2Events.* 或 V2HookEvents.*)
        data: 事件数据(dict)
        source: 来源标识(如 "command_executor")
        sync: True 同步执行 handlers,False 后台线程

    Returns:
        v3 EventBus 返回的 Event 对象

    Note:
        - 异常被 EventBus 内部捕获,不会冒泡
        - 关闭后(环境变量 FR_CLI_NO_EVENTS=1)直接 no-op
    """
    if not _dispatch_enabled:
        return None
    if os.environ.get("FR_CLI_NO_EVENTS") == "1":
        return None
    try:
        from fr_cli.v3.core.events import EventBus
        bus = EventBus.instance()
        return bus.emit(event_type, data=data, source=source, sync=sync)
    except Exception as e:
        # 事件总线异常永远不能影响主流程
        log.debug(f"dispatch_event {event_type} failed: {e}")
        return None


def subscribe_event(event_type: str,
                    handler: Callable,
                    priority: int = 0) -> Callable:
    """订阅一个 v2 事件(底层走 v3 EventBus)

    Args:
        event_type: 事件名
        handler: 处理函数,签名 handler(event)
        priority: 越大越先执行

    Returns:
        handler(可作 unsubscribe 用)
    """
    from fr_cli.v3.core.events import EventBus
    return EventBus.instance().on(event_type, handler, priority=priority)


def unsubscribe_event(event_type: str, handler: Callable) -> bool:
    """取消订阅"""
    try:
        from fr_cli.v3.core.events import EventBus
        return EventBus.instance().off(event_type, handler)
    except Exception:
        return False


def get_event_bus():
    """获取 v3 全局 EventBus 实例(v2 代码可以用这个监听所有事件)"""
    from fr_cli.v3.core.events import EventBus
    return EventBus.instance()


def reset_for_testing():
    """重置事件分发状态(仅测试用)"""
    global _dispatch_enabled
    with _dispatch_lock:
        _dispatch_enabled = True
