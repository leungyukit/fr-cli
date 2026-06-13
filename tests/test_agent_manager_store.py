"""
Agent manager 配置与进度持久化测试 —— 验证已迁移到 JsonStore。
"""
import pytest

from fr_cli import agent as agent_module
from fr_cli.agent import manager as manager_module
from fr_cli.agent.manager import (
    load_agent_config, save_agent_config, load_progress, save_progress
)


@pytest.fixture(autouse=True)
def _isolate_agents_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(manager_module, "AGENTS_DIR", tmp_path)
    monkeypatch.setattr(agent_module, "AGENTS_DIR", tmp_path)
    yield


def test_save_and_load_agent_config():
    save_agent_config("coder", {"provider": "deepseek", "model": "deepseek-chat"})
    cfg = load_agent_config("coder")
    assert cfg["provider"] == "deepseek"
    assert cfg["model"] == "deepseek-chat"


def test_load_agent_config_missing_returns_empty():
    assert load_agent_config("nonexistent") == {}


def test_save_and_load_progress():
    save_progress("coder", {"runs": [{"status": "success"}]})
    progress = load_progress("coder")
    assert progress["runs"][0]["status"] == "success"


def test_load_progress_missing_returns_empty():
    assert load_progress("nonexistent") == {}
