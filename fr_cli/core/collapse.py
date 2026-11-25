"""
折叠内容登记表 —— 让"被折叠掉的内容"还能被找回来

背景
----
``fr_cli/core/chat/helpers.py::fold_result`` 会把超长的命令执行结果折叠成
「头 15 行 + … (省略 N 行) … + 尾 5 行」，但**被省略的内容直接丢了** ——
用户看到省略号，却没有任何办法把它要回来。

流式 Markdown 渲染器也有同样的问题：回答过长时刷屏，把输入区顶出屏幕。

本模块提供一个进程级的登记表：折叠发生时把原文存进来，REPL 里按 Ctrl+O
就能把最近一次折叠的内容原样打印出来。

设计
----
* **线程安全**：折叠发生在 LLM 流式后台线程，Ctrl+O 在主线程读 → 用锁。
* **只留最近几条**：默认 5 条，超出丢弃最旧的 —— 避免长会话把内存吃光。
* **不落盘**：这是运行时临时状态，进程退出即消失（与 steering 一致）。
"""

from __future__ import annotations

import threading
from typing import List, NamedTuple, Optional

#: 最多保留多少条折叠内容（超出丢弃最旧的）
MAX_ITEMS = 5


class CollapsedItem(NamedTuple):
    """一条被折叠的内容"""

    text: str      # 折叠掉的原文（可能很大）
    meta: str      # 人类可读的说明（如 "命令输出 120 行"）


_lock = threading.Lock()
_items: List[CollapsedItem] = []


def register(text: str, meta: str = "") -> int:
    """登记一条被折叠的内容。

    Args:
        text: 被折叠掉的原文
        meta: 说明文字（展开时显示）

    Returns:
        int: 当前保留的折叠条目数
    """
    if not text:
        return count()
    with _lock:
        _items.append(CollapsedItem(text=text, meta=meta))
        # 只保留最近 MAX_ITEMS 条
        while len(_items) > MAX_ITEMS:
            _items.pop(0)
        return len(_items)


def peek() -> Optional[CollapsedItem]:
    """看一眼最近一条折叠内容（不取走）"""
    with _lock:
        return _items[-1] if _items else None


def take() -> Optional[CollapsedItem]:
    """取走最近一条折叠内容（取走后从登记表移除）。

    Returns:
        CollapsedItem | None: 最近一条；没有则 None
    """
    with _lock:
        if not _items:
            return None
        return _items.pop()


def count() -> int:
    """当前保留的折叠条目数"""
    with _lock:
        return len(_items)


def clear() -> None:
    """清空登记表"""
    with _lock:
        _items.clear()


__all__ = [
    "MAX_ITEMS",
    "CollapsedItem",
    "register",
    "peek",
    "take",
    "count",
    "clear",
]
