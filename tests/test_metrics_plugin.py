"""
MetricsPlugin 测试

覆盖:
- Counter 增/读/标签
- Histogram 观察 / 分位数估算
- Timer 增 / 摘要(count/total/min/max/avg)
- Gauge 增/减/设
- 自动从事件总线收 11 类事件
- 三种导出格式:text(Prometheus)/ json / summary
- install_metrics() 幂等
- Web Console /api/metrics 端点
- reset()
- 线程安全
"""
import os
import sys
import json
import socket
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from fr_cli.v3.core.events import EventBus
from fr_cli.v3.core.plugin import PluginManager
from fr_cli.core.events import dispatch_event, V2Events
from fr_cli.core.metrics import (
    MetricsPlugin, install_metrics, get_metrics,
    reset_metrics_for_testing,
)


@pytest.fixture(autouse=True)
def reset_state():
    """每个测试重置 bus + metrics"""
    EventBus.reset()
    bus = EventBus.instance()
    bus.clear()
    reset_metrics_for_testing()
    yield
    bus.clear()
    reset_metrics_for_testing()


# ==================== Counter ====================

class TestCounter:
    def test_inc_default(self):
        m = MetricsPlugin()
        m.counter_inc("foo")
        m.counter_inc("foo")
        m.counter_inc("foo")
        assert m.counter_get("foo") == 3

    def test_inc_with_value(self):
        m = MetricsPlugin()
        m.counter_inc("foo", value=10)
        assert m.counter_get("foo") == 10

    def test_inc_with_labels(self):
        m = MetricsPlugin()
        m.counter_inc("foo", tool="x", user="alice")
        m.counter_inc("foo", tool="x", user="bob")
        m.counter_inc("foo", tool="y", user="alice")
        assert m.counter_get("foo", tool="x", user="alice") == 1
        assert m.counter_get("foo", tool="x", user="bob") == 1
        assert m.counter_get("foo", tool="y", user="alice") == 1

    def test_missing_returns_zero(self):
        m = MetricsPlugin()
        assert m.counter_get("never_set") == 0


# ==================== Histogram ====================

class TestHistogram:
    def test_observe_basic(self):
        m = MetricsPlugin()
        m.histogram_observe("rt", 0.5)
        m.histogram_observe("rt", 1.5)
        m.histogram_observe("rt", 5.0)

        snap = m.metrics_json()
        h = snap["histograms"]["rt"]
        assert h["count"] == 3
        assert h["sum"] == 7.0

    def test_percentile_estimate(self):
        m = MetricsPlugin()
        # 加 100 个 1.0 的值
        for _ in range(100):
            m.histogram_observe("rt", 1.0)
        # 加 100 个 5.0
        for _ in range(100):
            m.histogram_observe("rt", 5.0)

        # p50 应在 1.0 附近(100/200=0.5 落在第一个非空桶)
        p50 = m.histogram_percentile("rt", 0.5)
        # p95 应在 5.0(190/200=0.95)
        p95 = m.histogram_percentile("rt", 0.95)
        assert p50 == 1.0
        assert p95 == 5.0

    def test_percentile_empty(self):
        m = MetricsPlugin()
        assert m.histogram_percentile("empty", 0.5) is None


# ==================== Timer ====================

class TestTimer:
    def test_observe(self):
        m = MetricsPlugin()
        m.timer_observe("op", 0.1)
        m.timer_observe("op", 0.5)
        m.timer_observe("op", 1.0)

        s = m.timer_summary("op")
        assert s["count"] == 3
        assert s["min"] == 0.1
        assert s["max"] == 1.0
        assert s["total"] == 1.6
        assert abs(s["avg"] - 0.533333) < 0.001

    def test_summary_empty(self):
        m = MetricsPlugin()
        assert m.timer_summary("never") is None


# ==================== Gauge ====================

class TestGauge:
    def test_set(self):
        m = MetricsPlugin()
        m.gauge_set("active_users", 42)
        assert m.gauge_get("active_users") == 42

    def test_inc_dec(self):
        m = MetricsPlugin()
        m.gauge_inc("x", 5)
        m.gauge_inc("x", 3)
        assert m.gauge_get("x") == 8
        m.gauge_dec("x", 3)
        assert m.gauge_get("x") == 5

    def test_get_missing(self):
        m = MetricsPlugin()
        assert m.gauge_get("never") is None


