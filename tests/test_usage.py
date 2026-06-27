"""
UsageTracker 用量统计测试
覆盖 record / summary / reset / cost 估算等。
"""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fr_cli.core.usage import UsageTracker


@pytest.fixture
def tracker(tmp_path):
    """每个测试一个独立的用量跟踪器"""
    return UsageTracker(path=str(tmp_path / "usage.json"))


class TestRecord:

    def test_record_basic(self, tracker):
        tracker.record("zhipu", "glm-4-flash", 100, 50)
        assert len(tracker._records) == 1
        record = tracker._records[0]
        assert record["provider"] == "zhipu"
        assert record["model"] == "glm-4-flash"
        assert record["prompt_tokens"] == 100
        assert record["completion_tokens"] == 50
        assert record["total_tokens"] == 150

    def test_record_total_auto_calculated(self, tracker):
        tracker.record("zhipu", "glm-4-flash", 200, 100)
        assert tracker._records[0]["total_tokens"] == 300

    def test_record_explicit_total(self, tracker):
        tracker.record("zhipu", "glm-4-flash", 100, 50, total_tokens=999)
        assert tracker._records[0]["total_tokens"] == 999

    def test_record_with_cost(self, tracker):
        tracker.record("zhipu", "glm-4-flash", 100, 50, cost=0.01)
        assert tracker._records[0]["cost"] == 0.01

    def test_record_with_none_tokens_defaults_to_zero(self, tracker):
        tracker.record("zhipu", "glm-4-flash", None, None)
        assert tracker._records[0]["prompt_tokens"] == 0
        assert tracker._records[0]["completion_tokens"] == 0
        assert tracker._records[0]["total_tokens"] == 0

    def test_record_multiple(self, tracker):
        for i in range(5):
            tracker.record("zhipu", "glm-4-flash", 100 * i, 50 * i)
        assert len(tracker._records) == 5

    def test_record_empty_provider(self):
        """空 provider 应默认为 'unknown'"""
        tracker = UsageTracker(path="/tmp/test_usage_xyz.json")
        tracker.record("", "glm-4-flash", 10, 5)
        assert tracker._records[0]["provider"] == "unknown"

    def test_record_timestamp_recent(self, tracker):
        before = time.time()
        tracker.record("zhipu", "glm-4-flash", 10, 5)
        after = time.time()
        assert before <= tracker._records[0]["timestamp"] <= after


class TestCostEstimate:

    def test_estimate_with_config(self, tmp_path):
        cfg = {
            "usage_prices": {
                "deepseek": {
                    "deepseek-chat": {"prompt": 1.5, "completion": 6.0},
                }
            }
        }
        tracker = UsageTracker(path=str(tmp_path / "u.json"), cfg=cfg)
        # 1k prompt tokens @ 1.5元/k + 1k completion @ 6.0元/k
        cost = tracker._estimate_cost("deepseek", "deepseek-chat", 1000, 1000)
        # 单位可能不同(/千 tokens vs /百万 tokens)
        assert cost >= 0

    def test_estimate_unknown_provider_returns_zero(self, tracker):
        cost = tracker._estimate_cost("unknown_provider", "model", 1000, 1000)
        assert cost == 0.0


class TestSummary:

    def test_summary_empty(self, tracker):
        s = tracker.summary(days=30)
        assert s["days"] == 30
        assert s["calls"] == 0
        assert s["prompt_tokens"] == 0
        assert s["completion_tokens"] == 0
        assert s["total_tokens"] == 0

    def test_summary_aggregates(self, tracker):
        tracker.record("zhipu", "glm-4-flash", 100, 50)
        tracker.record("zhipu", "glm-4-flash", 200, 100)
        tracker.record("deepseek", "deepseek-chat", 300, 150)
        s = tracker.summary(days=30)
        assert s["calls"] == 3
        assert s["prompt_tokens"] == 600
        assert s["completion_tokens"] == 300
        assert s["total_tokens"] == 900

    def test_summary_filters_by_days(self, tracker):
        # 手动插入老记录
        tracker._records.append({
            "timestamp": time.time() - 100 * 86400,  # 100 天前
            "provider": "zhipu", "model": "glm-4-flash",
            "prompt_tokens": 999, "completion_tokens": 999, "total_tokens": 1998,
            "cost": 0.0,
        })
        tracker.record("zhipu", "glm-4-flash", 10, 5)  # 今天
        s = tracker.summary(days=30)
        # 只应包含今天的
        assert s["calls"] == 1
        assert s["prompt_tokens"] == 10


class TestReset:

    def test_reset_clears_records(self, tracker):
        tracker.record("zhipu", "glm-4-flash", 100, 50)
        assert len(tracker._records) > 0
        tracker.reset()
        assert tracker._records == []


class TestPersistence:

    def test_persists_across_instances(self, tmp_path):
        path = str(tmp_path / "usage.json")
        t1 = UsageTracker(path=path)
        t1.record("zhipu", "glm-4-flash", 100, 50)

        # 新实例从同一路径读取
        t2 = UsageTracker(path=path)
        assert len(t2._records) == 1
        assert t2._records[0]["prompt_tokens"] == 100
