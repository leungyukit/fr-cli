"""
Hermes 后台产物审核队列 —— 非交互式场景下暂存检测到的插件 / Agent 代码
"""

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from fr_cli.conf.paths import HERMES_REVIEW_QUEUE_FILE
from fr_cli.core.store import JsonStore
from fr_cli.core.error_ledger import get_error_ledger


@dataclass
class ReviewItem:
    id: str
    artifact_type: str  # plugin | agent
    code: str
    suggested_name: str = ""
    status: str = "pending"  # pending | approved | rejected
    task_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "ReviewItem":
        return cls(
            id=d.get("id", ""),
            artifact_type=d.get("artifact_type", ""),
            code=d.get("code", ""),
            suggested_name=d.get("suggested_name", ""),
            status=d.get("status", "pending"),
            task_id=d.get("task_id"),
            created_at=d.get("created_at", time.time()),
            metadata=d.get("metadata", {}) or {},
        )


class PersistentReviewQueue:
    """基于 JsonStore 的持久化审核队列，支持 REPL / HTTP 异步审批"""

    def __init__(self, store: Optional[JsonStore] = None):
        self.store = store or JsonStore(HERMES_REVIEW_QUEUE_FILE, default={"items": []})

    def _read_items(self) -> List[Dict]:
        try:
            return list(self.store.read().get("items", []))
        except Exception:
            return []

    def _write_items(self, items: List[Dict]):
        self.store.write({"items": items})

    def add(
        self,
        artifact_type: str,
        code: str,
        suggested_name: str = "",
        task_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> ReviewItem:
        item = ReviewItem(
            id=f"rev-{uuid.uuid4().hex[:8]}",
            artifact_type=artifact_type,
            code=code,
            suggested_name=suggested_name,
            status="pending",
            task_id=task_id,
            created_at=time.time(),
            metadata=metadata or {},
        )
        items = self._read_items()
        items.append(item.to_dict())
        self._write_items(items)
        return item

    def list(self, status: Optional[str] = None) -> List[ReviewItem]:
        items = [ReviewItem.from_dict(d) for d in self._read_items()]
        if status:
            items = [i for i in items if i.status == status]
        return sorted(items, key=lambda x: x.created_at, reverse=True)

    def get(self, item_id: str) -> Optional[ReviewItem]:
        for d in self._read_items():
            if d.get("id") == item_id:
                return ReviewItem.from_dict(d)
        return None

    def update(self, item: ReviewItem) -> bool:
        items = self._read_items()
        found = False
        for i, d in enumerate(items):
            if d.get("id") == item.id:
                items[i] = item.to_dict()
                found = True
                break
        if found:
            self._write_items(items)
        return found

    def approve(self, item_id: str, final_name: Optional[str] = None) -> Optional[ReviewItem]:
        item = self.get(item_id)
        if item is None:
            return None
        if final_name:
            item.suggested_name = final_name
        item.status = "approved"
        self.update(item)
        return item

    def reject(self, item_id: str) -> Optional[ReviewItem]:
        item = self.get(item_id)
        if item is None:
            return None
        item.status = "rejected"
        self.update(item)
        get_error_ledger().record(
            "review_rejected", item.id,
            f"{item.artifact_type} review rejected",
            f"suggested_name={item.suggested_name}, task_id={item.task_id}",
            metadata={"artifact_type": item.artifact_type, "suggested_name": item.suggested_name, "task_id": item.task_id}
        )
        return item

    def counts(self) -> Dict[str, int]:
        items = self.list()
        return {
            "total": len(items),
            "pending": sum(1 for i in items if i.status == "pending"),
            "approved": sum(1 for i in items if i.status == "approved"),
            "rejected": sum(1 for i in items if i.status == "rejected"),
        }
