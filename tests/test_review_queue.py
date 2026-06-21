"""
Hermes 后台产物审核队列测试
"""
import time
from pathlib import Path

import pytest

from fr_cli.core.store import JsonStore
from fr_cli.agent.review_queue import ReviewItem, PersistentReviewQueue


@pytest.fixture
def queue(tmp_path):
    store = JsonStore(tmp_path / "review_queue.json", default={"items": []})
    return PersistentReviewQueue(store)


class TestReviewItem:
    def test_roundtrip(self):
        item = ReviewItem(
            id="rev-123",
            artifact_type="plugin",
            code="def run(): pass",
            suggested_name="demo",
            task_id="task-abc",
        )
        d = item.to_dict()
        restored = ReviewItem.from_dict(d)
        assert restored.id == item.id
        assert restored.artifact_type == item.artifact_type
        assert restored.code == item.code
        assert restored.status == "pending"


class TestPersistentReviewQueue:
    def test_add_and_list(self, queue):
        item = queue.add("plugin", "def run(): pass", task_id="t1")
        assert item.id.startswith("rev-")
        assert item.status == "pending"
        assert queue.list(status="pending")[0].id == item.id

    def test_approve_reject(self, queue):
        item = queue.add("agent", "def run(context, **kwargs): pass")
        assert queue.approve(item.id, final_name="my_agent") is not None
        loaded = queue.get(item.id)
        assert loaded.status == "approved"
        assert loaded.suggested_name == "my_agent"

        assert queue.reject(item.id) is not None
        assert queue.get(item.id).status == "rejected"

    def test_counts(self, queue):
        a = queue.add("plugin", "code1")
        b = queue.add("plugin", "code2")
        queue.approve(a.id)
        queue.reject(b.id)
        counts = queue.counts()
        assert counts["total"] == 2
        assert counts["approved"] == 1
        assert counts["rejected"] == 1
        assert counts["pending"] == 0

    def test_get_missing(self, queue):
        assert queue.get("not-exist") is None
        assert queue.approve("not-exist") is None
