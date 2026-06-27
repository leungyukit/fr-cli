"""并行工具调用测试"""
import time
import unittest
from unittest.mock import MagicMock

from fr_cli.command.parallel import (
    extract_parallel_calls, _split_calls, remove_parallel_markers,
    ParallelExecutor, DEFAULT_MAX_WORKERS, _clamp_workers,
)


class TestExtract(unittest.TestCase):
    def test_single_call(self):
        text = "看看【并行调用：read_file({\"path\": \"a.md\"})】"
        calls = extract_parallel_calls(text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "read_file")

    def test_multiple_calls(self):
        text = '【并行调用：read_file({"path": "a"}),read_file({"path": "b"})】'
        calls = extract_parallel_calls(text)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0], "read_file")
        self.assertEqual(calls[1][0], "read_file")

    def test_no_parallel(self):
        text = "普通文本没有并行调用"
        calls = extract_parallel_calls(text)
        self.assertEqual(len(calls), 0)

    def test_nested_parens(self):
        text = "【并行调用：search_web({\"query\": \"a (b)\"})】"
        calls = extract_parallel_calls(text)
        self.assertEqual(len(calls), 1)
        self.assertIn("(b)", calls[0][1])

    def test_multiple_blocks(self):
        text = (
            "【并行调用：read_file({\"path\": \"a\"})】\n"
            "中间文本\n"
            "【并行调用：read_file({\"path\": \"b\"}),read_file({\"path\": \"c\"})】"
        )
        calls = extract_parallel_calls(text)
        self.assertEqual(len(calls), 3)


class TestSplit(unittest.TestCase):
    def test_simple(self):
        text = 'a({"x": 1}),b({"y": 2})'
        items = _split_calls(text)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0][0], "a")
        self.assertEqual(items[1][0], "b")

    def test_with_brackets_in_string(self):
        text = 'a({"x": "{a,b}"}),b({})'
        items = _split_calls(text)
        self.assertEqual(len(items), 2)


class TestRemoveMarkers(unittest.TestCase):
    def test_removes_marker(self):
        text = '前文【并行调用：read_file({"path": "a"})】后文'
        cleaned, calls = remove_parallel_markers(text)
        self.assertNotIn("并行调用", cleaned)
        self.assertIn("前文", cleaned)
        self.assertIn("后文", cleaned)
        self.assertEqual(len(calls), 1)


class TestParallelExecution(unittest.TestCase):
    def test_execute_batch_concurrent(self):
        # 模拟 executor
        executor = MagicMock()
        from fr_cli.core.result import Result

        def fake_invoke(tool_name, kwargs, msgs=None, skip_security=False,
                       client=None, model_name=None):
            time.sleep(0.05)  # 模拟耗时
            return Result.ok(f"{tool_name}:{kwargs}")

        executor.invoke_tool = fake_invoke
        executor._parse_tool_kwargs = lambda s: {"arg": s}

        par = ParallelExecutor(executor, max_workers=3)
        calls = [
            ("a", "{}", "marker1"),
            ("b", "{}", "marker2"),
            ("c", "{}", "marker3"),
        ]
        t0 = time.time()
        results, markers = par.execute_batch(calls)
        elapsed = time.time() - t0

        self.assertEqual(len(results), 3)
        # 并发执行应该比串行快(3 个 * 0.05s = 0.15s 串行,<0.15s 并发)
        self.assertLess(elapsed, 0.15)

    def test_execute_batch_with_failure(self):
        executor = MagicMock()
        from fr_cli.core.result import Result

        def fake_invoke(tool_name, kwargs, msgs=None, skip_security=False,
                       client=None, model_name=None):
            if tool_name == "bad":
                return Result.fail("boom")
            return Result.ok(f"ok:{tool_name}")

        executor.invoke_tool = fake_invoke
        executor._parse_tool_kwargs = lambda s: {"arg": s}

        par = ParallelExecutor(executor, max_workers=2)
        calls = [("good", "{}", "m1"), ("bad", "{}", "m2")]
        results, _ = par.execute_batch(calls)
        self.assertEqual(len(results), 2)
        self.assertFalse(results[0].is_fail())
        self.assertTrue(results[1].is_fail())

    def test_execute_batch_empty(self):
        executor = MagicMock()
        par = ParallelExecutor(executor)
        results, markers = par.execute_batch([])
        self.assertEqual(results, [])
        self.assertEqual(markers, [])


class TestClampWorkers(unittest.TestCase):
    def test_normal(self):
        self.assertEqual(_clamp_workers(3), 3)

    def test_too_many(self):
        self.assertEqual(_clamp_workers(100), 10)

    def test_zero(self):
        self.assertEqual(_clamp_workers(0), 1)

    def test_negative(self):
        self.assertEqual(_clamp_workers(-5), 1)


if __name__ == "__main__":
    unittest.main()