# ==================== 事件钩子 ====================

class TestEventHooks:
    def test_tool_events(self):
        m = MetricsPlugin()
        EventBus.instance().on("tool.invoked", m.on_tool_invoked)
        EventBus.instance().on("tool.succeeded", m.on_tool_succeeded)
        EventBus.instance().on("tool.failed", m.on_tool_failed)

        EventBus.instance().emit("tool.invoked", data={"name": "read_file"})
        EventBus.instance().emit("tool.succeeded", data={"name": "read_file"})
        EventBus.instance().emit("tool.failed", data={"name": "write_file"})

        assert m.counter_get("tool.invoked", name="read_file") == 1
        assert m.counter_get("tool.succeeded", name="read_file") == 1
        assert m.counter_get("tool.failed", name="write_file") == 1

    def test_llm_response_time_histogram(self):
        m = MetricsPlugin()
        EventBus.instance().on("llm.responded", m.on_llm_responded)

        EventBus.instance().emit("llm.responded", data={
            "model": "glm-4-flash",
            "response_time": 1.5,
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        })

        h = m.metrics_json()["histograms"]["llm.response_time"]
        assert h["count"] == 1
        assert h["sum"] == 1.5

        g = m.metrics_json()["gauges"]
        assert g["llm.tokens.total"] == 150
        assert g["llm.tokens.prompt"] == 100
        assert g["llm.tokens.completion"] == 50

    def test_agent_events(self):
        m = MetricsPlugin()
        EventBus.instance().on("agent.invoked", m.on_agent_invoked)
        EventBus.instance().on("agent.responded", m.on_agent_responded)
        EventBus.instance().on("agent.failed", m.on_agent_failed)

        EventBus.instance().emit("agent.invoked", data={"name": "coder"})
        EventBus.instance().emit("agent.responded", data={"name": "coder"})
        EventBus.instance().emit("agent.failed", data={"name": "reviewer"})

        assert m.counter_get("agent.invoked", name="coder") == 1
        assert m.counter_get("agent.responded", name="coder") == 1
        assert m.counter_get("agent.failed", name="reviewer") == 1


# ==================== 导出格式 ====================

class TestExportFormats:
    def test_metrics_text_prometheus_style(self):
        m = MetricsPlugin()
        m.counter_inc("foo")
        m.counter_inc("bar", tool="x")
        m.histogram_observe("rt", 0.5)
        m.timer_observe("op", 0.1)
        m.gauge_set("g", 42)

        text = m.metrics_text()
        assert "# TYPE foo counter" in text
        assert "foo 1" in text
        assert 'bar{tool="x"} 1' in text
        assert "# TYPE rt histogram" in text
        assert "rt_bucket" in text
        assert "# TYPE op summary" in text
        assert "# TYPE g gauge" in text
        assert "g 42" in text
        assert "# meta" in text
        assert "started_at:" in text

    def test_metrics_json_structure(self):
        m = MetricsPlugin()
        m.counter_inc("foo")
        m.histogram_observe("rt", 1.0)

        snap = m.metrics_json()
        assert "counters" in snap
        assert "histograms" in snap
        assert "timers" in snap
        assert "gauges" in snap
        assert "meta" in snap
        assert "foo" in snap["counters"]
        assert "rt" in snap["histograms"]
        # 分位数字段
        assert "p50" in snap["histograms"]["rt"]["percentiles"]
        assert "p95" in snap["histograms"]["rt"]["percentiles"]
        assert "p99" in snap["histograms"]["rt"]["percentiles"]

    def test_metrics_summary_human_readable(self):
        m = MetricsPlugin()
        m.counter_inc("foo")
        m.histogram_observe("rt", 1.0)
        m.timer_observe("op", 0.1)

        s = m.metrics_summary()
        assert "📊 Metrics Summary" in s
        assert "Counters:" in s
        assert "Histograms:" in s
        assert "Timers:" in s
        assert "foo" in s
        assert "rt" in s
        assert "op" in s


