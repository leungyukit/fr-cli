"""
结构化 trace / span 日志测试
"""
import threading

import pytest

from fr_cli.core.trace import (
    KIND_AGENT,
    KIND_LLM,
    KIND_ROOT,
    KIND_TOOL,
    STATUS_ERROR,
    STATUS_OK,
    TraceRecorder,
    TraceSpan,
    current_span,
    get_recorder,
    get_recent_spans,
    get_traces,
    new_trace_id,
    reset_recorder,
    start_span,
    trace_summary,
)


@pytest.fixture(autouse=True)
def _clean_recorder():
    """每个用例前后都重置全局记录器，避免用例间互相污染。"""
    reset_recorder()
    yield
    reset_recorder()


class TestTraceSpanModel:
    """TraceSpan 字段完整性与耗时计算"""

    def test_fields_present(self):
        with start_span("my_op", kind=KIND_TOOL, foo="bar") as span:
            assert isinstance(span, TraceSpan)
            assert span.name == "my_op"
            assert span.kind == KIND_TOOL
            assert span.attributes.get("foo") == "bar"
            assert span.trace_id
            assert span.span_id
            assert span.parent_span_id is None
            assert span.status == STATUS_OK
            assert span.error is None

    def test_duration_recorded(self):
        with start_span("timed") as span:
            pass
        assert span.start_time > 0
        assert span.end_time is not None
        assert span.end_time >= span.start_time
        assert span.duration_ms is not None
        assert span.duration_ms >= 0

    def test_set_attribute(self):
        with start_span("op") as span:
            span.set_attribute("success", True)
            span.set_attributes({"a": 1, "b": 2})
        assert span.attributes["success"] is True
        assert span.attributes["a"] == 1
        assert span.attributes["b"] == 2

    def test_to_dict_is_json_serialisable(self):
        import json
        with start_span("op", kind=KIND_LLM) as span:
            span.set_attribute("model", "glm-4-flash")
        data = span.to_dict()
        assert data["name"] == "op"
        assert data["kind"] == KIND_LLM
        assert data["attributes"]["model"] == "glm-4-flash"
        assert json.loads(json.dumps(data, ensure_ascii=False))["trace_id"] == span.trace_id


class TestContextPropagation:
    """嵌套 span 的 parent / trace_id 继承"""

    def test_nested_span_inherits_parent_and_trace(self):
        with start_span("root", kind=KIND_ROOT) as root:
            with start_span("child", kind=KIND_TOOL) as child:
                assert child.trace_id == root.trace_id
                assert child.parent_span_id == root.span_id
                assert child.span_id != root.span_id

    def test_three_level_nesting(self):
        with start_span("l1") as l1:
            with start_span("l2") as l2:
                with start_span("l3") as l3:
                    assert l3.trace_id == l1.trace_id
                    assert l3.parent_span_id == l2.span_id
                    assert l2.parent_span_id == l1.span_id

    def test_current_span_visible_inside(self):
        assert current_span() is None
        with start_span("outer") as outer:
            assert current_span() is outer
            with start_span("inner") as inner:
                assert current_span() is inner
            assert current_span() is outer
        assert current_span() is None

    def test_standalone_span_has_own_trace_id(self):
        """没有根 span 时也能独立工作：trace_id 自成一体。"""
        with start_span("standalone") as span:
            assert span.parent_span_id is None
            assert span.trace_id
        with start_span("standalone2") as span2:
            assert span2.trace_id != span.trace_id

    def test_trace_id_format(self):
        tid = new_trace_id()
        assert len(tid) == 16
        assert all(c in "0123456789abcdef" for c in tid)


