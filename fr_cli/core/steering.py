"""
流式期间交互(steering)——在 AI 生成途中追加/修正指令

参考 kimi-cli 的 Ctrl-S steering：
- 用户在 AI 正在生成时，把当前输入框里的文字按 Ctrl-S 提交为**转向指令**；
- 转向指令**不**排成下一轮对话，而是在**当前这一轮**结束前注入消息历史，
  让模型在同一轮里带着新指令继续推理（相当于中途改需求，不用重开一轮）；
- 空闲时按 Ctrl-S 不做任何事（此时应该直接按 Enter 提交）。

与"对话队列"(repl/queue.py)的区别：
- 队列：排成**下一轮**独立对话，处理完当前轮才开始；
- steering：注入**当前轮**，与当前轮的上下文连续。

本模块只负责"暂存 + 取走"，不碰 UI、不碰 LLM，方便单测。
"""
from __future__ import annotations

import threading
from typing import List, Tuple

# 暂存上限：防止用户疯狂按 Ctrl-S 把上下文撑爆
MAX_STEER_MESSAGES = 20


def _is_lock(obj) -> bool:
    """鸭子类型判断是否为可用的锁对象（threading.Lock 在 3.8+ 是工厂函数不是类）"""
    return obj is not None and hasattr(obj, "acquire") and hasattr(obj, "release")


def _get_store(state) -> Tuple[list, threading.Lock]:
    """惰性初始化 steering 暂存区，返回 (消息列表, 锁)。

    挂在 state 上（``_steer_messages`` / ``_steer_lock``），
    不改动 bootstrap 的构造签名 —— 免得影响所有既有构造点。
    """
    messages = getattr(state, "_steer_messages", None)
    if not isinstance(messages, list):
        messages = []
        try:
            state._steer_messages = messages
        except Exception:
            pass

    lock = getattr(state, "_steer_lock", None)
    if not _is_lock(lock):
        lock = threading.Lock()
        try:
            state._steer_lock = lock
        except Exception:
            pass

    return messages, lock


def push_steer(state, text: str) -> int:
    """暂存一条转向指令，返回暂存后的总条数。

    空文本/纯空白直接忽略（返回当前条数）。超过 ``MAX_STEER_MESSAGES``
    时丢弃最旧的 —— 用户连按 Ctrl-S 时不至于把上下文撑爆。
    """
    text = (text or "").strip()
    if not text:
        return steer_count(state)

    messages, lock = _get_store(state)
    with lock:
        messages.append(text)
        if len(messages) > MAX_STEER_MESSAGES:
            del messages[:-MAX_STEER_MESSAGES]
        return len(messages)


def drain_steer(state) -> List[str]:
    """取走并清空所有暂存的转向指令；没有则返回空列表。"""
    messages, lock = _get_store(state)
    with lock:
        if not messages:
            return []
        out = list(messages)
        messages.clear()
        return out


def peek_steer(state) -> List[str]:
    """查看暂存的转向指令（不取走）。"""
    messages, lock = _get_store(state)
    with lock:
        return list(messages)


def steer_count(state) -> int:
    """当前暂存的转向指令条数。"""
    messages, lock = _get_store(state)
    with lock:
        return len(messages)


def clear_steer(state) -> None:
    """清空暂存的转向指令。"""
    messages, lock = _get_store(state)
    with lock:
        messages.clear()


def format_steer_notice(count: int) -> str:
    """把转向指令条数渲染成一行提示文案（供 UI 复用）。"""
    if count <= 0:
        return ""
    return f"↯ 已注入 {count} 条转向指令，将在本轮生效"
