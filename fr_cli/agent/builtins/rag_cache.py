"""
RAGManager 查询缓存 mixin —— 内存 TTL 缓存 + 跨会话持久化

从 fr_cli.agent.builtins.rag 拆出(原文件 509 行)。
缓存结构 {key: (ts, value)},TTL 由 self._cache_ttl 决定(默认 600s),
上限 self._cache_max(默认 128 条,写满清最旧 1/4)。
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict


class RAGCacheMixin:
    """查询缓存(内存 + 可选磁盘持久化)"""

    def _query_cache_key(self, question: str, top_k: int, lang: str) -> str:
        """生成查询缓存 key"""
        # 超长问题或非标准 lang 不缓存
        if len(question) > 2000 or lang not in ("zh", "en"):
            return f"_nocache_{id(self)}_{time.time()}"
        import hashlib
        h = hashlib.sha256(f"{question}|{top_k}|{lang}".encode("utf-8")).hexdigest()
        return h[:32]

    def _write_cache(self, key: str, value: Any) -> None:
        """写缓存(满了清掉最旧的)"""
        if key.startswith("_nocache_"):
            return
        if len(self._query_cache) >= self._cache_max:
            # 清掉最旧的 1/4
            to_remove = max(1, self._cache_max // 4)
            by_ts = sorted(self._query_cache.items(), key=lambda x: x[1][0])
            for k, _ in by_ts[:to_remove]:
                self._query_cache.pop(k, None)
        self._query_cache[key] = (time.time(), value)

    def clear_cache(self) -> int:
        """清空缓存,返回清理条数"""
        n = len(self._query_cache)
        self._query_cache.clear()
        # v2.8+:清理持久化文件
        if self._persist_cache and self._persist_path:
            try:
                if os.path.exists(self._persist_path):
                    os.remove(self._persist_path)
            except Exception:
                pass
        return n

    def cache_stats(self) -> Dict[str, Any]:
        """缓存统计"""
        now = time.time()
        valid = sum(1 for ts, _ in self._query_cache.values() if now - ts < self._cache_ttl)
        expired = len(self._query_cache) - valid
        return {
            "total": len(self._query_cache),
            "valid": valid,
            "expired": expired,
            "ttl_seconds": self._cache_ttl,
            "max_entries": self._cache_max,
            "persist_enabled": self._persist_cache,
            "persist_path": self._persist_path,
        }

    def _load_persistent_cache(self) -> None:
        """从磁盘加载持久化缓存"""
        if not self._persist_path or not os.path.exists(self._persist_path):
            return
        try:
            import json
            with open(self._persist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # data 是 {key: [ts, value]}
            now = time.time()
            loaded = 0
            for key, (ts, value) in data.items():
                if now - ts < self._cache_ttl:  # 只加载未过期
                    self._query_cache[key] = (ts, value)
                    loaded += 1
                    if loaded >= self._cache_max:
                        break
        except Exception:
            pass

    def _flush_persistent_cache(self) -> None:
        """把缓存刷到磁盘"""
        if not self._persist_cache or not self._persist_path:
            return
        try:
            import json
            import tempfile
            now = time.time()
            valid_items = {
                k: (ts, v)
                for k, (ts, v) in self._query_cache.items()
                if now - ts < self._cache_ttl
            }
            # 限制大小
            if len(valid_items) > self._cache_max:
                by_ts = sorted(valid_items.items(), key=lambda x: x[1][0])
                valid_items = dict(by_ts[-self._cache_max:])

            fd, tmp = tempfile.mkstemp(
                dir=os.path.dirname(self._persist_path),
                prefix=".rag_cache_", suffix=".tmp"
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(valid_items, f, ensure_ascii=False)
            os.replace(tmp, self._persist_path)
        except Exception:
            pass

    def enable_persistent_cache(self, enable: bool = True) -> bool:
        """开关持久化缓存"""
        self._persist_cache = enable
        if enable and not self._persist_path:
            try:
                from fr_cli.conf.paths import ROOT as FR_CLI_DIR
                self._persist_path = str(FR_CLI_DIR / "rag_cache.json")
                self._load_persistent_cache()
            except Exception:
                return False
        return True
