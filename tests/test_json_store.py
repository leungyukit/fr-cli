"""
JsonStore 统一持久化抽象测试。
"""

import pytest

from fr_cli.core.store import JsonStore


def test_read_missing_returns_default(tmp_path):
    store = JsonStore(tmp_path / "missing.json", default=list)
    assert store.read() == []


def test_read_missing_dict_default(tmp_path):
    store = JsonStore(tmp_path / "missing.json")
    assert store.read() == {}


def test_write_and_read(tmp_path):
    path = tmp_path / "data.json"
    store = JsonStore(path)
    store.write({"a": 1, "b": [2, 3]})
    assert store.read() == {"a": 1, "b": [2, 3]}
    assert path.exists()


def test_atomic_write(tmp_path):
    path = tmp_path / "atomic.json"
    store = JsonStore(path)
    store.write({"x": 1})
    # .tmp 文件不应残留
    assert not (tmp_path / "atomic.json.tmp").exists()


def test_file_permissions(tmp_path):
    path = tmp_path / "secure.json"
    store = JsonStore(path, chmod=0o600)
    store.write({"secret": 1})
    # 某些文件系统/平台可能不支持权限，跳过异常
    try:
        mode = path.stat().st_mode
        assert (mode & 0o777) == 0o600
    except Exception:
        pytest.skip("权限检查在当前环境不可用")


def test_corrupted_file_returns_default(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("not json", encoding="utf-8")
    store = JsonStore(path, default=list)
    assert store.read() == []


def test_default_factory_called_each_time(tmp_path):
    path = tmp_path / "factory.json"
    store = JsonStore(path, default=lambda: {"items": []})
    d1 = store.read()
    d2 = store.read()
    assert d1 is not d2
    d1["items"].append(1)
    assert d2["items"] == []


def test_delete(tmp_path):
    path = tmp_path / "del.json"
    store = JsonStore(path)
    store.write({"a": 1})
    assert path.exists()
    store.delete()
    assert not path.exists()
