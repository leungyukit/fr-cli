"""
memory/history 与 memory/session 持久化测试 —— 验证已迁移到 JsonStore。
"""
import pytest

from fr_cli import conf as conf_module
from fr_cli.memory import history as history_module
from fr_cli.memory import session as session_module
from fr_cli.memory.history import save_sess, load_sess, get_sessions, del_sess
from fr_cli.memory.session import (
    create_session, update_session, list_sessions, load_session, delete_session
)


@pytest.fixture(autouse=True)
def _isolate_history_dir(tmp_path, monkeypatch):
    hist_dir = tmp_path / "sessions" / "manual"
    monkeypatch.setattr(history_module, "HIST_DIR", hist_dir)
    # SESSIONS_MANUAL_DIR = ROOT / "sessions" / "manual"
    # 通过设置 _root_holder.value 让整个根目录都指向 tmp_path
    monkeypatch.setattr(conf_module.paths._root_holder, "value", tmp_path)
    yield


@pytest.fixture(autouse=True)
def _isolate_session_dir(tmp_path, monkeypatch):
    auto_dir = tmp_path / "sessions" / "auto"
    monkeypatch.setattr(session_module, "SESSION_DIR", auto_dir)
    # 已经在 _isolate_history_dir 里设过,这里无需重复
    yield


def test_save_and_load_history():
    msgs = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    assert save_sess("test", msgs) is True
    sessions = get_sessions()
    assert len(sessions) == 1
    ok, loaded, name = load_sess(0, "sp")
    assert ok is True
    assert name == "test"
    assert loaded[0]["role"] == "system"
    assert loaded[0]["content"] == "sp"
    assert loaded[1]["content"] == "hi"


def test_delete_history():
    save_sess("del", [])
    assert len(get_sessions()) == 1
    assert del_sess(0) is True
    assert len(get_sessions()) == 0


def test_create_and_update_session():
    path = create_session([{"role": "user", "content": "hi"}])
    assert path is not None
    sessions = list_sessions()
    assert len(sessions) == 1
    ok = update_session(path, [{"role": "user", "content": "updated"}])
    assert ok is True
    ok, msgs, fname = load_session(1, "sp")
    assert ok is True
    assert msgs[1]["content"] == "updated"


def test_delete_session():
    create_session([{"role": "user", "content": "hi"}])
    assert delete_session(1) is True
    assert len(list_sessions()) == 0
