"""v3 Provider / Plugin / Pipeline 测试"""
import asyncio
import unittest

from fr_cli.v3.core.provider import (
    BaseProvider, ProviderRequest, ProviderResponse,
    LLMRequest, ToolRequest, ResourceRequest, PromptRequest,
    ProviderRegistry, global_registry, reset_global_registry,
)
from fr_cli.v3.core.plugin import (
    Plugin, PluginManager, hook,
    LoggingPlugin, MetricsPlugin,
    reset_global_plugin_manager,
)
from fr_cli.v3.core.pipeline import (
    Chunk, Pipeline, PipelineManager,
    pipeline, stream_to_callback, collect_stream,
    global_pipeline_manager, reset_global_pipeline_manager,
)


# ---------------- Provider ----------------

class TestProviderRequests(unittest.TestCase):
    def test_llm_request(self):
        req = LLMRequest(messages=[{"role": "user", "content": "hi"}], model="x")
        self.assertEqual(req.type, "llm")
        self.assertEqual(req.messages[0]["content"], "hi")
        self.assertEqual(req.temperature, 0.7)

    def test_tool_request(self):
        req = ToolRequest(tool_name="search_web", arguments={"q": "x"})
        self.assertEqual(req.type, "tool")
        self.assertEqual(req.tool_name, "search_web")

    def test_resource_request(self):
        req = ResourceRequest(uri="file:///data")
        self.assertEqual(req.uri, "file:///data")

    def test_prompt_request(self):
        req = PromptRequest(prompt_name="summarize", arguments={"text": "x"})
        self.assertEqual(req.prompt_name, "summarize")

    def test_provider_response(self):
        r = ProviderResponse(ok=True, data="x", metadata={"k": "v"})
        self.assertTrue(r.ok)
        d = r.to_dict()
        self.assertEqual(d["data"], "x")


class TestBaseProvider(unittest.TestCase):
    def test_default_capabilities(self):
        p = BaseProvider()
        caps = p.capabilities()
        self.assertIn("name", caps)

    def test_default_stream(self):
        # BaseProvider.invoke 默认抛 NotImplementedError
        # stream 会冒泡上来
        async def run():
            p = BaseProvider()
            async for _ in p.stream(ProviderRequest()):
                pass
        with self.assertRaises(NotImplementedError):
            asyncio.run(run())


class TestProviderRegistry(unittest.TestCase):
    def setUp(self):
        reset_global_registry()
        self.reg = ProviderRegistry()

    def tearDown(self):
        self.reg.clear()

    def test_register_and_get(self):
        class MyProvider(BaseProvider):
            name = "my"
            type = "test"
            async def invoke(self, request):
                return ProviderResponse(ok=True, data="ok")
        p = MyProvider()
        self.reg.register(p)
        self.assertIs(self.reg.get("my"), p)

    def test_by_type(self):
        class A(BaseProvider):
            name = "a"; type = "tool"
            async def invoke(self, r): return ProviderResponse()
        class B(BaseProvider):
            name = "b"; type = "tool"
            async def invoke(self, r): return ProviderResponse()
        self.reg.register(A())
        self.reg.register(B())
        tools = self.reg.by_type("tool")
        self.assertEqual(set(tools.keys()), {"a", "b"})

    def test_unregister(self):
        class A(BaseProvider):
            name = "a"; type = "x"
            async def invoke(self, r): return ProviderResponse()
        self.reg.register(A())
        self.assertTrue(self.reg.unregister("a"))
        self.assertIsNone(self.reg.get("a"))

    def test_names(self):
        class A(BaseProvider):
            name = "a"; type = "x"
            async def invoke(self, r): return ProviderResponse()
        self.reg.register(A())
        self.assertIn("a", self.reg.names())

    def test_no_override(self):
        class A(BaseProvider):
            name = "a"; type = "x"
            async def invoke(self, r): return ProviderResponse(data="first")
        class B(BaseProvider):
            name = "a"; type = "x"
            async def invoke(self, r): return ProviderResponse(data="second")
        first = A()
        second = B()
        self.reg.register(first)
        self.reg.register(second, override=False)
        self.assertIs(self.reg.get("a"), first)

    def test_global_registry_singleton(self):
        reset_global_registry()
        c1 = global_registry()
        c2 = global_registry()
        self.assertIs(c1, c2)


