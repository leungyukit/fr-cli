"""
Gatekeeper 配置持久化测试 —— 验证已迁移到 ~/.fr_cli/config.json 的 gatekeeper 命名空间。
"""
import json
from pathlib import Path

import pytest

from fr_cli.gatekeeper import manager as manager_module


@pytest.fixture(autouse=True)
def _isolate_gatekeeper_store(tmp_path, monkeypatch):
    """每个测试使用独立的 HOME，隔离主配置和老文件"""
    fake_home = tmp_path / "home"
    fake_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(fake_home))

    fake_fr_cli = fake_home / ".fr_cli"
    fake_fr_cli.mkdir(parents=True, exist_ok=True)
    old_store = fake_fr_cli / "daemon" / "config.json"
    monkeypatch.setattr(manager_module, "DAEMON_CONFIG_FILE", old_store)
    # 通过 _root_holder 改路径
    import fr_cli.conf.paths as _paths_mod
    monkeypatch.setattr(_paths_mod._root_holder, "value", fake_fr_cli)
    yield


def test_save_and_read_daemon_config():
    cfg = {"cron_jobs": [{"cmd": "echo hi", "interval": 60}]}
    result = manager_module.GatekeeperManager.save_daemon_config(cfg)
    assert result.is_ok()

    # 验证主配置已写入
    config_file = Path.home() / ".fr_cli" / "config.json"
    main_cfg = json.loads(config_file.read_text(encoding="utf-8"))
    assert main_cfg["gatekeeper"]["cron_jobs"][0]["cmd"] == "echo hi"

    loaded = manager_module.read_daemon_config()
    assert loaded["cron_jobs"][0]["cmd"] == "echo hi"


def test_sync_gatekeeper_cron_jobs():
    assert manager_module.sync_gatekeeper_cron_jobs(
        cron_jobs=[{"cmd": "echo a", "interval": 10}]
    ) is True
    cfg = manager_module.read_daemon_config()
    assert len(cfg["cron_jobs"]) == 1

    assert manager_module.sync_gatekeeper_cron_jobs(
        agent_crons=[{"agent_name": "agent1", "interval": 20}]
    ) is True
    cfg = manager_module.read_daemon_config()
    assert len(cfg["agent_crons"]) == 1


def test_read_daemon_config_missing_returns_empty():
    assert manager_module.read_daemon_config() == {}


def test_gatekeeper_legacy_migration():
    """老 daemon/config.json 会在首次加载时自动迁移到主配置"""
    old_store = Path.home() / ".fr_cli" / "daemon" / "config.json"
    old_store.parent.mkdir(parents=True, exist_ok=True)
    old_store.write_text(json.dumps({
        "agent_server_port": 17890,
        "cron_jobs": [{"id": 1, "cmd": "legacy", "interval": 30, "job_type": "shell"}],
    }), encoding="utf-8")

    cfg = manager_module.read_daemon_config()
    assert cfg["agent_server_port"] == 17890
    assert cfg["cron_jobs"][0]["cmd"] == "legacy"

    # 验证主配置已合并
    main_cfg = json.loads((Path.home() / ".fr_cli" / "config.json").read_text(encoding="utf-8"))
    assert main_cfg["gatekeeper"]["agent_server_port"] == 17890

    # 老文件已重命名
    assert not old_store.exists()
    assert (Path.home() / ".fr_cli" / "daemon" / "config.json.migrated").exists()
