"""
确认请求代理 —— 跨线程配对"发问"与"应答"

v2.8.7 新增。

bot 场景的确认流程天然跨线程：

    线程 A（处理用户提问）        线程 B（入站消息线程）
    ─────────────────────        ─────────────────────
    工具需要确认
      → 发确认问题到 IM
      → 阻塞等应答 ────────────→  用户在 IM 回复 "y"
                                   → 解析成 BotMessage
                                   → deliver(answer)
      ← 拿到 "y"，放行

本模块用 ``threading.Event`` 做配对，键为 ``(channel, chat_id, thread_id)``。

安全约束：
  - 超时**按拒绝处理**（fail-closed）
  - 没有等待中的请求时收到 "y" 之类的回复，直接忽略（避免误放行）
  - 每个请求独立，不会串台
"""
from __future__ import annotations

import threading
from typing import Dict, Optional, Tuple

__all__ = ["ConfirmBroker", "PendingRequest"]

#: 确认应答的默认超时（秒）
DEFAULT_TIMEOUT = 120


class PendingRequest:
    """一个待应答的确认请求。"""

    __slots__ = ("key", "question", "event", "answer", "created_at")

    def __init__(self, key: Tuple[str, str, str], question: str):
        import time
        self.key = key
        self.question = question
        self.event = threading.Event()
        self.answer: Optional[str] = None
        self.created_at = time.time()

    def resolve(self, answer: str) -> None:
        """写入答案并唤醒等待方（只生效一次）。"""
        if not self.event.is_set():
            self.answer = answer
            self.event.set()


class ConfirmBroker:
    """确认请求的配对中心（线程安全）。"""

    def __init__(self, default_timeout: int = DEFAULT_TIMEOUT):
        self.default_timeout = default_timeout
        self._pending: Dict[Tuple[str, str, str], PendingRequest] = {}
        self._lock = threading.Lock()
        self._asked = 0
        self._answered = 0
        self._timed_out = 0

    @staticmethod
    def _key(channel: str, chat_id: str, thread_id: str = "") -> Tuple[str, str, str]:
        return (channel or "", chat_id or "", thread_id or "")

    def ask(self, channel: str, chat_id: str, question: str,
            thread_id: str = "", timeout: Optional[int] = None) -> str:
        """发起一个确认请求并等待应答。

        Returns:
            用户的应答原文；超时或异常时返回空串（调用方应按拒绝处理）。
        """
        key = self._key(channel, chat_id, thread_id)
        wait_seconds = self.default_timeout if timeout is None else timeout
        req = PendingRequest(key, question)
        with self._lock:
            # 同一会话只允许一个待应答请求（后到的覆盖先到的）
            self._pending[key] = req
            self._asked += 1
        try:
            if req.event.wait(wait_seconds):
                with self._lock:
                    self._answered += 1
                return req.answer or ""
            with self._lock:
                self._timed_out += 1
            return ""
        finally:
            with self._lock:
                if self._pending.get(key) is req:
                    self._pending.pop(key, None)

    def deliver(self, channel: str, chat_id: str, answer: str,
                thread_id: str = "") -> bool:
        """投递一个应答（由入站消息处理线程调用）。

        Returns:
            True 表示命中了一个待应答请求；False 表示没有（直接忽略）。
        """
        key = self._key(channel, chat_id, thread_id)
        with self._lock:
            req = self._pending.get(key)
        if req is None:
            return False
        req.resolve(answer)
        return True

    def has_pending(self, channel: str, chat_id: str, thread_id: str = "") -> bool:
        """该会话是否有待应答的确认请求。"""
        key = self._key(channel, chat_id, thread_id)
        with self._lock:
            return key in self._pending

    def cancel(self, channel: str, chat_id: str, thread_id: str = "") -> bool:
        """取消一个待应答请求（按拒绝处理）。"""
        key = self._key(channel, chat_id, thread_id)
        with self._lock:
            req = self._pending.pop(key, None)
        if req is None:
            return False
        req.resolve("")
        return True

    def stats(self) -> Dict[str, int]:
        """统计信息（用于 /bot_status）。"""
        with self._lock:
            return {
                "pending": len(self._pending),
                "asked": self._asked,
                "answered": self._answered,
                "timed_out": self._timed_out,
            }
