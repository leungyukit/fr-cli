"""
UsageTracker 测试 —— 用量记录、汇总、持久化与费用估算。
"""
import time

import pytest

from fr_cli.core.usage import UsageTracker


@pytest.fixture
def tracker(tmp_path):
    return UsageTracker(path=tmp_path / "usage.json")


def test_record_and_summary(tracker):
    tracker.record("zhipu", "glm-4-flash", 100, 50)
    tracker.record("deepseek", "deepseek-chat", 200, 80)
    stats = tracker.summary(days=30)
    assert stats["calls"] == 2
    assert stats["prompt_tokens"] == 300
    assert stats["completion_tokens"] == 130
    assert stats["total_tokens"] == 430


def test_summary_filters_days(tracker):
    old_time = time.time() - 40 * 86400
    tracker._records.append({
        "timestamp": old_time,
        "provider": "zhipu",
        "model": "glm-4-flash",
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
        "cost": 0.0,
    })
    tracker.record("zhipu", "glm-4-flash", 100, 50)
    stats = tracker.summary(days=30)
    assert stats["calls"] == 1
    assert stats["total_tokens"] == 150


def test_persistence(tmp_path):
    path = tmp_path / "usage.json"
    t1 = UsageTracker(path=path)
    t1.record("kimi", "moonshot-v1-8k", 50, 20)
    del t1

    t2 = UsageTracker(path=path)
    stats = t2.summary(days=30)
    assert stats["calls"] == 1
    assert stats["prompt_tokens"] == 50


def test_cost_estimation(tmp_path):
    cfg = {
        "usage_prices": {
            "deepseek": {
                "prompt": 1.0,
                "completion": 2.0,
            }
        }
    }
    tracker = UsageTracker(path=tmp_path / "usage.json", cfg=cfg)
    tracker.record("deepseek", "deepseek-chat", 1000, 500)
    # (1000*1 + 500*2) / 1000 = 2.0
    assert tracker.summary(days=30)["estimated_cost"] == 2.0


def test_model_specific_price(tmp_path):
    cfg = {
        "usage_prices": {
            "deepseek": {
                "deepseek-chat": {"prompt": 1.5, "completion": 3.0},
                "deepseek-coder": {"prompt": 2.0, "completion": 4.0},
            }
        }
    }
    tracker = UsageTracker(path=tmp_path / "usage.json", cfg=cfg)
    tracker.record("deepseek", "deepseek-coder", 1000, 500)
    assert tracker.summary(days=30)["estimated_cost"] == 4.0


def test_reset(tracker):
    tracker.record("zhipu", "glm-4-flash", 10, 5)
    tracker.reset()
    assert tracker.summary(days=30)["calls"] == 0
