"""
/metrics REPL 命令 + 事件派发对账测试

覆盖:
- /metrics 三种格式(摘要 / json / prom)都能输出且不抛异常
- metrics 模块未安装时给友好提示(不抛异常)
- 未知子命令格式时给用法提示
- 事件名清单完整性(ALL / MUST / OPTIONAL 三张表)
- **对账守卫**:MUST_DISPATCH_EVENTS 里每个事件都必须有生产派发点
  (扫描 fr_cli/ 源码里的 dispatch_event 调用点)
- command.executed 派发:跑一次真实 router.dispatch() 后事件确实被派发
- dispatch_event 事件名拼写自检(未知事件名 → log.warning)
"""
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from fr_cli.core.events import (
    ALL_V2_EVENTS,
    HOOK_EVENTS,
    MUST_DISPATCH_EVENTS,
    OPTIONAL_EVENTS,
    V2Events,
    dispatch_event,
)
from fr_cli.repl.commands.config.metrics import _cmd_metrics
from fr_cli.v3.core.events import EventBus

# 项目根目录(fr_cli/ 包所在位置)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PKG_ROOT = _PROJECT_ROOT / "fr_cli"

# 源码里 dispatch_event(...) 的调用点
_DISPATCH_CALL_RE = re.compile(r"dispatch_event\s*\(")
# 调用点之后取多少字符作为"这次派发用了哪个事件名"的判定范围
_SNIPPET_CHARS = 400

# 事件值 → V2Events 属性名(源码里写的是 V2Events.XXX 而不是字面量)
_ATTR_BY_EVENT: Dict[str, str] = {}
for _attr in dir(V2Events):
    if _attr.startswith("_"):
        continue
    _value = getattr(V2Events, _attr)
    if isinstance(_value, str):
        _ATTR_BY_EVENT.setdefault(_value, _attr)


class _FakeState:
    """最小可用的 state 替身(只提供 /metrics 需要的字段)"""

    def __init__(self, metrics=None):
        self.metrics = metrics
        self.lang = "zh"


@pytest.fixture
def metrics_plugin():
    """一个真实但未接入总线的 MetricsPlugin"""
    from fr_cli.core.metrics import MetricsPlugin

    plugin = MetricsPlugin()
    plugin.counter_inc("tool.invoked", name="read_file")
    return plugin


# ==================== /metrics 命令 ====================

class TestMetricsCommand:
    def test_summary_format(self, capsys, metrics_plugin):
        state = _FakeState(metrics_plugin)
        assert _cmd_metrics(state, ["/metrics"]) is False
        out = capsys.readouterr().out
        assert "Metrics Summary" in out

    def test_json_format(self, capsys, metrics_plugin):
        state = _FakeState(metrics_plugin)
        assert _cmd_metrics(state, ["/metrics", "json"]) is False
        out = capsys.readouterr().out
        payload = json.loads(out)
        assert "counters" in payload
        assert "meta" in payload

    def test_prom_format(self, capsys, metrics_plugin):
        state = _FakeState(metrics_plugin)
        assert _cmd_metrics(state, ["/metrics", "prom"]) is False
        out = capsys.readouterr().out
        assert "# TYPE" in out
        assert "tool.invoked" in out

    def test_metrics_not_installed_friendly_message(self, capsys):
        """指标模块未安装 → 友好提示,不抛异常"""
        state = _FakeState(None)
        assert _cmd_metrics(state, ["/metrics"]) is False
        out = capsys.readouterr().out
        assert "指标模块未初始化" in out

    def test_metrics_attribute_missing_friendly_message(self, capsys):
        """state 上完全没有 metrics 属性 → 友好提示,不抛异常"""
        state = _FakeState(None)
        del state.metrics
        assert _cmd_metrics(state, ["/metrics", "json"]) is False
        out = capsys.readouterr().out
        assert "指标模块未初始化" in out

    def test_unknown_format_shows_usage(self, capsys, metrics_plugin):
        state = _FakeState(metrics_plugin)
        assert _cmd_metrics(state, ["/metrics", "wat"]) is False
        out = capsys.readouterr().out
        assert "用法" in out


# ==================== 事件名清单 ====================

class TestEventNameInventory:
    def test_all_v2_events_complete(self):
        """ALL_V2_EVENTS 从类定义推导,覆盖 V2Events 的全部取值"""
        assert len(ALL_V2_EVENTS) == 23
        declared = {
            value
            for name, value in vars(V2Events).items()
            if not name.startswith("_") and isinstance(value, str)
        }
        assert set(ALL_V2_EVENTS) == declared

    def test_must_events_are_subset(self):
        assert set(MUST_DISPATCH_EVENTS).issubset(set(ALL_V2_EVENTS))

    def test_optional_events_are_subset(self):
        assert set(OPTIONAL_EVENTS).issubset(set(ALL_V2_EVENTS))

    def test_must_and_optional_disjoint(self):
        assert not set(MUST_DISPATCH_EVENTS) & set(OPTIONAL_EVENTS)

    def test_hook_events_unchanged(self):
        assert len(HOOK_EVENTS) == 6


# ==================== 对账守卫(防复发) ====================

