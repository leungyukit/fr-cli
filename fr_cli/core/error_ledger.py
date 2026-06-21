"""
统一错误账本

收集 Hermes 任务失败、动态构建自测失败、审核拒绝等错误事件，
供 /status 与 HTTP /info 集中展示。
"""
import time
import uuid
import threading
from typing import Dict, List, Optional, Any

from fr_cli.core.store import JsonStore
from fr_cli.conf.paths import ERROR_LEDGER_FILE


class ErrorLedger:
    """线程安全的 JSON 错误账本。"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, store_path: Optional[Any] = None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init(store_path)
        return cls._instance

    def _init(self, store_path: Optional[Any]):
        self._store = JsonStore(store_path or ERROR_LEDGER_FILE, default=list)
        self._records: List[Dict[str, Any]] = []
        self._record_lock = threading.RLock()
        self._load()

    def _load(self):
        data = self._store.read()
        self._records = data if isinstance(data, list) else []

    def _persist(self):
        with self._record_lock:
            # 最多保留 500 条
            self._records = self._records[-500:]
            self._store.write(self._records)

    def record(
        self,
        category: str,
        source_id: str,
        description: str,
        error: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """记录一条错误事件，返回事件 ID。"""
        event_id = f"err-{uuid.uuid4().hex[:8]}-{int(time.time())}"
        record = {
            "id": event_id,
            "category": category,
            "source_id": source_id,
            "description": str(description)[:200],
            "error": str(error)[:500],
            "metadata": metadata or {},
            "timestamp": time.time(),
        }
        with self._record_lock:
            self._records.append(record)
        self._persist()
        return event_id

    def list_errors(self, category: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """按类别过滤并返回最近的错误事件。"""
        with self._record_lock:
            records = list(self._records)
        if category:
            records = [r for r in records if r.get("category") == category]
        records.sort(key=lambda r: r.get("timestamp", 0), reverse=True)
        return records[:limit]

    def counts(self) -> Dict[str, int]:
        """返回每个类别的错误数量。"""
        counts: Dict[str, int] = {}
        with self._record_lock:
            for r in self._records:
                cat = r.get("category", "unknown")
                counts[cat] = counts.get(cat, 0) + 1
        return counts


def get_error_ledger(store_path: Optional[Any] = None) -> ErrorLedger:
    """获取全局错误账本实例。"""
    return ErrorLedger(store_path)
