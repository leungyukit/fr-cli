"""
Cron 表达式 + at 一次性任务测试
覆盖新增的 schedule 参数（cron 表达式 / 一次性任务）功能。
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from fr_cli.weapon.cron import CronManager, _parse_schedule, _next_run


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """每个测试使用独立 HOME + 隔离存储"""
    fake_home = tmp_path / "home"
    fake_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(fake_home))
    import fr_cli.conf.paths as _paths_mod
    monkeypatch.setattr(_paths_mod._root_holder, "value", fake_home / ".fr_cli")
    yield


def test_parse_interval():
    """interval 模式解析"""
    assert _parse_schedule("every 60s") == ("interval", 60.0)
    assert _parse_schedule("every 30") == ("interval", 30.0)
    assert _parse_schedule("interval:90") == ("interval", 90.0)


def test_parse_cron():
    """cron 表达式解析"""
    assert _parse_schedule("0 9 * * *") == ("cron", "0 9 * * *")
    assert _parse_schedule("*/5 * * * *") == ("cron", "*/5 * * * *")
    assert _parse_schedule("cron:0 0 * * 0") == ("cron", "0 0 * * 0")


def test_parse_at():
    """at 一次性任务解析"""
    at_dt = datetime(2026, 12, 31, 23, 59, 59)
    mode, value = _parse_schedule("2026-12-31 23:59:59")
    assert mode == "at"
    assert value == at_dt
    mode, value = _parse_schedule("at:2026-12-31 23:59:59")
    assert mode == "at"
    assert value == at_dt


def test_parse_invalid():
    """无效输入应抛 ValueError"""
    with pytest.raises(ValueError):
        _parse_schedule("invalid_garbage")
    with pytest.raises(ValueError):
        _parse_schedule("")


def test_next_run_interval():
    """interval 模式:now + N 秒"""
    base = datetime(2026, 7, 1, 12, 0, 0)
    next_at = _next_run("interval", 60, after=base)
    assert next_at == base + timedelta(seconds=60)


def test_next_run_cron():
    """cron 模式:croniter 计算"""
    base = datetime(2026, 7, 1, 8, 0, 0)
    # 每天 9 点
    next_at = _next_run("cron", "0 9 * * *", after=base)
    assert next_at == datetime(2026, 7, 1, 9, 0, 0)


def test_add_job_with_cron_schedule():
    """用 cron 表达式添加任务"""
    mgr = CronManager()
    result = mgr.add_job(schedule="0 9 * * *", cmd="echo morning", lang="zh")
    assert result is not None
    job_id, msg = result
    assert job_id is not None
    assert "cron" in msg or "布阵" in msg
    assert len(mgr.jobs) == 1
    job = mgr.jobs[0]
    assert job["mode"] == "cron"
    assert job["value"] == "0 9 * * *"


def test_add_job_with_at_schedule():
    """用 at 添加一次性任务"""
    mgr = CronManager()
    future = (datetime.now() + timedelta(hours=1)).isoformat()
    result = mgr.add_job(schedule=future, cmd="echo once", lang="zh")
    assert result is not None
    job_id, _ = result
    assert job_id is not None
    assert len(mgr.jobs) == 1
    assert mgr.jobs[0]["mode"] == "at"


def test_add_job_invalid_schedule():
    """无效的 schedule 字符串应被拒绝"""
    mgr = CronManager()
    result = mgr.add_job(schedule="nonsense 123", cmd="echo x", lang="zh")
    assert result[0] is None  # job_id 为 None
    assert "无效" in result[1] or "cron" in result[1]


def test_backward_compat_interval():
    """旧式 add_job(cmd, interval, lang) 仍能工作"""
    mgr = CronManager()
    result = mgr.add_job("echo legacy", 30, "zh")
    assert result[0] is not None
    assert len(mgr.jobs) == 1
    assert mgr.jobs[0]["mode"] == "interval"
    assert mgr.jobs[0]["value"] == 30


def test_cron_job_persists_in_new_format():
    """cron 任务持久化到主配置时用新格式"""
    mgr = CronManager()
    mgr.add_job(schedule="*/10 * * * *", cmd="echo every-10min", lang="zh")

    config_file = Path.home() / ".fr_cli" / "config.json"
    cfg = json.loads(config_file.read_text(encoding="utf-8"))
    assert "cron" in cfg
    assert cfg["cron"][0]["mode"] == "cron"
    assert cfg["cron"][0]["value"] == "*/10 * * * *"
    assert cfg["cron"][0]["cmd"] == "echo every-10min"


def test_min_interval_enforced_for_interval_only():
    """interval 模式强制 ≥ MIN_INTERVAL，cron/at 模式不受限"""
    mgr = CronManager()
    # interval 太短
    r = mgr.add_job("echo x", 3, "zh")
    assert r[0] is None
    # cron 不受限
    r = mgr.add_job(schedule="* * * * *", cmd="echo x", lang="zh")
    assert r[0] is not None
    # at 不受限
    future = (datetime.now() + timedelta(hours=1)).isoformat()
    r = mgr.add_job(schedule=future, cmd="echo x", lang="zh")
    assert r[0] is not None


def test_legacy_migration_still_works():
    """老格式(只有 interval 字段,无 mode)的迁移测试"""
    # 写一个老格式的 cron.json
    old_file = Path.home() / ".fr_cli" / "cron.json"
    old_file.parent.mkdir(parents=True, exist_ok=True)
    old_file.write_text(json.dumps([
        {"id": 99, "cmd": "legacy task", "interval": 30, "job_type": "shell"}
    ]), encoding="utf-8")

    mgr = CronManager()
    mgr.load_persistent_jobs(lang="zh")
    assert len(mgr.jobs) == 1
    assert mgr.jobs[0]["cmd"] == "legacy task"
    # 老文件已迁移
    assert not old_file.exists()
    assert (Path.home() / ".fr_cli" / "cron.json.migrated").exists()
