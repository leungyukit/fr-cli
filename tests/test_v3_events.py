"""v3 EventBus 测试"""
import unittest
from fr_cli.v3.core.events import Event, EventBus, Events, emit, on


class TestEvent(unittest.TestCase):
    def test_basic(self):
        e = Event("test.event", {"k": "v"})
        self.assertEqual(e.type, "test.event")
        self.assertEqual(e.data["k"], "v")
        self.assertIsNone(e.source)

    def test_stop_propagation(self):
        e = Event("test")
        e.stop_propagation()
        self.assertTrue(e._propagated)


class TestEventBus(unittest.TestCase):
    def setUp(self):
        EventBus.reset()
        self.bus = EventBus.instance()

    def tearDown(self):
        EventBus.reset()

    def test_on_and_emit(self):
        received = []
        self.bus.on("test", lambda e: received.append(e.data["x"]))
        self.bus.emit("test", {"x": 1})
        self.bus.emit("test", {"x": 2})
        self.assertEqual(received, [1, 2])

    def test_priority(self):
        order = []
        self.bus.on("test", lambda e: order.append("low"), priority=1)
        self.bus.on("test", lambda e: order.append("high"), priority=10)
        self.bus.on("test", lambda e: order.append("mid"), priority=5)
        self.bus.emit("test")
        self.assertEqual(order, ["high", "mid", "low"])

    def test_wildcard(self):
        received = []
        self.bus.on("*", lambda e: received.append(e.type))
        self.bus.emit("a")
        self.bus.emit("b")
        self.assertEqual(received, ["a", "b"])

    def test_off(self):
        received = []
        handler = lambda e: received.append(1)
        self.bus.on("test", handler)
        self.assertTrue(self.bus.off("test", handler))
        self.bus.emit("test")
        self.assertEqual(received, [])

    def test_once(self):
        received = []
        self.bus.once("test", lambda e: received.append(e.data))
        self.bus.emit("test", {"x": 1})
        self.bus.emit("test", {"x": 2})
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["x"], 1)

    def test_handler_exception(self):
        def bad(e):
            raise RuntimeError("boom")
        received = []
        self.bus.on("test", bad)
        self.bus.on("test", lambda e: received.append("ok"))
        self.bus.emit("test")
        # 第一个 handler 抛错不影响第二个
        self.assertEqual(received, ["ok"])

    def test_stop_propagation(self):
        order = []
        def first(e):
            order.append("first")
            e.stop_propagation()
        def second(e):
            order.append("second")
        self.bus.on("test", first, priority=10)
        self.bus.on("test", second, priority=5)
        self.bus.emit("test")
        self.assertEqual(order, ["first"])

    def test_listener_count(self):
        self.bus.on("a", lambda e: None)
        self.bus.on("a", lambda e: None)
        self.bus.on("b", lambda e: None)
        self.bus.on("*", lambda e: None)
        self.assertEqual(self.bus.listener_count("a"), 3)  # a + *
        self.assertEqual(self.bus.listener_count(), 4)

    def test_event_types(self):
        self.bus.on("foo", lambda e: None)
        self.bus.on("bar", lambda e: None)
        types = self.bus.event_types()
        self.assertIn("foo", types)
        self.assertIn("bar", types)

    def test_stats(self):
        self.bus.emit("a")
        self.bus.emit("a")
        self.bus.emit("b")
        stats = self.bus.stats()
        self.assertEqual(stats["a"], 2)
        self.assertEqual(stats["b"], 1)

    def test_clear(self):
        self.bus.on("a", lambda e: None)
        self.bus.clear()
        self.assertEqual(self.bus.listener_count(), 0)

    def test_emit_async(self):
        import threading
        import time
        sync_received = []
        async_received = []
        lock = threading.Lock()
        slow_count = [0]

        def slow(e):
            time.sleep(0.02)
            with lock:
                async_received.append(e.data["async_marker"])
                slow_count[0] += 1

        self.bus.on("test", slow)
        self.bus.on("test", lambda e: sync_received.append(e.data["sync_marker"]))

        # async emit:后台执行
        self.bus.emit("test", {"async_marker": 1, "sync_marker": "s1"}, sync=False)
        # sync emit:立即执行(也会跑 slow,但同步)
        self.bus.emit("test", {"async_marker": 2, "sync_marker": "s2"})

        # sync emit 中的 sync handler 一定执行
        self.assertIn("s2", sync_received)
        # 等两条 slow 都跑完
        deadline = time.time() + 3
        while time.time() < deadline:
            with lock:
                if slow_count[0] >= 2:
                    break
            time.sleep(0.02)
        # async_received 含 1 和 2
        self.assertIn(1, async_received)
        self.assertIn(2, async_received)

        self.bus.off("test", slow)


class TestConvenience(unittest.TestCase):
    """便捷函数:bus / emit / on"""

    def setUp(self):
        EventBus.reset()

    def tearDown(self):
        EventBus.reset()

    def test_emit(self):
        received = []
        on("test", lambda e: received.append(e.data))
        emit("test", {"x": 1})
        self.assertEqual(received, [{"x": 1}])

    def test_emit_returns_event(self):
        e = emit("test", {"x": 1})
        self.assertIsInstance(e, Event)
        self.assertEqual(e.type, "test")

    def test_events_constants(self):
        self.assertEqual(Events.APP_STARTING, "app.starting")
        self.assertEqual(Events.TOOL_INVOKED, "tool.invoked")
        self.assertEqual(Events.LLM_RESPONDED, "llm.responded")


if __name__ == "__main__":
    unittest.main()
