"""v3 Lifecycle + Errors 测试"""
import unittest
from unittest.mock import patch

from fr_cli.v3.core.lifecycle import Lifecycle, LifecyclePhase, App
from fr_cli.v3.core.errors import (
    FrCliError, LLMError, LLMTimeoutError, ToolNotFoundError,
    ValidationError, NetworkError, ErrorAggregator,
    to_frcli_error, collect_errors,
)


class TestLifecycle(unittest.TestCase):
    def test_phases(self):
        lc = Lifecycle("test")
        self.assertEqual(lc.phase, LifecyclePhase.NEW)

        hooks_called = []
        lc.on_starting(lambda: hooks_called.append("starting"))
        lc.on_started(lambda: hooks_called.append("started"))
        lc.on_stopping(lambda: hooks_called.append("stopping"))
        lc.on_stopped(lambda: hooks_called.append("stopped"))

        lc.start()
        self.assertEqual(lc.phase, LifecyclePhase.STARTED)
        self.assertIn("starting", hooks_called)
        self.assertIn("started", hooks_called)

        lc.stop()
        self.assertEqual(lc.phase, LifecyclePhase.STOPPED)
        self.assertIn("stopping", hooks_called)
        self.assertIn("stopped", hooks_called)

    def test_priority(self):
        lc = Lifecycle("p")
        order = []
        lc.on_started(lambda: order.append("low"), priority=1)
        lc.on_started(lambda: order.append("high"), priority=10)
        lc.start()
        self.assertEqual(order, ["high", "low"])

    def test_is_running(self):
        lc = Lifecycle("r")
        self.assertFalse(lc.is_running)
        lc.start()
        self.assertTrue(lc.is_running)
        lc.stop()
        self.assertFalse(lc.is_running)

    def test_double_start(self):
        lc = Lifecycle("d")
        lc.start()
        # 第二次 start 应该 warn 但不报错
        lc.start()
        self.assertEqual(lc.phase, LifecyclePhase.STARTED)

    def test_stop_without_start(self):
        lc = Lifecycle("n")
        # 没 start 就 stop 应该 warn 不报错
        lc.stop()
        self.assertEqual(lc.phase, LifecyclePhase.NEW)

    def test_hook_exception(self):
        lc = Lifecycle("h")
        def bad():
            raise RuntimeError("boom")
        lc.on_started(bad)
        # 应该捕获不抛
        lc.start()
        self.assertEqual(lc.phase, LifecyclePhase.STARTED)

    def test_on_stop_callback(self):
        lc = Lifecycle("c")
        cb_called = []
        lc.on_stop(lambda: cb_called.append(1))
        lc.start()
        lc.stop()
        self.assertEqual(cb_called, [1])

    def test_wait_stop(self):
        import threading
        lc = Lifecycle("w")
        lc.start()

        def stop_after():
            import time
            time.sleep(0.1)
            lc.stop()

        threading.Thread(target=stop_after, daemon=True).start()
        # wait 0.5s 足够
        self.assertTrue(lc.wait_stop(timeout=2.0))


class TestApp(unittest.TestCase):
    def test_init(self):
        app = App("test_app")
        self.assertEqual(app.name, "test_app")
        self.assertIsNotNone(app.lifecycle)
        self.assertIsNotNone(app.container)

    def test_context_manager(self):
        with App("ctx") as app:
            app.lifecycle.start()
            self.assertTrue(app.lifecycle.is_running)
        self.assertFalse(app.lifecycle.is_running)

    def test_state_compat(self):
        with patch("fr_cli.core.core.AppState") as mock_state:
            mock_state.return_value = "fake_state"
            app = App("state_test")
            self.assertEqual(app.state, "fake_state")


class TestErrors(unittest.TestCase):
    def test_basic(self):
        e = FrCliError("test message", code="TST", data={"k": "v"})
        self.assertEqual(e.message, "test message")
        self.assertEqual(e.code, "TST")
        self.assertEqual(e.data["k"], "v")

    def test_to_dict(self):
        e = FrCliError("test", code="X")
        d = e.to_dict()
        self.assertEqual(d["type"], "FrCliError")
        self.assertEqual(d["code"], "X")
        self.assertEqual(d["severity"], "error")

    def test_subclass(self):
        e = LLMTimeoutError("timeout")
        self.assertIsInstance(e, LLMError)
        self.assertIsInstance(e, FrCliError)
        self.assertEqual(e.severity, "warning")

    def test_tool_not_found(self):
        e = ToolNotFoundError("my_tool")
        self.assertIn("my_tool", e.message)
        self.assertEqual(e.severity, "error")

    def test_validation_error(self):
        e = ValidationError("bad arg")
        self.assertIsInstance(e, FrCliError)

    def test_network_error(self):
        e = NetworkError("conn refused")
        self.assertEqual(e.severity, "warning")

    def test_to_frcli_error_passthrough(self):
        orig = LLMError("already frcli")
        converted = to_frcli_error(orig)
        self.assertIs(converted, orig)

    def test_to_frcli_error_from_exception(self):
        orig = ValueError("value error")
        converted = to_frcli_error(orig, source="test")
        self.assertIsInstance(converted, FrCliError)
        self.assertEqual(converted.source, "test")
        self.assertIs(converted._cause, orig)

    def test_error_aggregator(self):
        agg = ErrorAggregator()
        self.assertFalse(agg.has_errors())
        agg.add(ValueError("err1"))
        agg.add(NetworkError("err2"))
        self.assertTrue(agg.has_errors())
        self.assertEqual(len(agg.errors), 2)

    def test_aggregator_to_exception(self):
        agg = ErrorAggregator()
        agg.add(ValueError("err1"))
        agg.add(ValueError("err2"))
        exc = agg.to_exception("test msg")
        self.assertIsInstance(exc, FrCliError)
        self.assertEqual(exc.code, "AGGREGATED")

    def test_aggregator_to_exception_empty(self):
        agg = ErrorAggregator()
        exc = agg.to_exception()
        self.assertIsInstance(exc, FrCliError)

    def test_collect_errors(self):
        from fr_cli.v3.core.errors import FrCliError
        def good():
            return 42
        def bad():
            raise RuntimeError("oops")
        results, errors = collect_errors(good, bad, good)
        # bad 抛错 → 进 errors,不进 results
        self.assertEqual(results, [42, 42])
        self.assertEqual(len(errors), 1)
        # 收集时被 to_frcli_error 包装
        self.assertIsInstance(errors[0], FrCliError)
        self.assertIn("oops", str(errors[0]))

    def test_collect_errors_reraise(self):
        def bad():
            raise ValueError("oops")
        with self.assertRaises(Exception):
            collect_errors(bad, reraise=True)

    def test_repr(self):
        e = LLMError("test", code="MY_CODE")
        r = repr(e)
        self.assertIn("LLMError", r)
        self.assertIn("test", r)
        self.assertIn("MY_CODE", r)


if __name__ == "__main__":
    unittest.main()
