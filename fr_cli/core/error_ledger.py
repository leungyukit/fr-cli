"""
统一错误账本

收集 Hermes 任务失败、动态构建自测失败、审核拒绝等错误事件，
供 /status 与 HTTP /info 集中展示。

v3.0+:可订阅 v3 EventBus,自动从 tool.failed / llm.failed / agent.failed 事件中提取并记录。
"""
import time
import uuid
import threading
from typing import Dict, List, Optional, Any

from fr_cli.core.store import JsonStore
from fr_cli.conf.paths import ERROR_LEDGER_FILE


# 默认监听的事件类型(category 映射)
_DEFAULT_LISTENERS = {
    "tool.failed": "tool",
    "llm.failed": "llm",
    "agent.failed": "agent",
    "error.occurred": "error",
}


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


# ---------------- v3 EventBus 集成 ----------------

def install_bus_listeners(ledger: Optional[ErrorLedger] = None,
                          bus=None) -> int:
    """订阅 v3 EventBus,自动从失败事件记录错误

    Args:
        ledger: ErrorLedger 实例,默认全局单例
        bus: v3 EventBus 实例,默认全局单例

    Returns:
        安装的 listener 数量

    Note:
        - 每个事件类型安装一个 listener,把 failed 类事件转为 ErrorLedger 条目
        - 自动从 event.data 提取:source / category / description / error
        - 不影响现有 record() 显式调用(可叠加)
    """
    if ledger is None:
        ledger = get_error_ledger()
    try:
        from fr_cli.v3.core.events import EventBus
    except Exception:
        return 0
    if bus is None:
        bus = EventBus.instance()

    count = 0

    def _make_handler(category: str):
        def handler(event):
            try:
                data = event.data or {}
                # source_id 优先用具体名称(name/model/path),其次用 source(组件)
                source_id = (data.get("name")
                             or data.get("model")
                             or data.get("path")
                             or event.source
                             or data.get("_source")
                             or "unknown")
                description = (data.get("description")
                               or data.get("message")
                               or f"{category} failed")
                error = (data.get("error")
                         or data.get("reason")
                         or data.get("detail")
                         or "")
                metadata = {
                    k: v for k, v in data.items()
                    if k not in ("error", "reason", "description", "message",
                                 "name", "model", "path")
                }
                ledger.record(
                    category=category,
                    source_id=str(source_id),
                    description=str(description),
                    error=str(error),
                    metadata=metadata,
                )
            except Exception:
                pass
        return handler

    for event_type, category in _DEFAULT_LISTENERS.items():
        try:
            bus.on(event_type, _make_handler(category), priority=0)
            count += 1
        except Exception:
            pass

    return count
