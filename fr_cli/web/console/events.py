"""
Web Console SSE 事件桥接

功能:
- push_event:把事件推到所有连接的 SSE 客户端
- 历史缓存(_sse_history):供新客户端拉取
- v3 EventBus 桥接:wildcard 监听全部 v3/v2 事件,自动推到 SSE
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, List

# v2.8+:SSE 事件队列(多客户端)
_sse_clients: List[threading.Event] = []
_sse_history: List[Dict[str, Any]] = []
_sse_history_max = 50
_sse_lock = threading.Lock()

# v3.0+:console 与 v3 EventBus 的桥接 handler 引用
_console_event_handler = None


def push_event(event_type: str, data: Dict[str, Any]):
    """推送一个 SSE 事件给所有连接的客户端

    Args:
        event_type: 事件类型(status / task / log / tool / llm / agent / custom)
        data: 事件数据(dict)
    """
    global _sse_history
    event = {
        "type": event_type,
        "timestamp": time.time(),
        "data": data,
    }
    with _sse_lock:
        _sse_history.append(event)
        if len(_sse_history) > _sse_history_max:
            _sse_history = _sse_history[-_sse_history_max:]
        clients = list(_sse_clients)
    for ev in clients:
        try:
            ev.set()
        except Exception:
            pass


def _on_event_to_sse(event):
    """v3 EventBus → SSE 桥接

    把所有 v3/v2 事件自动推到 console 的 SSE 流上。
    'tool.invoked' → channel='tool', sub='invoked'
    """
    try:
        etype = event.type
        if "." in etype:
            channel, sub = etype.split(".", 1)
        else:
            channel, sub = etype, ""
        safe_data = {}
        for k, v in (event.data or {}).items():
            try:
                json.dumps(v)
                safe_data[k] = v
            except (TypeError, ValueError):
                safe_data[k] = str(v)
        safe_data["_source"] = event.source or ""
        safe_data["_sub"] = sub
        push_event(channel, safe_data)
    except Exception:
        # bridge 永远不抛错
        pass


def attach_event_bus(bus=None) -> bool:
    """把 v3 EventBus 接到 console SSE(wildcard 监听全部事件)

    Args:
        bus: v3 EventBus,默认全局 EventBus.instance()

    Returns:
        True 成功, False 失败
    """
    global _console_event_handler
    try:
        from fr_cli.v3.core.events import EventBus
        if bus is None:
            bus = EventBus.instance()
        handler = bus.on("*", _on_event_to_sse, priority=-100)
        _console_event_handler = handler
        return True
    except Exception:
        return False


def detach_event_bus(bus=None) -> bool:
    """解除 console 与 v3 EventBus 的桥接"""
    global _console_event_handler
    try:
        from fr_cli.v3.core.events import EventBus
        if bus is None:
            bus = EventBus.instance()
        if _console_event_handler is not None:
            bus.off("*", _console_event_handler)
            _console_event_handler = None
            return True
    except Exception:
        pass
    return False


def get_recent_events(limit: int = 50) -> List[Dict[str, Any]]:
    """获取最近事件(给新客户端拉取历史)"""
    with _sse_lock:
        return list(_sse_history[-limit:])


def add_sse_client(event_signal: threading.Event):
    """注册一个新的 SSE 客户端(等待 push_event 唤醒)"""
    with _sse_lock:
        _sse_clients.append(event_signal)


def remove_sse_client(event_signal: threading.Event):
    """注销 SSE 客户端"""
    with _sse_lock:
        if event_signal in _sse_clients:
            _sse_clients.remove(event_signal)


def reset_sse_state():
    """重置 SSE 状态(测试用)"""
    global _console_event_handler
    with _sse_lock:
        _sse_history.clear()
        _sse_clients.clear()
        _console_event_handler = None
