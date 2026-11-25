"""
消息幂等 / 去重 —— 平台会重投 webhook

v2.8.7 新增。

IM 平台（飞书 / Telegram / 企微）在网络超时、客户端重试、事件重放等
场景下会**重复投递同一条消息**。若不去重，同一个问题会被处理 N 次：
- 重复调用 LLM（烧钱）
- 重复执行工具（可能有副作用 —— 写文件、发邮件）
- 重复回复用户

这里用 ``dedup_key``（``BotMessage.dedup_key``）+ TTL 做幂等。
进程内内存实现 —— bot 常驻进程的生命周期与平台重投窗口匹配；
若要跨进程重启也幂等，可把后端换成 Redis / SQLite。
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Dict, Optional

__all__ = ["IdempotencyGuard"]


class IdempotencyGuard:
    """基于 TTL 的去重守卫（线程安全）。

    Attributes:
        ttl:       去重窗口（秒）—— 超过则视为新消息
        max_size:  最多保留多少条记录（LRU 淘汰）
    """

    def __init__(self, ttl: int = 3600, max_size: int = 10000):
        self.ttl = max(1, int(ttl))
        self.max_size = max(1, int(max_size))
        self._seen: "OrderedDict[str, float]" = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def check_and_mark(self, key: str, now: Optional[float] = None) -> bool:
        """检查并标记。

        Returns:
            True  = **重复**消息（应当忽略）
            False = 新消息（应当处理）
        """
        if not key:
            return False
        ts = now if now is not None else time.time()
        with self._lock:
            self._expire(ts)
            if key in self._seen:
                self._hits += 1
                # 刷新 LRU 位置
                self._seen.move_to_end(key)
                return True
            self._seen[key] = ts
            self._misses += 1
            while len(self._seen) > self.max_size:
                self._seen.popitem(last=False)
            return False

    def seen(self, key: str, now: Optional[float] = None) -> bool:
        """只检查不标记。"""
        ts = now if now is not None else time.time()
        with self._lock:
            self._expire(ts)
            return key in self._seen

    def forget(self, key: str) -> None:
        """移除一条记录（处理失败需要重试时用）。"""
        with self._lock:
            self._seen.pop(key, None)

    def clear(self) -> None:
        """清空全部记录。"""
        with self._lock:
            self._seen.clear()
            self._hits = 0
            self._misses = 0

    def _expire(self, now: float) -> None:
        """清理过期记录（调用方需持有锁）。"""
        cutoff = now - self.ttl
        while self._seen:
            oldest_key = next(iter(self._seen))
            if self._seen[oldest_key] > cutoff:
                break
            self._seen.pop(oldest_key, None)

    def stats(self) -> Dict[str, int]:
        """统计信息（用于 /bot_status）。"""
        with self._lock:
            return {
                "tracked": len(self._seen),
                "duplicates": self._hits,
                "accepted": self._misses,
                "ttl": self.ttl,
            }
