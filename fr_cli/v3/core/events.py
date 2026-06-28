"""
v3 EventBus —— 事件驱动核心

v2.x 直接函数调用,无法插入横切关注点(日志/监控/审计/UI 推送)。
v3 EventBus 通过发布订阅模式,把所有跨切关注点解耦。

事件生命周期:
1. 组件 emit(event_type, data) 发布事件
2. 所有 on(event_type) 注册的 handler 同步执行
3. emit 可以 return aggregated result(可选)
4. handlers 抛异常会被捕获并 log,不影响主流程

事件命名:
- 主体.动作(如 "tool.invoked", "llm.responded")
- 或纯事件名("started", "stopping")
"""
from __future__ import annotations

import logging
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Set

log = logging.getLogger(__name__)

# 类型
EventHandler = Callable[["Event"], Any]
EventType = str


class Event:
    """事件对象

    Attributes:
        type: 事件类型(如 "tool.invoked")
        data: 事件数据(dict)
        source: 事件来源(可选,通常是组件名)
        timestamp: 时间戳(自动)
        propagated: 是否停止传播(供 handler 设置)
    """
    __slots__ = ("type", "data", "source", "timestamp", "_propagated")

    def __init__(self, type: EventType, data: Optional[Dict[str, Any]] = None,
                 source: Optional[str] = None):
        self.type = type
        self.data = data or {}
        self.source = source
        import time
        self.timestamp = time.time()
        self._propagated = False

    def stop_propagation(self):
        """阻止后续 handler 执行"""
        self._propagated = True

    def __repr__(self):
        return f"Event(type={self.type!r}, source={self.source!r})"


