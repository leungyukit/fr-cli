"""
Result 统一返回风格测试
覆盖 ok/fail 构造、is_ok/is_fail、unwrap/unwrap_or、to_tuple/from_tuple、
迭代器协议、链式调用等。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fr_cli.core.result import Result


class TestBasicConstruction:

    def test_ok_with_data(self):
        r = Result.ok({"foo": "bar"})
        assert r.is_ok()
        assert r.is_fail() is False
        assert r.data == {"foo": "bar"}
        assert r.error is None

    def test_ok_without_data(self):
        r = Result.ok()
        assert r.is_ok()
        assert r.data is None

    def test_fail_with_error(self):
        r = Result.fail("something went wrong")
        assert r.is_fail()
        assert r.is_ok() is False
        assert r.error == "something went wrong"
        assert r.data is None

    def test_direct_construction_ok(self):
        r = Result(ok=True, data=42)
        assert r.is_ok()
        assert r.data == 42

    def test_direct_construction_fail(self):
        r = Result(ok=False, error="oops")
        assert r.is_fail()
        assert r.error == "oops"


class TestUnwrap:

    def test_unwrap_ok_returns_data(self):
        r = Result.ok([1, 2, 3])
        assert r.unwrap() == [1, 2, 3]

    def test_unwrap_fail_raises(self):
        r = Result.fail("error")
        with pytest.raises(Exception) as exc_info:
            r.unwrap()
        # 错误信息应包含原 error
        assert "error" in str(exc_info.value)

    def test_unwrap_or_returns_data_when_ok(self):
        r = Result.ok("value")
        assert r.unwrap_or("default") == "value"

    def test_unwrap_or_returns_default_when_fail(self):
        r = Result.fail("err")
        assert r.unwrap_or("default") == "default"


class TestTupleInterop:

    def test_to_tuple_ok(self):
        r = Result.ok(42)
        assert r.to_tuple() == (42, None)

    def test_to_tuple_fail(self):
        r = Result.fail("err")
        assert r.to_tuple() == (None, "err")

    def test_from_tuple_ok(self):
        r = Result.from_tuple(42, None)
        assert r.is_ok()
        assert r.data == 42

    def test_from_tuple_fail(self):
        r = Result.from_tuple(None, "err")
        assert r.is_fail()
        assert r.error == "err"

    def test_tuple_unpacking_ok(self):
        """Result 支持 (data, error) 元组解包,向后兼容"""
        r = Result.ok("hello")
        data, error = r
        assert data == "hello"
        assert error is None

    def test_tuple_unpacking_fail(self):
        r = Result.fail("oops")
        data, error = r
        assert data is None
        assert error == "oops"


class TestRepr:

    def test_repr_ok(self):
        r = Result.ok(42)
        s = repr(r)
        assert "ok" in s.lower() or "True" in s

    def test_repr_fail(self):
        r = Result.fail("err")
        s = repr(r)
        assert "fail" in s.lower() or "err" in s or "False" in s


class TestResultWithVariousData:

    def test_with_dict(self):
        r = Result.ok({"a": 1, "b": [1, 2, 3]})
        assert r.data["a"] == 1
        assert r.data["b"] == [1, 2, 3]

    def test_with_list(self):
        r = Result.ok([1, 2, 3])
        assert len(r.data) == 3

    def test_with_none(self):
        r = Result.ok(None)
        assert r.is_ok()
        assert r.data is None

    def test_with_nested_result(self):
        """Result 可以嵌套"""
        inner = Result.ok(42)
        outer = Result.ok(inner)
        assert outer.data.data == 42
