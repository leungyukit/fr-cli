"""
定时任务持久化测试

从 ~/.fr_cli/cron.json 迁移到 ~/.fr_cli/config.json 的 cron 命名空间。
"""
import json
from pathlib import Path

import pytest

from fr_cli.weapon.cron import CronManager


@pytest.fixture(autouse=True)
def _isolate_cron_store(tmp_path, monkeypatch):
    """每个测试使用独立主配置目录，老 cron.json 路径也指向 tmp"""
    fake_home = tmp_path / "home"
    fake_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(fake_home))

    # 让老路径指向 tmp，便于测试迁移
    fake_fr_cli = fake_home / ".fr_cli"
    fake_fr_cli.mkdir(parents=True, exist_ok=True)
    old_store = fake_fr_cli / "cron.json"
    monkeypatch.setattr("fr_cli.weapon.cron.CRON_STORE_FILE", old_store)
    # 通过 _root_holder 改路径（ROOT 是只读的不可直接 set）
    import fr_cli.conf.paths as _paths_mod
    monkeypatch.setattr(_paths_mod._root_holder, "value", fake_fr_cli)
    yield


def test_cron_persist_and_load():
    mgr = CronManager()
    jid, _ = mgr.add_job("echo hello", 10, "zh")

    # 验证持久化到主配置
    config_file = Path.home() / ".fr_cli" / "config.json"
    assert config_file.exists()
    cfg = json.loads(config_file.read_text(encoding="utf-8"))
    assert "cron" in cfg
    data = cfg["cron"]
    assert len(data) == 1
    assert data[0]["cmd"] == "echo hello"
    # 兼容新旧两种格式
    if "interval" in data[0]:
        assert data[0]["interval"] == 10
    else:
        assert data[0]["mode"] == "interval"
        assert data[0]["value"] == 10

    # 新建管理器并加载
    mgr2 = CronManager()
    mgr2.load_persistent_jobs("zh")
    assert len(mgr2.jobs) == 1
    assert mgr2.jobs[0]["cmd"] == "echo hello"

    # 删除任务后主配置 cron 命名空间清空
    mgr2.del_job(jid, "zh")
    cfg = json.loads(config_file.read_text(encoding="utf-8"))
    assert cfg.get("cron") == []


def test_cron_legacy_migration():
    """老 cron.json 会在首次加载时自动迁移到主配置"""
    old_store = Path.home() / ".fr_cli" / "cron.json"
    old_store.write_text(json.dumps([
        {"id": 99, "cmd": "legacy task", "interval": 30, "job_type": "shell",
         "agent_name": None, "agent_input": ""}
    ]), encoding="utf-8")

    mgr = CronManager()
    mgr.load_persistent_jobs("zh")
    assert len(mgr.jobs) == 1
    assert mgr.jobs[0]["cmd"] == "legacy task"

    # 主配置已包含老数据
    cfg = json.loads((Path.home() / ".fr_cli" / "config.json").read_text(encoding="utf-8"))
    assert cfg["cron"][0]["cmd"] == "legacy task"

    # 老文件已重命名
    assert not old_store.exists()
    assert (Path.home() / ".fr_cli" / "cron.json.migrated").exists()