class EventBus:
    """事件总线(单例 + 线程安全)"""

    _instance: Optional["EventBus"] = None
    _lock = threading.Lock()

    def __init__(self, max_workers: int = 4):
        # type -> list of handlers
        self._handlers: Dict[EventType, List[EventHandler]] = defaultdict(list)
        # wildcards("*")
        self._wildcards: List[EventHandler] = []
        self._executor = ThreadPoolExecutor(max_workers=max_workers,
                                            thread_name_prefix="fr-cli-events")
        self._global_lock = threading.RLock()
        self._stats: Dict[str, int] = defaultdict(int)

    @classmethod
    def instance(cls) -> "EventBus":
        """全局单例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls):
        """重置单例(测试用)"""
        with cls._lock:
            if cls._instance is not None:
                cls._instance._executor.shutdown(wait=False, cancel_futures=True)
            cls._instance = None

    # ---------------- 订阅 ----------------

    def on(self, event_type: EventType,
           handler: EventHandler,
           priority: int = 0) -> Callable:
        """订阅事件

        Args:
            event_type: 事件类型,"*" 匹配所有事件
            handler: 回调函数,接收 Event 对象
            priority: 数字越大越先执行(默认 0)

        Returns:
            handler(支持链式 / 用作 unsubscribe)
        """
        with self._global_lock:
            if event_type == "*":
                self._wildcards.append((priority, handler))
                self._wildcards.sort(key=lambda x: -x[0])
            else:
                self._handlers[event_type].append((priority, handler))
                self._handlers[event_type].sort(key=lambda x: -x[0])
        log.debug(f"subscribed: {event_type} -> {handler.__name__ if hasattr(handler, '__name__') else handler}")
        return handler

    def off(self, event_type: EventType, handler: EventHandler) -> bool:
        """取消订阅"""
        with self._global_lock:
            if event_type == "*":
                before = len(self._wildcards)
                self._wildcards = [(p, h) for p, h in self._wildcards if h != handler]
                return len(self._wildcards) < before
            else:
                handlers = self._handlers[event_type]
                before = len(handlers)
                self._handlers[event_type] = [(p, h) for p, h in handlers if h != handler]
                return len(self._handlers[event_type]) < before

    def once(self, event_type: EventType, handler: EventHandler) -> Callable:
        """订阅一次后自动取消"""
        def wrapper(event: Event):
            try:
                handler(event)
            finally:
                self.off(event_type, wrapper)
        return self.on(event_type, wrapper)

    # ---------------- 发布 ----------------

    def emit(self, event_type: EventType,
             data: Optional[Dict[str, Any]] = None,
             source: Optional[str] = None,
             sync: bool = True) -> Event:
        """发布事件

        Args:
            event_type: 事件类型
            data: 事件数据
            source: 事件来源
            sync: True 同步执行所有 handler,False 后台线程

        Returns:
            事件对象(handler 可修改 _propagated)
        """
        event = Event(event_type, data=data, source=source)

        with self._global_lock:
            self._stats[event_type] += 1
            # 同类型 handlers(按优先级)
            handlers = list(self._handlers.get(event_type, []))
            wildcards = list(self._wildcards)

        all_handlers = [h for _, h in handlers] + [h for _, h in wildcards]

        if sync:
            self._run_handlers(event, all_handlers)
        else:
            self._executor.submit(self._run_handlers, event, all_handlers)

        return event

    def emit_async(self, event_type: EventType,
                   data: Optional[Dict[str, Any]] = None,
                   source: Optional[str] = None):
        """异步发布(后台线程)"""
        return self.emit(event_type, data=data, source=source, sync=False)

    def _run_handlers(self, event: Event, handlers: List[EventHandler]):
        """运行所有 handlers"""
        for handler in handlers:
            if event._propagated:
                break
            try:
                handler(event)
            except Exception as e:
                log.error(f"handler {handler} failed for event {event.type}: {e}",
                          exc_info=True)

    # ---------------- 工具 ----------------

    def listener_count(self, event_type: Optional[EventType] = None) -> int:
        """订阅者数量"""
        with self._global_lock:
            if event_type is None:
                return sum(len(h) for h in self._handlers.values()) + len(self._wildcards)
            return len(self._handlers.get(event_type, [])) + len(self._wildcards)

    def event_types(self) -> Set[EventType]:
        """已注册的事件类型"""
        with self._global_lock:
            return set(self._handlers.keys())

    def stats(self) -> Dict[str, int]:
        """事件触发统计"""
        with self._global_lock:
            return dict(self._stats)

    def reset_stats(self):
        """重置统计"""
        with self._global_lock:
            self._stats.clear()

    def clear(self):
        """清空所有订阅(测试用)"""
        with self._global_lock:
            self._handlers.clear()
            self._wildcards.clear()

    def shutdown(self):
        """关闭 executor(应用退出时)"""
        self._executor.shutdown(wait=True, cancel_futures=True)


# ---------------- 标准事件名(常量) ----------------

class Events:
    """标准事件名常量(避免拼写错误)"""
    # App lifecycle
    APP_STARTING = "app.starting"
    APP_STARTED = "app.started"
    APP_STOPPING = "app.stopping"
    APP_STOPPED = "app.stopped"

    # LLM
    LLM_REQUESTED = "llm.requested"
    LLM_RESPONDED = "llm.responded"
    LLM_FAILED = "llm.failed"
    LLM_CHUNK = "llm.chunk"  # 流式输出

    # Tool
    TOOL_INVOKED = "tool.invoked"
    TOOL_SUCCEEDED = "tool.succeeded"
    TOOL_FAILED = "tool.failed"
    TOOL_BLOCKED = "tool.blocked"  # 被 hook / 权限阻止

    # Session / Memory
    SESSION_CREATED = "session.created"
    SESSION_MESSAGE_ADDED = "session.message_added"
    SESSION_SAVED = "session.saved"

    # Plan
    PLAN_CREATED = "plan.created"
    PLAN_APPROVED = "plan.approved"
    PLAN_EXECUTED = "plan.executed"

    # RAG
    RAG_INDEXED = "rag.indexed"
    RAG_QUERIED = "rag.queried"

    # Hooks(钩子链)
    HOOK_PRE_TOOL = "hook.pre_tool"
    HOOK_POST_TOOL = "hook.post_tool"

    # MCP
    MCP_SERVER_REGISTERED = "mcp.server_registered"
    MCP_TOOL_CALLED = "mcp.tool_called"

    # Agent
    AGENT_INVOKED = "agent.invoked"
    AGENT_RESPONDED = "agent.responded"


# 便捷函数(全局单例)
bus = EventBus.instance


def emit(event_type: EventType, data: Optional[Dict[str, Any]] = None,
         source: Optional[str] = None, sync: bool = True) -> Event:
    """便捷:发布事件到全局总线"""
    return EventBus.instance().emit(event_type, data=data, source=source, sync=sync)


def on(event_type: EventType, handler: EventHandler,
      priority: int = 0) -> EventHandler:
    """便捷:订阅全局总线"""
    return EventBus.instance().on(event_type, handler, priority=priority)
