"""
LLM 响应缓存 —— 相同问题 5 分钟内问第二次直接返回缓存

节省 token + 加速 + 减少 API 配额消耗

设计：
- 缓存键 = (model, system_prompt_hash, user_message)
- TTL 5 分钟
- 大小限制 100 条（LRU 淘汰）
- 可通过 /cache clear 清空
"""
import hashlib
import time
import threading
from collections import OrderedDict
from typing import Optional, Tuple, Dict, Any


_TTL_SEC = 300  # 5 分钟
_MAX_ENTRIES = 100


class ResponseCache:
    """LRU 响应缓存（线程安全）"""

    def __init__(self, ttl: int = _TTL_SEC, max_entries: int = _MAX_ENTRIES):
        self._ttl = ttl
        self._max = max_entries
        self._store: "OrderedDict[str, Tuple[float, str, dict]]" = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _make_key(model: str, system: str, user: str) -> str:
        h = hashlib.sha256()
        h.update(model.encode("utf-8"))
        h.update(b"\x00")
        # system 经常很长，只 hash 前 500 chars
        h.update(system[:500].encode("utf-8"))
        h.update(b"\x00")
        h.update(user.encode("utf-8"))
        return h.hexdigest()[:32]

    def get(self, model: str, system: str, user: str) -> Optional[Tuple[str, dict]]:
        """获取缓存；返回 (full_text, usage) 或 None"""
        key = self._make_key(model, system, user)
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            ts, text, usage = entry
            if time.time() - ts > self._ttl:
                del self._store[key]
                self._misses += 1
                return None
            # LRU：移到最后
            self._store.move_to_end(key)
            self._hits += 1
            return text, usage

    def put(self, model: str, system: str, user: str, text: str, usage: dict):
        """写入缓存"""
        key = self._make_key(model, system, user)
        with self._lock:
            self._store[key] = (time.time(), text, usage)
            self._store.move_to_end(key)
            # LRU 淘汰
            while len(self._store) > self._max:
                self._store.popitem(last=False)

    def clear(self):
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            return {
                "entries": len(self._store),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": f"{(self._hits / total * 100):.1f}%" if total > 0 else "0%",
            }


# 全局单例
_cache = ResponseCache()


def cache_get(model: str, system: str, user: str):
    return _cache.get(model, system, user)


def cache_put(model: str, system: str, user: str, text: str, usage: dict):
    _cache.put(model, system, user, text, usage)


def cache_clear():
    _cache.clear()


def cache_stats() -> Dict[str, Any]:
    return _cache.stats()
