"""
JsonStore 统一 JSON 持久化测试
覆盖原子写、默认回退、文件权限、线程安全、嵌套数据等。
"""
import json
import os
import sys
import threading


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fr_cli.core.store import JsonStore


class TestBasicOperations:

    def test_write_and_read(self, tmp_path):
        path = tmp_path / "data.json"
        store = JsonStore(path)
        store.write({"key": "value"})
        assert store.read() == {"key": "value"}

    def test_read_nonexistent_returns_default(self, tmp_path):
        path = tmp_path / "missing.json"
        store = JsonStore(path, default={"default": True})
        assert store.read() == {"default": True}

    def test_exists(self, tmp_path):
        path = tmp_path / "data.json"
        store = JsonStore(path)
        assert not store.exists()
        store.write({"x": 1})
        assert store.exists()

    def test_delete(self, tmp_path):
        path = tmp_path / "data.json"
        store = JsonStore(path)
        store.write({"x": 1})
        assert path.exists()
        store.delete()
        assert not path.exists()

    def test_delete_nonexistent_no_error(self, tmp_path):
        path = tmp_path / "missing.json"
        store = JsonStore(path)
        store.delete()  # 不应抛异常


class TestDataTypes:

    def test_write_list(self, tmp_path):
        path = tmp_path / "data.json"
        store = JsonStore(path)
        store.write([1, 2, 3])
        assert store.read() == [1, 2, 3]

    def test_write_string(self, tmp_path):
        path = tmp_path / "data.json"
        store = JsonStore(path)
        store.write("just a string")
        assert store.read() == "just a string"

    def test_write_int(self, tmp_path):
        path = tmp_path / "data.json"
        store = JsonStore(path)
        store.write(42)
        assert store.read() == 42

    def test_write_nested_dict(self, tmp_path):
        path = tmp_path / "data.json"
        store = JsonStore(path)
        data = {"users": [{"name": "Alice", "age": 30}], "meta": {"version": 1}}
        store.write(data)
        assert store.read() == data

    def test_overwrite_replaces_completely(self, tmp_path):
        path = tmp_path / "data.json"
        store = JsonStore(path)
        store.write({"a": 1, "b": 2})
        store.write({"c": 3})
        assert store.read() == {"c": 3}


class TestFilePermissions:

    def test_default_chmod_0o600(self, tmp_path):
        """默认权限 0o600(仅所有者可读写)"""
        path = tmp_path / "secret.json"
        store = JsonStore(path, default={})
        store.write({"token": "secret"})
        mode = path.stat().st_mode & 0o777
        assert mode == 0o600, f"expected 0o600, got {oct(mode)}"

    def test_custom_chmod(self, tmp_path):
        path = tmp_path / "public.json"
        store = JsonStore(path, default={}, chmod=0o644)
        store.write({"x": 1})
        mode = path.stat().st_mode & 0o777
        assert mode == 0o644


class TestAtomicity:

    def test_atomic_write_no_partial_file(self, tmp_path):
        """原子写:不应留下损坏的部分文件"""
        path = tmp_path / "data.json"
        store = JsonStore(path)
        store.write({"key": "value"})
        # 路径下的临时文件不应残留
        tmp_files = list(tmp_path.glob("*.tmp")) + list(tmp_path.glob(".*.tmp"))
        assert tmp_files == [], f"残留临时文件: {tmp_files}"


class TestConcurrency:

    def test_concurrent_writes(self, tmp_path):
        """多线程并发写:最终结果应一致(后写者覆盖)"""
        path = tmp_path / "counter.json"
        store = JsonStore(path)
        errors = []

        def writer(val):
            try:
                for _ in range(10):
                    store.write({"value": val})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        # 最终文件应是合法 JSON
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "value" in data


class TestReadWithDefault:

    def test_default_used_when_file_missing(self, tmp_path):
        path = tmp_path / "absent.json"
        default = {"fallback": True, "count": 0}
        store = JsonStore(path, default=default)
        # 不创建文件,read 应返回 default
        assert store.read() == default

    def test_default_not_mutated(self, tmp_path):
        """多次 read 不应修改 default dict"""
        path = tmp_path / "absent.json"
        default = {"x": 1}
        store = JsonStore(path, default=default)
        store.read()
        store.read()
        assert default == {"x": 1}


class TestInvalidJSON:

    def test_read_corrupted_json_returns_default(self, tmp_path):
        path = tmp_path / "corrupt.json"
        path.write_text("{not valid json", encoding="utf-8")
        store = JsonStore(path, default={"recovered": True})
        # 应优雅降级到 default
        result = store.read()
        assert result == {"recovered": True}
