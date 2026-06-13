"""
Gatekeeper 配置持久化测试 —— 验证已迁移到 JsonStore。
"""
import pytest

from fr_cli.gatekeeper import manager as manager_module


@pytest.fixture(autouse=True)
def _isolate_gatekeeper_store(tmp_path, monkeypatch):
    store = tmp_path / "gatekeeper.json"
    monkeypatch.setattr(manager_module, "DAEMON_CONFIG_FILE", store)
    yield


def test_save_and_read_daemon_config():
    cfg = {"cron_jobs": [{"cmd": "echo hi", "interval": 60}]}
    result = manager_module.GatekeeperManager.save_daemon_config(cfg)
    assert result.is_ok()
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
