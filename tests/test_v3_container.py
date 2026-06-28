"""v3 Container 测试"""
import unittest
from fr_cli.v3.core.container import Container


class ContainerTest(unittest.TestCase):
    def setUp(self):
        self.c = Container()

    def test_register_and_get(self):
        self.c.register("config", instance={"key": "value"})
        self.assertEqual(self.c.get("config"), {"key": "value"})

    def test_register_with_factory(self):
        self.c.register("counter", lambda: 42)
        self.assertEqual(self.c.get("counter"), 42)

    def test_singleton_scope(self):
        call_count = [0]
        def factory():
            call_count[0] += 1
            return {"instance": call_count[0]}
        self.c.register("singleton", factory, scope="singleton")
        a = self.c.get("singleton")
        b = self.c.get("singleton")
        self.assertEqual(a, b)
        self.assertEqual(call_count[0], 1)

    def test_transient_scope(self):
        call_count = [0]
        def factory():
            call_count[0] += 1
            return {"instance": call_count[0]}
        self.c.register("transient", factory, scope="transient")
        a = self.c.get("transient")
        b = self.c.get("transient")
        self.assertNotEqual(a, b)
        self.assertEqual(call_count[0], 2)

    def test_get_default(self):
        self.assertIsNone(self.c.get("missing", default=None))
        self.assertEqual(self.c.get("missing", default="default"), "default")

    def test_get_missing_raises(self):
        with self.assertRaises(KeyError):
            self.c.get("missing")

    def test_has(self):
        self.c.register("x", instance=1)
        self.assertTrue(self.c.has("x"))
        self.assertFalse(self.c.has("y"))

    def test_remove(self):
        self.c.register("x", instance=1)
        self.assertTrue(self.c.remove("x"))
        self.assertFalse(self.c.has("x"))

    def test_keys(self):
        self.c.register("a", instance=1)
        self.c.register("b", instance=2)
        keys = self.c.keys()
        self.assertIn("a", keys)
        self.assertIn("b", keys)

    def test_clear(self):
        self.c.register("a", instance=1)
        self.c.clear()
        self.assertEqual(self.c.keys(), [])

    def test_override(self):
        self.c.register("x", instance=1)
        self.c.register("x", instance=2, override=True)
        self.assertEqual(self.c.get("x"), 2)

    def test_no_override(self):
        self.c.register("x", instance=1)
        self.c.register("x", instance=2, override=False)
        self.assertEqual(self.c.get("x"), 1)

    def test_register_class(self):
        class MyService:
            pass
        self.c.register_class(MyService, scope="transient")
        s = self.c.get(MyService)
        self.assertIsInstance(s, MyService)

    def test_register_instance(self):
        class MyService:
            pass
        inst = MyService()
        self.c.register_instance(inst)
        self.assertIs(self.c.get(MyService), inst)

    def test_name_param(self):
        self.c.register("db", instance="primary", name="main")
        self.c.register("db", instance="replica", name="replica")
        self.assertEqual(self.c.get("db", name="main"), "primary")
        self.assertEqual(self.c.get("db", name="replica"), "replica")

    def test_parent_container(self):
        parent = Container()
        parent.register("from_parent", instance="parent_value")
        child = Container(parent=parent)
        self.assertEqual(child.get("from_parent"), "parent_value")

    def test_inject_decorator(self):
        self.c.register("vfs", instance={"vfs": True})
        self.c.register("config", instance={"cfg": True})

        @self.c.inject
        def my_func(vfs, config, extra="default"):
            return f"vfs={vfs}, config={config}, extra={extra}"

        result = my_func()
        self.assertIn("vfs={'vfs': True}", result)
        self.assertIn("config={'cfg': True}", result)
        self.assertIn("extra=default", result)

    def test_inject_with_args(self):
        self.c.register("dep", instance="d")

        @self.c.inject
        def my_func(dep, explicit="x"):
            return f"{dep}-{explicit}"

        result = my_func(explicit="y")
        self.assertEqual(result, "d-y")

    def test_contains(self):
        self.c.register("x", instance=1)
        self.assertIn("x", self.c)
        self.assertNotIn("y", self.c)

    def test_repr(self):
        self.c.register("x", instance=1)
        self.assertIn("Container", repr(self.c))


class TestGlobalContainer(unittest.TestCase):
    def test_singleton(self):
        from fr_cli.v3.core.container import (
            global_container, reset_global_container
        )
        reset_global_container()
        c1 = global_container()
        c2 = global_container()
        self.assertIs(c1, c2)
        reset_global_container()


if __name__ == "__main__":
    unittest.main()