# ---------------- Plugin ----------------

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


class TestBuiltinPlugins(unittest.TestCase):
    def test_logging_plugin(self):
        p = LoggingPlugin()
        self.assertEqual(p.name, "logging")

    def test_metrics_plugin(self):
        from fr_cli.v3.core.events import EventBus
        EventBus.reset()
        bus = EventBus.instance()
        pm = PluginManager()
        pm.set_event_bus(bus)

        p = MetricsPlugin()
        pm.register(p)

        bus.emit("tool.invoked", {"name": "a"})
        bus.emit("tool.invoked", {"name": "b"})
        bus.emit("tool.invoked", {"name": "a"})

        self.assertEqual(p.counters["tool.a.invoked"], 2)
        self.assertEqual(p.counters["tool.b.invoked"], 1)
        EventBus.reset()


# ---------------- Pipeline ----------------

class TestPipeline(unittest.TestCase):
    def setUp(self):
        reset_global_pipeline_manager()
        self.pm = PipelineManager()

    def tearDown(self):
        self.pm = None

    def test_register_and_run(self):
        def add(a, b):
            return a + b
        self.pm.register("add", add)
        result = asyncio.run(self.pm.run("add", 1, 2))
        self.assertEqual(result, 3)

    def test_async_function(self):
        async def afn(x):
            return x * 2
        self.pm.register("afn", afn)
        result = asyncio.run(self.pm.run("afn", 5))
        self.assertEqual(result, 10)

    def test_get_pipeline(self):
        def f():
            return 1
        self.pm.register("f", f)
        p = self.pm.get("f")
        self.assertIsInstance(p, Pipeline)
        self.assertEqual(p.name, "f")

    def test_run_unknown(self):
        with self.assertRaises(ValueError):
            asyncio.run(self.pm.run("nope"))

    def test_pipeline_decorator(self):
        @pipeline("dec.fn")
        def fn(x):
            return x + 1

        # @pipeline 装饰器注册到全局 manager,不是 self.pm
        gpm = global_pipeline_manager()
        self.assertEqual(asyncio.run(gpm.run("dec.fn", 10)), 11)

    def test_stats(self):
        def f():
            return 1
        self.pm.register("f", f)
        asyncio.run(self.pm.run("f"))
        asyncio.run(self.pm.run("f"))
        self.assertEqual(self.pm.stats()["f"], 2)

    def test_timeout(self):
        def slow():
            import time
            time.sleep(2)
            return "done"
        self.pm.register("slow", slow, timeout=0.1)
        with self.assertRaises(Exception):  # TimeoutError
            asyncio.run(self.pm.run("slow"))

    def test_chunk(self):
        c = Chunk(data="x", index=0)
        self.assertEqual(c.data, "x")
        self.assertEqual(c.index, 0)
        self.assertFalse(c.is_final)


class TestStreamHelpers(unittest.TestCase):
    def test_stream_to_callback(self):
        async def source():
            for i in range(3):
                yield f"chunk-{i}"

        received = []
        done = []
        async def run():
            await stream_to_callback(
                source(),
                on_chunk=lambda c: received.append(c.data),
                on_done=lambda f: done.append(f.data if f else None),
            )
        asyncio.run(run())
        self.assertEqual(received, ["chunk-0", "chunk-1", "chunk-2"])
        self.assertEqual(done, ["chunk-2"])

    def test_stream_max_chunks(self):
        async def source():
            for i in range(10):
                yield f"chunk-{i}"
        received = []
        async def run():
            await stream_to_callback(source(), on_chunk=lambda c: received.append(c.data),
                                    max_chunks=3)
        asyncio.run(run())
        self.assertEqual(len(received), 3)

    def test_collect_stream(self):
        async def source():
            for i in range(5):
                yield i
        result = asyncio.run(collect_stream(source()))
        self.assertEqual(result, [0, 1, 2, 3, 4])


if __name__ == "__main__":
    unittest.main()
