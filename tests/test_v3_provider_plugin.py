"""v3 Plugin 测试

注: v3 的 container / lifecycle / pipeline / provider / errors / builtin_plugins
为未接线设施(生产代码零引用, 仅有自引用测试), 已在死代码清理中移除。
events 与 plugin 由 core/metrics、core/events 等生产路径使用, 保留。
"""
import unittest

from fr_cli.v3.core.plugin import (
    Plugin, PluginManager, hook,
    reset_global_plugin_manager,
)


class TestPlugin(unittest.TestCase):
    def setUp(self):
        reset_global_plugin_manager()
        self.pm = PluginManager()

    def tearDown(self):
        self.pm.clear()

    def test_basic_plugin(self):
        p = Plugin()
        p.name = "test"
        self.pm.register(p)
        self.assertIs(self.pm.get("test"), p)

    def test_hook_decorator(self):
        received = []

        class P(Plugin):
            name = "p"
            @hook("test.event")
            def handler(self, event):
                received.append(event.data)

        p = P()
        self.pm.register(p)
        # 手动触发 hook(传 mock event)
        from fr_cli.v3.core.events import Event
        for _, _, method in self.pm._hooks["test.event"]:
            method(Event(type="test.event", data={"x": 1}))
        self.assertEqual(received, [{"x": 1}])

    def test_enable_disable(self):
        class P(Plugin):
            name = "p"
        p = P()
        self.pm.register(p, enabled=True)
        self.assertTrue(self.pm.is_enabled("p"))
        self.pm.disable("p")
        self.assertFalse(self.pm.is_enabled("p"))
        self.pm.enable("p")
        self.assertTrue(self.pm.is_enabled("p"))

    def test_unregister(self):
        class P(Plugin):
            name = "p"
        p = P()
        self.pm.register(p)
        self.assertTrue(self.pm.unregister("p"))
        self.assertIsNone(self.pm.get("p"))

    def test_setup_teardown(self):
        setup_called = []
        teardown_called = []
        class P(Plugin):
            name = "p"
            def setup(self):
                setup_called.append(True)
            def teardown(self):
                teardown_called.append(True)
        self.pm.register(P())
        self.assertEqual(setup_called, [True])
        self.pm.unregister("p")
        self.assertEqual(teardown_called, [True])

    def test_hook_priority(self):
        order = []
        class P(Plugin):
            name = "p"
            @hook("test", priority=10)
            def high(self, e):
                order.append("high")
            @hook("test", priority=1)
            def low(self, e):
                order.append("low")
        self.pm.register(P())
        for _, _, method in self.pm._hooks["test"]:
            method(None)
        self.assertEqual(order, ["high", "low"])

    def test_event_bus_binding(self):
        from fr_cli.v3.core.events import EventBus
        EventBus.reset()
        bus = EventBus.instance()

        received = []
        class P(Plugin):
            name = "p"
            @hook("tool.invoked")
            def handler(self, e):
                received.append(e.data)
        self.pm.set_event_bus(bus)
        self.pm.register(P())

        bus.emit("tool.invoked", {"name": "x"})
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["name"], "x")

        EventBus.reset()

    def test_plugin_disabled_no_callback(self):
        from fr_cli.v3.core.events import EventBus
        EventBus.reset()
        bus = EventBus.instance()
        received = []
        class P(Plugin):
            name = "p"
            @hook("tool.invoked")
            def handler(self, e):
                received.append(e.data)
        self.pm.set_event_bus(bus)
        self.pm.register(P(), enabled=False)
        bus.emit("tool.invoked", {"name": "x"})
        self.assertEqual(received, [])
        EventBus.reset()

    def test_list_plugins(self):
        class P(Plugin):
            name = "p1"
        self.pm.register(P())
        plugins = self.pm.list_plugins()
        self.assertEqual(len(plugins), 1)

    def test_list_hooks(self):
        class P(Plugin):
            name = "p"
            @hook("a")
            def h1(self, e): pass
            @hook("a")
            def h2(self, e): pass
            @hook("b")
            def h3(self, e): pass
        self.pm.register(P())
        hooks = self.pm.list_hooks()
        self.assertEqual(len(hooks["a"]), 2)
        self.assertEqual(len(hooks["b"]), 1)


if __name__ == "__main__":
    unittest.main()
