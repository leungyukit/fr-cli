"""
测试 UsageTracker / ErrorLedger 接入 v3 EventBus

覆盖:
- UsageTracker.install_listener() 自动从 llm.responded 事件记录用量
- UsageTracker.uninstall_listener() 解除订阅
- 多次 install 幂等
- ErrorLedger 自动从 tool.failed / llm.failed / agent.failed 记录
- 事件格式不规范时跳过,不抛错
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


from fr_cli.v3.core.events import EventBus
from fr_cli.core.events import V2Events, dispatch_event


# ==================== UsageTracker ====================

class TestUsageTrackerListener:
    def setup_method(self):
        """每个测试前清空 bus + 新 tracker"""
        EventBus.reset()
        self.bus = EventBus.instance()
        self.bus.clear()
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.path = self.tmp.name

    def teardown_method(self):
        try:
            os.unlink(self.path)
        except Exception:
            pass

    def test_install_returns_true(self):
        from fr_cli.core.usage import UsageTracker
        t = UsageTracker(path=self.path)
        try:
            assert t.install_listener(bus=self.bus) is True
        finally:
            t.uninstall_listener()

    def test_llm_responded_auto_records(self):
        from fr_cli.core.usage import UsageTracker
        t = UsageTracker(path=self.path)
        try:
            t.install_listener(bus=self.bus)
            self.bus.emit("llm.responded", data={
                "model": "glm-4-flash",
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            })
            # 同步事件,handler 立即跑
            summary = t.summary(days=1)
            assert summary["calls"] == 1
            assert summary["prompt_tokens"] == 100
            assert summary["completion_tokens"] == 50
            assert summary["total_tokens"] == 150
        finally:
            t.uninstall_listener()

    def test_v2_dispatch_event_also_records(self):
        from fr_cli.core.usage import UsageTracker
        t = UsageTracker(path=self.path)
        try:
            t.install_listener(bus=self.bus)
            # v2 dispatch_event 内部走 v3 bus,所以也应该被收到
            dispatch_event(V2Events.LLM_RESPONDED, data={
                "model": "deepseek-chat",
                "usage": {"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300},
            }, source="chat")
            summary = t.summary(days=1)
            assert summary["calls"] == 1
            assert summary["total_tokens"] == 300
        finally:
            t.uninstall_listener()

    def test_no_usage_skips(self):
        from fr_cli.core.usage import UsageTracker
        t = UsageTracker(path=self.path)
        try:
            t.install_listener(bus=self.bus)
            # 没 usage 数据,应跳过
            self.bus.emit("llm.responded", data={"model": "x", "response_time": 1.2})
            summary = t.summary(days=1)
            assert summary["calls"] == 0
        finally:
            t.uninstall_listener()

    def test_idempotent_install(self):
        from fr_cli.core.usage import UsageTracker
        t = UsageTracker(path=self.path)
        try:
            assert t.install_listener(bus=self.bus) is True
            # 第二次 install 返回 True(已存在,不报错)
            assert t.install_listener(bus=self.bus) is True
            # 只应有 1 个 listener
            assert self.bus.listener_count("llm.responded") == 1
        finally:
            t.uninstall_listener()

    def test_uninstall_stops(self):
        from fr_cli.core.usage import UsageTracker
        t = UsageTracker(path=self.path)
        t.install_listener(bus=self.bus)
        self.bus.emit("llm.responded", data={
            "model": "x", "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
        })
        assert t.summary(days=1)["calls"] == 1

        t.uninstall_listener()
        self.bus.emit("llm.responded", data={
            "model": "x", "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}
        })
        # 仍然只有 1 条
        assert t.summary(days=1)["calls"] == 1
        assert t.summary(days=1)["total_tokens"] == 2

    def test_explicit_record_still_works(self):
        """显式 record() 与 listener 叠加"""
        from fr_cli.core.usage import UsageTracker
        t = UsageTracker(path=self.path)
        try:
            t.install_listener(bus=self.bus)
            # 显式 record
            t.record("openai", "gpt-4", 500, 200, 700)
            # listener 自动 record
            self.bus.emit("llm.responded", data={
                "model": "glm-4-flash", "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
            })
            summary = t.summary(days=1)
            assert summary["calls"] == 2
            assert summary["total_tokens"] == 700 + 150
        finally:
            t.uninstall_listener()

    def test_persistence_across_instances(self):
        """持久化到 JSON,新实例能读回"""
        from fr_cli.core.usage import UsageTracker
        t1 = UsageTracker(path=self.path)
        try:
            t1.install_listener(bus=self.bus)
            self.bus.emit("llm.responded", data={
                "model": "x", "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
            })
        finally:
            t1.uninstall_listener()

        # 新实例读回
        t2 = UsageTracker(path=self.path)
        summary = t2.summary(days=1)
        assert summary["calls"] == 1
        assert summary["total_tokens"] == 15

    def test_uninstall_when_not_installed(self):
        from fr_cli.core.usage import UsageTracker
        t = UsageTracker(path=self.path)
        assert t.uninstall_listener() is False


# ==================== ErrorLedger ====================

class TestErrorLedgerListener:
    def setup_method(self):
        EventBus.reset()
        self.bus = EventBus.instance()
        self.bus.clear()
        # 重置 ErrorLedger 单例
        from fr_cli.core import error_ledger as el_mod
        el_mod.ErrorLedger._instance = None
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.path = self.tmp.name

    def teardown_method(self):
        from fr_cli.core import error_ledger as el_mod
        el_mod.ErrorLedger._instance = None
        try:
            os.unlink(self.path)
        except Exception:
            pass

    def test_install_returns_count(self):
        from fr_cli.core.error_ledger import (
            get_error_ledger, install_bus_listeners,
        )
        get_error_ledger(store_path=self.path)
        n = install_bus_listeners(bus=self.bus)
        assert n >= 3  # 至少 tool.failed / llm.failed / agent.failed

    def test_tool_failed_auto_records(self):
        from fr_cli.core.error_ledger import (
            get_error_ledger, install_bus_listeners,
        )
        ledger = get_error_ledger(store_path=self.path)
        install_bus_listeners(bus=self.bus)
        self.bus.emit("tool.failed", data={
            "name": "read_file", "error": "file not found"
        }, source="command_executor")
        errors = ledger.list_errors("tool", limit=10)
        assert len(errors) == 1
        assert "read_file" in errors[0]["source_id"]
        assert "file not found" in errors[0]["error"]

    def test_llm_failed_auto_records(self):
        from fr_cli.core.error_ledger import (
            get_error_ledger, install_bus_listeners,
        )
        ledger = get_error_ledger(store_path=self.path)
        install_bus_listeners(bus=self.bus)
        self.bus.emit("llm.failed", data={
            "model": "glm-4-flash", "error": "rate limit"
        })
        errors = ledger.list_errors("llm", limit=10)
        assert len(errors) == 1
        assert "glm-4-flash" in errors[0]["source_id"]
        assert "rate limit" in errors[0]["error"]

    def test_agent_failed_auto_records(self):
        from fr_cli.core.error_ledger import (
            get_error_ledger, install_bus_listeners,
        )
        ledger = get_error_ledger(store_path=self.path)
        install_bus_listeners(bus=self.bus)
        self.bus.emit("agent.failed", data={
            "name": "coder", "error": "syntax error"
        })
        errors = ledger.list_errors("agent", limit=10)
        assert len(errors) == 1
        assert "coder" in errors[0]["source_id"]

    def test_error_occurred_auto_records(self):
        from fr_cli.core.error_ledger import (
            get_error_ledger, install_bus_listeners,
        )
        ledger = get_error_ledger(store_path=self.path)
        install_bus_listeners(bus=self.bus)
        self.bus.emit("error.occurred", data={
            "description": "disk full",
            "error": "no space left on device"
        })
        errors = ledger.list_errors("error", limit=10)
        assert len(errors) == 1
        assert "disk full" in errors[0]["description"]

    def test_succeeded_does_not_record(self):
        from fr_cli.core.error_ledger import (
            get_error_ledger, install_bus_listeners,
        )
        ledger = get_error_ledger(store_path=self.path)
        install_bus_listeners(bus=self.bus)
        # tool.succeeded 不是 failed 类,不应记录
        self.bus.emit("tool.succeeded", data={"name": "x", "result": "ok"})
        # 应保持空
        assert ledger.counts() == {}

    def test_v2_dispatch_also_records(self):
        from fr_cli.core.error_ledger import (
            get_error_ledger, install_bus_listeners,
        )
        ledger = get_error_ledger(store_path=self.path)
        install_bus_listeners(bus=self.bus)
        # v2 dispatch → v3 bus → listener
        dispatch_event(V2Events.TOOL_FAILED, data={
            "name": "write_file", "error": "permission denied"
        }, source="command_executor")
        errors = ledger.list_errors("tool", limit=10)
        assert len(errors) == 1
        assert "permission denied" in errors[0]["error"]

    def test_metadata_preserved(self):
        from fr_cli.core.error_ledger import (
            get_error_ledger, install_bus_listeners,
        )
        ledger = get_error_ledger(store_path=self.path)
        install_bus_listeners(bus=self.bus)
        self.bus.emit("tool.failed", data={
            "name": "x",
            "error": "boom",
            "url": "https://example.com",  # metadata
            "size": 1024,  # metadata
        })
        errors = ledger.list_errors("tool", limit=10)
        assert errors[0]["metadata"]["url"] == "https://example.com"
        assert errors[0]["metadata"]["size"] == 1024


# ==================== 集成测试: 全链路 ====================

class TestIntegration:
    """v2 dispatch_event → v3 bus → usage + error ledger 自动记录"""

    def setup_method(self):
        EventBus.reset()
        self.bus = EventBus.instance()
        self.bus.clear()
        from fr_cli.core import error_ledger as el_mod
        el_mod.ErrorLedger._instance = None
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.path = self.tmp.name

    def teardown_method(self):
        from fr_cli.core import error_ledger as el_mod
        el_mod.ErrorLedger._instance = None
        try:
            os.unlink(self.path)
        except Exception:
            pass

    def test_full_flow(self):
        """模拟完整会话:LLM 成功 → tool 失败"""
        from fr_cli.core.usage import UsageTracker
        from fr_cli.core.error_ledger import (
            get_error_ledger, install_bus_listeners,
        )

        usage = UsageTracker(path=self.path)
        usage.install_listener(bus=self.bus)
        ledger = get_error_ledger(store_path=self.path)
        install_bus_listeners(bus=self.bus)

        # 1. LLM 成功响应
        dispatch_event(V2Events.LLM_RESPONDED, data={
            "model": "glm-4-flash",
            "usage": {"prompt_tokens": 500, "completion_tokens": 200, "total_tokens": 700},
        }, source="chat")

        # 2. tool 调用成功
        dispatch_event(V2Events.TOOL_SUCCEEDED, data={
            "name": "read_file", "result": "ok"
        }, source="command_executor")

        # 3. tool 调用失败
        dispatch_event(V2Events.TOOL_FAILED, data={
            "name": "write_file", "error": "permission denied"
        }, source="command_executor")

        # 验证
        assert usage.summary(days=1)["calls"] == 1
        assert usage.summary(days=1)["total_tokens"] == 700

        tool_errors = ledger.list_errors("tool", limit=10)
        assert len(tool_errors) == 1
        assert "write_file" in tool_errors[0]["source_id"]
        assert "permission denied" in tool_errors[0]["error"]

        # 清理
        usage.uninstall_listener()
