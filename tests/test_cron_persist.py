"""
定时任务持久化测试
"""
import json
from pathlib import Path

import pytest

from fr_cli.weapon.cron import CronManager


@pytest.fixture(autouse=True)
def _isolate_cron_store(tmp_path, monkeypatch):
    """每个测试使用独立 cron 持久化文件"""
    store = tmp_path / "cron.json"
    monkeypatch.setattr("fr_cli.weapon.cron.CRON_STORE_FILE", store)
    yield


def test_cron_persist_and_load():
    mgr = CronManager()
    jid, _ = mgr.add_job("echo hello", 10, "zh")

    # 验证持久化文件已写入
    store = Path(str(mgr._persist.__globals__["CRON_STORE_FILE"]))
    assert store.exists()
    data = json.loads(store.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["cmd"] == "echo hello"
    assert data[0]["interval"] == 10

    # 新建管理器并加载
    mgr2 = CronManager()
    mgr2.load_persistent_jobs("zh")
    assert len(mgr2.jobs) == 1
    assert mgr2.jobs[0]["cmd"] == "echo hello"

    # 删除任务后持久化文件清空
    mgr2.del_job(jid, "zh")
    data = json.loads(store.read_text(encoding="utf-8"))
    assert len(data) == 0
