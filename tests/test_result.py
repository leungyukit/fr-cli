"""
Result 统一返回容器测试。
"""
import pytest

from fr_cli.core.result import Result


def test_success():
    r = Result.ok("data")
    assert r.is_ok()
    assert not r.is_fail()
    assert r.unwrap() == "data"
    assert r.unwrap_or("default") == "data"
    assert r.to_tuple() == ("data", None)


def test_failure():
    r = Result.fail("boom")
    assert r.is_fail()
    assert not r.is_ok()
    assert r.unwrap_or("default") == "default"
    assert r.to_tuple() == (None, "boom")
    with pytest.raises(RuntimeError):
        r.unwrap()


def test_from_tuple_success():
    r = Result.from_tuple("data", None)
    assert r.is_ok()
    assert r.data == "data"


def test_from_tuple_failure():
    r = Result.from_tuple(None, "err")
    assert r.is_fail()
    assert r.error == "err"