class TestErrorSemantics:
    """异常时 status=error，且异常继续抛出"""

    def test_exception_marks_error_and_reraises(self):
        with pytest.raises(ValueError, match="boom"):
            with start_span("failing") as span:
                raise ValueError("boom")
        assert span.status == STATUS_ERROR
        assert "boom" in span.error
        assert "ValueError" in span.error
        assert span.end_time is not None
        assert span.duration_ms is not None

    def test_error_span_is_recorded(self):
        with pytest.raises(RuntimeError):
            with start_span("failing2"):
                raise RuntimeError("nope")
        spans = get_recent_spans()
        assert any(s.name == "failing2" and s.status == STATUS_ERROR for s in spans)

    def test_no_exception_means_ok(self):
        with start_span("fine") as span:
            pass
        assert span.status == STATUS_OK
        assert span.error is None


class TestRecorder:
    """记录器的 maxlen 淘汰与查询"""

    def test_maxlen_eviction(self):
        # start_span 走全局记录器，这里直接验证独立实例的淘汰行为
        rec2 = TraceRecorder(max_spans=3)
        for i in range(10):
            span = TraceSpan(trace_id=f"t{i}", span_id=f"s{i}", name=f"op{i}")
            rec2.record(span)
        spans = rec2.recent()
        assert len(spans) == 3
        assert [s.name for s in spans] == ["op7", "op8", "op9"]

    def test_recent_limit(self):
        for i in range(5):
            with start_span(f"op{i}"):
                pass
        assert len(get_recent_spans(limit=2)) == 2

    def test_clear(self):
        with start_span("op"):
            pass
        rec = get_recorder()
        assert rec.recent()
        rec.clear()
        assert rec.recent() == []

    def test_reset_recorder_returns_new_instance(self):
        first = get_recorder()
        second = reset_recorder()
        assert first is not second


class TestAggregation:
    """get_traces() / trace_summary() 的聚合结果"""

    def test_get_traces_groups_by_trace_id(self):
        with start_span("root", kind=KIND_ROOT):
            with start_span("tool_a", kind=KIND_TOOL):
                pass
            with start_span("tool_b", kind=KIND_TOOL):
                pass
        traces = get_traces()
        assert len(traces) == 1
        t = traces[0]
        assert t["span_count"] == 3
        assert t["error_count"] == 0
        assert t["root_name"] == "root"
        assert t["root_kind"] == KIND_ROOT
        assert t["total_duration_ms"] >= 0
        assert len(t["spans"]) == 3

    def test_get_traces_counts_errors(self):
        with start_span("root"):
            with pytest.raises(ValueError):
                with start_span("bad"):
                    raise ValueError("x")
        traces = get_traces()
        assert traces[0]["error_count"] == 1

    def test_get_traces_limit(self):
        for i in range(4):
            with start_span(f"root{i}"):
                pass
        assert len(get_traces(limit=2)) == 2

    def test_trace_summary_contains_key_info(self):
        with start_span("root", kind=KIND_ROOT):
            with start_span("tool_x", kind=KIND_TOOL):
                pass
        text = trace_summary()
        assert "root" in text
        assert "tool_x" in text
        assert "span" in text

    def test_trace_summary_empty(self):
        assert "暂无" in trace_summary()

    def test_kinds_are_recorded(self):
        with start_span("a", kind=KIND_AGENT):
            with start_span("b", kind=KIND_LLM):
                with start_span("c", kind=KIND_TOOL):
                    pass
        kinds = {s["kind"] for s in get_traces()[0]["spans"]}
        assert kinds == {KIND_AGENT, KIND_LLM, KIND_TOOL}


class TestConcurrency:
    """并发下不崩"""

    def test_concurrent_spans(self):
        errors = []

        def worker(idx):
            try:
                for _ in range(20):
                    with start_span(f"worker{idx}", kind=KIND_TOOL):
                        pass
            except Exception as e:  # pragma: no cover - 只在失败时触发
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert len(get_recent_spans(limit=1000)) == 160

    def test_concurrent_nested_spans_keep_trace_ids(self):
        trace_ids = []
        lock = threading.Lock()

        def worker():
            with start_span("outer") as outer:
                with start_span("inner") as inner:
                    with lock:
                        trace_ids.append((outer.trace_id, inner.trace_id))

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(trace_ids) == 10
        for outer_id, inner_id in trace_ids:
            assert outer_id == inner_id