def _collect_dispatch_sites() -> Dict[str, List[str]]:
    """扫描 fr_cli/ 源码,返回 事件名 → 派发点文件列表

    判定方式:找到 ``dispatch_event(`` 调用点,看它后面的一段文本里
    是否出现该事件名(字面量形式)或对应的 ``V2Events.XXX`` 属性名。
    """
    sites: Dict[str, List[str]] = {}
    for path in sorted(_PKG_ROOT.rglob("*.py")):
        # 事件常量定义文件本身不算派发点
        if path == _PKG_ROOT / "core" / "events.py":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for match in _DISPATCH_CALL_RE.finditer(text):
            snippet = text[match.end(): match.end() + _SNIPPET_CHARS]
            for event_name, attr_name in _ATTR_BY_EVENT.items():
                if event_name in snippet or f"V2Events.{attr_name}" in snippet:
                    sites.setdefault(event_name, []).append(str(path))
    return sites


class TestEventDispatchReconciliation:
    def test_must_events_have_production_dispatch_sites(self):
        """每个 MUST 事件都必须有生产派发点 —— 这是防止缺陷复发的关键测试"""
        sites = _collect_dispatch_sites()
        missing = [e for e in MUST_DISPATCH_EVENTS if not sites.get(e)]
        assert not missing, (
            f"以下事件在 MUST_DISPATCH_EVENTS 里但源码中找不到派发点: {missing};"
            f"已找到的派发点: {sites}"
        )

    def test_expected_dispatch_files(self):
        """派发点落在预期的文件里(防止事件被派发到错误的地方)"""
        sites = _collect_dispatch_sites()
        expected = {
            V2Events.COMMAND_EXECUTED: "repl/router.py",
            V2Events.SESSION_CREATED: "chat/pipeline_post.py",
            V2Events.SESSION_SAVED: "chat/pipeline_post.py",
            V2Events.APP_STOPPED: "main.py",
            V2Events.ERROR_OCCURRED: "core/errors.py",
        }
        for event_name, filename in expected.items():
            files = sites.get(event_name, [])
            assert any(f.endswith(filename) for f in files), (
                f"{event_name} 的派发点不在 {filename} 里: {files}"
            )


# ==================== command.executed 派发 ====================

class TestCommandExecutedDispatch:
    def test_real_dispatch_emits_command_executed(self, capsys):
        """跑一次真实 router.dispatch() → command.executed 被派发"""
        from fr_cli.repl.router import dispatch

        bus = EventBus.instance()
        received = []

        def handler(event):
            received.append(event)

        bus.on(V2Events.COMMAND_EXECUTED, handler)
        try:
            state = _FakeState(None)
            before = bus.stats().get(V2Events.COMMAND_EXECUTED, 0)
            should_exit = dispatch(state, "/metrics")
            after = bus.stats().get(V2Events.COMMAND_EXECUTED, 0)
        finally:
            bus.off(V2Events.COMMAND_EXECUTED, handler)

        assert should_exit is False
        assert after == before + 1
        assert len(received) == 1
        data = received[0].data
        assert data["cmd"] == "/metrics"
        assert data["should_break"] is False
        assert "elapsed" in data

    def test_dispatch_event_data_shape(self):
        """事件 data 结构:cmd / 耗时 / 是否退出循环"""
        from fr_cli.repl.router import _dispatch_command_executed

        bus = EventBus.instance()
        received = []
        handler = received.append
        bus.on(V2Events.COMMAND_EXECUTED, handler)
        try:
            _dispatch_command_executed("/model", 1.23456, True)
        finally:
            bus.off(V2Events.COMMAND_EXECUTED, handler)

        assert len(received) == 1
        data = received[0].data
        assert data["cmd"] == "/model"
        assert data["elapsed"] == 1.235
        assert data["should_break"] is True


# ==================== 事件名拼写自检 ====================

class TestEventNameSelfCheck:
    def test_unknown_event_name_warns(self, caplog):
        with caplog.at_level(logging.WARNING, logger="fr_cli.core.events"):
            dispatch_event("totally.bogus.event")
        assert any("totally.bogus.event" in rec.getMessage() for rec in caplog.records)

    def test_unknown_event_name_still_dispatches(self, caplog):
        """自检只告警,不改变现有行为(事件照常派发)"""
        bus = EventBus.instance()
        received = []
        handler = received.append
        bus.on("totally.bogus.event", handler)
        try:
            with caplog.at_level(logging.WARNING, logger="fr_cli.core.events"):
                event = dispatch_event("totally.bogus.event")
        finally:
            bus.off("totally.bogus.event", handler)

        assert event is not None
        assert event.type == "totally.bogus.event"
        assert len(received) == 1

    def test_known_event_name_does_not_warn(self, caplog):
        with caplog.at_level(logging.WARNING, logger="fr_cli.core.events"):
            dispatch_event(V2Events.COMMAND_EXECUTED)
        assert not [
            rec for rec in caplog.records
            if "未知事件名" in rec.getMessage()
        ]

    def test_hook_event_name_does_not_warn(self, caplog):
        """Hook 事件走另一套命名,同样不算拼写错误"""
        with caplog.at_level(logging.WARNING, logger="fr_cli.core.events"):
            dispatch_event(HOOK_EVENTS[0])
        assert not [
            rec for rec in caplog.records
            if "未知事件名" in rec.getMessage()
        ]
