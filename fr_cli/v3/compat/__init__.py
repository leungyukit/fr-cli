"""
v3 compat —— v2.x 到 v3.0 兼容层

提供 v2 风格的 API,但内部走 v3 基础设施。
"""
from fr_cli.v3.core.events import EventBus, Events as _Events, emit as _emit


def publish_event(event_type: str, data: dict = None, source: str = None):
    """v2 风格事件发布(代理到 v3 EventBus)"""
    _emit(event_type, data=data, source=source)


def subscribe_event(event_type: str, handler):
    """v2 风格事件订阅"""
    return EventBus.instance().on(event_type, handler)


def publish_tool_event(stage: str, tool_name: str, **kwargs):
    """发布工具事件(stage = before / after / failed)"""
    event_map = {
        "before": _Events.TOOL_INVOKED,
        "after": _Events.TOOL_SUCCEEDED,
        "failed": _Events.TOOL_FAILED,
    }
    event_type = event_map.get(stage, _Events.TOOL_INVOKED)
    _emit(event_type, data={"name": tool_name, **kwargs}, source="v2-compat")
