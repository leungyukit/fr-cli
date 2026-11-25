"""v2.8.7(P2-5 / P2-6)回归测试

P2-5：并行工具不再共享同一个 msgs list（每线程一份副本）
P2-6：Result 保留异常类型，registry.dispatch 不再把异常压成纯字符串
"""
from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from fr_cli.core.result import Result


# ============================================================
# P2-6 —— 异常类型保留
# ============================================================


class TestResultErrorType:
    def test_fail_without_error_type(self):
        r = Result.fail("boom")
        assert r.error_type is None

    def test_fail_with_error_type(self):
        r = Result.fail("boom", error_type="FileNotFoundError")
        assert r.error_type == "FileNotFoundError"
        assert r.error == "boom"

    def test_ok_has_no_error_type(self):
        assert Result.ok(1).error_type is None

    def test_from_tuple_keeps_working(self):
        r = Result.from_tuple(None, "err")
        assert r.is_fail()
        assert r.error == "err"
        assert r.error_type is None

    def test_repr_mentions_error_type(self):
        r = Result.fail("boom", error_type="ValueError")
        assert "ValueError" in repr(r)

    def test_repr_without_error_type_unchanged(self):
        assert repr(Result.fail("boom")) == "Result.fail('boom')"


class TestRegistryPreservesExceptionType:
    def _registry_with_raising_tool(self):
        from fr_cli.command.registry import get_registry

        reg = get_registry()

        def boom(deps, **kwargs):
            raise FileNotFoundError("目标文件不存在")

        reg._tools["__test_boom__"] = {
            "handler": boom,
            "description": "测试用：必定抛异常",
            "params": {},
            "security": None,
            "aliases": [],
            "needs_msgs": False,
            "triggers": [],
        }
        return reg

    def test_dispatch_keeps_exception_type(self):
        reg = self._registry_with_raising_tool()
        try:
            result = reg.dispatch(SimpleNamespace(), "__test_boom__")
            assert result.is_fail()
            assert result.error_type == "FileNotFoundError"
            # 原有文案保留（不破坏既有断言）
            assert "目标文件不存在" in result.error
        finally:
            reg._tools.pop("__test_boom__", None)

    def test_success_result_has_no_error_type(self):
        from fr_cli.command.registry import get_registry

        reg = get_registry()

        def fine(deps, **kwargs):
            return Result.ok("好")

        reg._tools["__test_fine__"] = {
            "handler": fine,
            "description": "测试用",
            "params": {},
            "security": None,
            "aliases": [],
            "needs_msgs": False,
            "triggers": [],
        }
        try:
            result = reg.dispatch(SimpleNamespace(), "__test_fine__")
            assert result.is_ok()
            assert result.error_type is None
        finally:
            reg._tools.pop("__test_fine__", None)


# ============================================================
# P2-5 —— 并行工具的 msgs 隔离
# ============================================================


class TestIsolateMsgs:
    def test_none_and_empty(self):
        from fr_cli.command.parallel import _isolate_msgs

        assert _isolate_msgs(None) is None
        assert _isolate_msgs([]) == []

    def test_list_is_copied(self):
        from fr_cli.command.parallel import _isolate_msgs

        src = [{"role": "user", "content": "a"}]
        out = _isolate_msgs(src)
        assert out is not src
        assert out == src

    def test_message_dicts_are_copied(self):
        """只拷列表不够 —— 工具改 msgs[i]["content"] 仍会串到别的线程"""
        from fr_cli.command.parallel import _isolate_msgs

        src = [{"role": "user", "content": "a"}]
        out = _isolate_msgs(src)
        out[0]["content"] = "改过了"
        assert src[0]["content"] == "a"

    def test_non_dict_items_preserved(self):
        from fr_cli.command.parallel import _isolate_msgs

        src = [{"role": "user", "content": "a"}, "裸字符串"]
        out = _isolate_msgs(src)
        assert out[1] == "裸字符串"


class TestParallelMsgsIsolation:
    def test_each_worker_gets_its_own_msgs(self):
        """并发执行的两个工具各自改 msgs，不应互相影响"""
        from fr_cli.command.parallel import ParallelExecutor

        shared_msgs = [{"role": "user", "content": "原始"}]
        seen = []
        barrier = threading.Barrier(2, timeout=5)

        class FakeExecutor:
            def _parse_tool_kwargs(self, arg_str):
                return {}

            def invoke_tool(self, tool_name, kwargs, msgs=None, **kw):
                # 两个线程都到这里 → 强制并发重叠
                msgs.append({"role": "assistant", "content": tool_name})
                barrier.wait()
                seen.append((tool_name, list(msgs)))
                return Result.ok(tool_name)

        pe = ParallelExecutor(FakeExecutor(), max_workers=2)
        results, markers = pe.execute_batch(
            [("tool_a", "{}", "A"), ("tool_b", "{}", "B")], msgs=shared_msgs
        )

        assert len(results) == 2
        assert all(r.is_ok() for r in results)
        # 两个线程看到的 msgs 内容互不相同（各自只多了一条自己的）
        contents = sorted(len(m) for _, m in seen)
        assert contents == [2, 2]
        # 原始共享列表没被污染
        assert len(shared_msgs) == 1
        assert shared_msgs[0]["content"] == "原始"

    def test_none_msgs_still_works(self):
        from fr_cli.command.parallel import ParallelExecutor

        class FakeExecutor:
            def _parse_tool_kwargs(self, arg_str):
                return {}

            def invoke_tool(self, tool_name, kwargs, msgs=None, **kw):
                return Result.ok(tool_name)

        pe = ParallelExecutor(FakeExecutor(), max_workers=2)
        results, _markers = pe.execute_batch([("t", "{}", "A")], msgs=None)
        assert len(results) == 1
        assert results[0].is_ok()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