# ==================== Reset & 安装 ====================

class TestInstall:
    def test_install_metrics_returns_plugin(self):
        pm = PluginManager()
        p = install_metrics(plugin_manager=pm)
        assert p is not None
        assert p.name == "metrics"

    def test_install_is_idempotent(self):
        pm = PluginManager()
        p1 = install_metrics(plugin_manager=pm)
        p2 = install_metrics(plugin_manager=pm)
        assert p1 is p2  # 同一个实例

    def test_get_metrics_returns_installed(self):
        pm = PluginManager()
        install_metrics(plugin_manager=pm)
        g = get_metrics()
        assert g is not None
        assert g.name == "metrics"

    def test_reset_clears_metrics(self):
        m = MetricsPlugin()
        m.counter_inc("foo")
        m.histogram_observe("rt", 1.0)
        m.reset()
        assert m.counter_get("foo") == 0
        assert m.metrics_json()["histograms"] == {}


# ==================== 集成:v2 dispatch → metrics ====================

class TestIntegrationV2Dispatch:
    def test_v2_events_increment_metrics(self):
        from fr_cli.v3.core.plugin import PluginManager
        pm = PluginManager()
        install_metrics(plugin_manager=pm)

        # 用 v2 API dispatch
        dispatch_event(V2Events.TOOL_INVOKED, data={"name": "read_file"}, source="command_executor")
        dispatch_event(V2Events.LLM_RESPONDED, data={
            "model": "x",
            "response_time": 2.0,
            "usage": {"prompt_tokens": 50, "completion_tokens": 30, "total_tokens": 80},
        }, source="chat")

        m = get_metrics()
        assert m.counter_get("tool.invoked", name="read_file", source="command_executor") == 1
        h = m.metrics_json()["histograms"]["llm.response_time"]
        assert h["count"] == 1
        assert m.metrics_json()["gauges"]["llm.tokens.total"] == 80


# ==================== 线程安全 ====================

class TestThreadSafety:
    def test_concurrent_counter_inc(self):
        m = MetricsPlugin()
        def worker():
            for _ in range(1000):
                m.counter_inc("foo")

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads: t.start()
        for t in threads: t.join()
        # 4 * 1000 = 4000
        assert m.counter_get("foo") == 4000


# ==================== Web Console /api/metrics ====================

class TestConsoleEndpoint:
    def test_metrics_endpoint_json(self):
        from fr_cli.web.console import start_console, stop_console
        from fr_cli.v3.core.plugin import PluginManager

        # 安装 metrics 到全局 bus
        pm = PluginManager()
        install_metrics(plugin_manager=pm)

        # 制造一些事件
        dispatch_event(V2Events.TOOL_INVOKED, data={"name": "test"}, source="console-test")

        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

        res = start_console(host="127.0.0.1", port=port, token="t", open_browser=False)
        try:
            assert res["ok"]
            import urllib.request
            url = f"http://127.0.0.1:{port}/api/metrics?token=t"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as r:
                body = json.loads(r.read())
            assert body["ok"] is True
            assert "data" in body
            # 应该看到 tool.invoked 计数器
            assert "tool.invoked" in body["data"]["counters"]
        finally:
            stop_console()

    def test_metrics_endpoint_prometheus(self):
        from fr_cli.web.console import start_console, stop_console
        from fr_cli.v3.core.plugin import PluginManager

        pm = PluginManager()
        install_metrics(plugin_manager=pm)

        # 制造一些指标,这样 prometheus 输出才有 # TYPE 行
        from fr_cli.core.metrics import get_metrics
        m = get_metrics()
        m.counter_inc("foo.bar")

        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

        res = start_console(host="127.0.0.1", port=port, token="t", open_browser=False)
        try:
            assert res["ok"]
            import urllib.request
            url = f"http://127.0.0.1:{port}/api/metrics?format=prom&token=t"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as r:
                body = r.read().decode("utf-8")
            assert "# TYPE foo.bar counter" in body
            assert "foo.bar 1" in body
        finally:
            stop_console()
