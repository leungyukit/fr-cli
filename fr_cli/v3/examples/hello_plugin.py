"""
v3 Example Plugin —— 演示如何写一个 fr-cli 插件

放到 ~/.fr_cli/plugins/ 目录,或在 v3 init 时手动 register。

用法:
    from fr_cli.v3.examples.hello_plugin import HelloPlugin
    global_plugin_manager().register(HelloPlugin())
"""
from fr_cli.v3.core.plugin import Plugin, hook


class HelloPlugin(Plugin):
    """示例插件:在工具调用前后打印问候"""

    name = "hello-plugin"
    version = "1.0.0"
    description = "演示插件:在工具调用时打印 Hello"

    def __init__(self, greeting: str = "Hello"):
        self.greeting = greeting
        self.invocation_count = 0

    @hook("tool.invoked", priority=50)
    def greet(self, event):
        self.invocation_count += 1
        tool_name = event.data.get("name", "?")
        print(f"[{self.name}] {self.greeting}! Tool '{tool_name}' invoked "
              f"(#{self.invocation_count})")

    @hook("tool.failed", priority=50)
    def on_failure(self, event):
        print(f"[{self.name}] Oh no, tool '{event.data.get('name')}' failed: "
              f"{event.data.get('error')}")

    @hook("app.started", priority=10)
    def on_start(self, event):
        print(f"[{self.name}] App started! {self.greeting}, world!")

    @hook("app.stopped", priority=10)
    def on_stop(self, event):
        print(f"[{self.name}] App stopped. Total invocations: {self.invocation_count}")


class CounterPlugin(Plugin):
    """示例插件:统计每个工具被调用次数"""

    name = "counter"
    version = "1.0.0"
    description = "工具调用计数器"

    def __init__(self):
        self.counts = {}

    @hook("tool.invoked")
    def count(self, event):
        name = event.data.get("name", "unknown")
        self.counts[name] = self.counts.get(name, 0) + 1

    @hook("app.stopped")
    def report(self, event):
        if self.counts:
            lines = ["📊 工具调用统计:"]
            for name, count in sorted(self.counts.items()):
                lines.append(f"  • {name}: {count}")
            print("\n".join(lines))
