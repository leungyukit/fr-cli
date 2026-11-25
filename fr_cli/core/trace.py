"""
结构化 trace / span 日志 —— 把一次调用里的 LLM 与工具执行串联起来

背景：
  此前全仓没有 trace_id / span_id，一次对话里的"模型调用 → 工具执行 →
  再次模型调用"只能靠零散的 print 串联，线上排查时无法还原调用链。

本模块提供：
  - TraceSpan          —— 一条 span 的数据模型
  - start_span()       —— 上下文管理器，嵌套 span 自动继承 parent / trace_id
  - TraceRecorder      —— 进程级单例，内存保留最近 N 条 span（可选 JSONL 落盘）
  - get_recent_spans() / get_traces() / trace_summary() —— 查询与聚合

设计约束：
  1. **不引入新依赖**（只用标准库）。
  2. **可在没有根 span 的情况下独立工作**：没有父 span 时自动开一个根 span，
     trace_id 自成一体（根 span / LLM span 由调用方按需埋点）。
  3. **落盘默认关闭**，避免污染用户目录；需显式开启（见下方开关）。
  4. **线程安全**：span 记录用 threading.Lock 保护；上下文用 contextvars
     隔离（每个线程 / 任务有独立上下文，不会互相串 parent）。

落盘开关（环境变量）：
  - FR_CLI_TRACE_ENABLE=1     开启 JSONL 落盘
  - FR_CLI_TRACE_DIR=<目录>   指定落盘目录（默认 ~/.fr_cli/traces）
  落盘文件格式：每个 trace 一个文件 `<目录>/<trace_id>.jsonl`，每行一个 span。
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Deque, Dict, Iterator, List, Optional

# ------------------------------------------------------------------
# 常量
# ------------------------------------------------------------------

# trace_id 长度（短、可读）
TRACE_ID_LEN = 16
# span_id 长度
SPAN_ID_LEN = 8
# 内存中保留的 span 条数上限
DEFAULT_MAX_SPANS = 500
# span 类型
KIND_ROOT = "root"
KIND_LLM = "llm"
KIND_TOOL = "tool"
KIND_AGENT = "agent"
# 状态
STATUS_OK = "ok"
STATUS_ERROR = "error"

# 环境变量开关
ENV_TRACE_ENABLE = "FR_CLI_TRACE_ENABLE"
ENV_TRACE_DIR = "FR_CLI_TRACE_DIR"


def new_trace_id() -> str:
    """生成一个短且可读的 trace_id（16 位十六进制）。"""
    return uuid.uuid4().hex[:TRACE_ID_LEN]


def _new_span_id() -> str:
    """生成一个短且可读的 span_id（8 位十六进制）。"""
    return uuid.uuid4().hex[:SPAN_ID_LEN]


# ------------------------------------------------------------------
# 数据模型
# ------------------------------------------------------------------

@dataclass
class TraceSpan:
    """一条 span —— 一次被观测的操作。

    Attributes:
        trace_id:      所属 trace 的 id（嵌套 span 与父 span 一致）
        span_id:       本 span 的 id
        parent_span_id:父 span 的 id；None 表示这是该 trace 的根 span
        name:          操作名（如工具名 / 模型名）
        kind:          操作类型 —— "root" / "llm" / "tool" / "agent"
        attributes:    附加属性（工具名、参数摘要、成功与否等）
        start_time:    开始时间戳（time.time()）
        end_time:      结束时间戳；未结束时为 None
        duration_ms:   耗时（毫秒）；未结束时为 None
        status:        "ok" / "error"
        error:         异常信息（status 为 error 时有值）
    """

    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    name: str = ""
    kind: str = KIND_ROOT
    attributes: Dict[str, Any] = field(default_factory=dict)
    start_time: float = 0.0
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    status: str = STATUS_OK
    error: Optional[str] = None

    def set_attribute(self, key: str, value: Any) -> None:
        """写入 / 覆盖一个属性（埋点方在 span 结束后补充结果时使用）。"""
        self.attributes[key] = value

    def set_attributes(self, values: Dict[str, Any]) -> None:
        """批量写入属性。"""
        if values:
            self.attributes.update(values)

    def mark_error(self, error: str) -> None:
        """标记 span 为失败并记录错误信息。"""
        self.status = STATUS_ERROR
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        """转成可 JSON 序列化的字典（落盘 / 导出用）。"""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "kind": self.kind,
            "attributes": dict(self.attributes),
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "error": self.error,
        }

    def __repr__(self) -> str:
        return (
            f"TraceSpan(trace_id={self.trace_id!r}, span_id={self.span_id!r}, "
            f"name={self.name!r}, kind={self.kind!r}, status={self.status!r}, "
            f"duration_ms={self.duration_ms!r})"
        )


# ------------------------------------------------------------------
# 上下文传播
# ------------------------------------------------------------------

# 当前 span（contextvars：线程 / 协程各自隔离，嵌套时自动继承 parent）
_current_span: ContextVar[Optional[TraceSpan]] = ContextVar("fr_cli_current_span", default=None)


def current_span() -> Optional[TraceSpan]:
    """返回当前上下文中的 span（没有则为 None）。"""
    return _current_span.get()


# ------------------------------------------------------------------
# 记录器
# ------------------------------------------------------------------

class TraceRecorder:
    """进程级 span 记录器。

    - 内存里用 `deque(maxlen=N)` 保留最近 N 条 span，超出自动淘汰最旧的
    - 可选把 span 以 JSONL 落盘（默认关闭）
    - 所有读写用 threading.Lock 保护，多线程下不会崩
    """

    def __init__(self, max_spans: int = DEFAULT_MAX_SPANS, dump_dir: Optional[Path] = None):
        """初始化记录器。

        Args:
            max_spans: 内存中保留的 span 条数上限（<=0 表示不限制）
            dump_dir:  JSONL 落盘目录；None 表示不落盘
        """
        self._spans: Deque[TraceSpan] = deque(maxlen=max_spans if max_spans and max_spans > 0 else None)
        self._max_spans = max_spans
        self._dump_dir = dump_dir
        self._lock = threading.Lock()

    # ---------------- 记录 ----------------

    def record(self, span: TraceSpan) -> None:
        """记录一条已结束的 span。"""
        with self._lock:
            self._spans.append(span)
        if self._dump_dir is not None:
            self._dump_span(span)

    def _dump_span(self, span: TraceSpan) -> None:
        """把 span 以 JSONL 追加写入 `<dump_dir>/<trace_id>.jsonl`（失败不影响主流程）。"""
        try:
            self._dump_dir.mkdir(parents=True, exist_ok=True)
            target = self._dump_dir / f"{span.trace_id}.jsonl"
            with target.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(span.to_dict(), ensure_ascii=False) + "\n")
        except Exception:
            pass  # 落盘失败不应影响主流程

    # ---------------- 查询 ----------------

    def recent(self, limit: int = 50) -> List[TraceSpan]:
        """返回最近结束的 span（按时间正序，最旧的在前）。"""
        with self._lock:
            items = list(self._spans)
        if limit and limit > 0:
            items = items[-limit:]
        return items

    def traces(self, limit: int = 20) -> List[Dict[str, Any]]:
        """按 trace_id 聚合 span，返回最近的若干条 trace 摘要（最新在前）。"""
        with self._lock:
            items = list(self._spans)

        buckets: Dict[str, List[TraceSpan]] = {}
        order: List[str] = []
        for span in items:
            if span.trace_id not in buckets:
                buckets[span.trace_id] = []
                order.append(span.trace_id)
            buckets[span.trace_id].append(span)

        traces = [_aggregate_trace(tid, buckets[tid]) for tid in order]
        traces.reverse()  # 最新的 trace 在前
        if limit and limit > 0:
            traces = traces[:limit]
        return traces

    def clear(self) -> None:
        """清空内存中的 span（测试用）。"""
        with self._lock:
            self._spans.clear()


def _aggregate_trace(trace_id: str, spans: List[TraceSpan]) -> Dict[str, Any]:
    """把同一个 trace 下的 span 聚合成一条摘要。"""
    start = min((s.start_time for s in spans if s.start_time), default=0.0)
    ends = [s.end_time for s in spans if s.end_time is not None]
    end = max(ends) if ends else None
    total_ms = sum(s.duration_ms or 0.0 for s in spans)
    errors = [s for s in spans if s.status == STATUS_ERROR]
    roots = [s for s in spans if not s.parent_span_id]
    root = roots[0] if roots else spans[0]
    return {
        "trace_id": trace_id,
        "root_name": root.name if root else "",
        "root_kind": root.kind if root else "",
        "spans": [s.to_dict() for s in spans],
        "span_count": len(spans),
        "error_count": len(errors),
        "start_time": start,
        "end_time": end,
        "total_duration_ms": round(total_ms, 3),
        "wall_duration_ms": round((end - start) * 1000, 3) if (end is not None and start) else 0.0,
    }


# ------------------------------------------------------------------
# 全局单例
# ------------------------------------------------------------------

_recorder: Optional[TraceRecorder] = None
_recorder_lock = threading.Lock()


def _default_dump_dir() -> Optional[Path]:
    """根据环境变量决定是否落盘；未开启则返回 None（默认不落盘）。"""
    enabled = os.environ.get(ENV_TRACE_ENABLE, "").strip().lower() in ("1", "true", "yes", "on")
    custom = os.environ.get(ENV_TRACE_DIR, "").strip()
    if not enabled and not custom:
        return None
    if custom:
        return Path(custom).expanduser()
    try:
        from fr_cli.conf.paths import ROOT
        return Path(ROOT) / "traces"
    except Exception:
        return Path.home() / ".fr_cli" / "traces"


def get_recorder() -> TraceRecorder:
    """获取全局 TraceRecorder 单例（首次调用时创建）。"""
    global _recorder
    if _recorder is None:
        with _recorder_lock:
            if _recorder is None:
                _recorder = TraceRecorder(
                    max_spans=DEFAULT_MAX_SPANS,
                    dump_dir=_default_dump_dir(),
                )
    return _recorder


def reset_recorder(max_spans: int = DEFAULT_MAX_SPANS,
                   dump_dir: Optional[Path] = None) -> TraceRecorder:
    """重置全局记录器（测试用），返回新的实例。"""
    global _recorder
    with _recorder_lock:
        _recorder = TraceRecorder(max_spans=max_spans, dump_dir=dump_dir)
    return _recorder


# ------------------------------------------------------------------
# 埋点入口
# ------------------------------------------------------------------

@contextmanager
def start_span(name: str, kind: str = KIND_ROOT, **attrs: Any) -> Iterator[TraceSpan]:
    """开启一个 span（上下文管理器）。

    - 若当前上下文已有 span → 自动继承其 trace_id，并把当前 span 设为 parent
    - 若当前上下文没有 span → 本 span 自成一体（trace_id 自新生成），充当根 span
    - 块内抛异常 → span 记 status="error" 与异常信息，然后**继续抛出**
      （不吞异常）

    Args:
        name:  操作名（工具名 / 模型名 / Agent 名）
        kind:  操作类型 —— "root" / "llm" / "tool" / "agent"
        attrs: 附加属性（会以字典形式存入 span.attributes）

    Yields:
        TraceSpan: 供调用方补充结果属性
    """
    parent = _current_span.get()
    if parent is not None:
        trace_id = parent.trace_id
        parent_span_id = parent.span_id
    else:
        trace_id = new_trace_id()
        parent_span_id = None

    span = TraceSpan(
        trace_id=trace_id,
        span_id=_new_span_id(),
        parent_span_id=parent_span_id,
        name=name,
        kind=kind,
        attributes=dict(attrs),
        start_time=time.time(),
    )

    token = _current_span.set(span)
    try:
        yield span
    except BaseException as exc:
        span.mark_error(f"{type(exc).__name__}: {exc}")
        raise
    finally:
        span.end_time = time.time()
        if span.duration_ms is None:
            span.duration_ms = round((span.end_time - span.start_time) * 1000, 3)
        _current_span.reset(token)
        get_recorder().record(span)


# ------------------------------------------------------------------
# 查询接口（模块级便捷函数）
# ------------------------------------------------------------------

def get_recent_spans(limit: int = 50) -> List[TraceSpan]:
    """返回最近结束的 span（按时间正序）。"""
    return get_recorder().recent(limit=limit)


def get_traces(limit: int = 20) -> List[Dict[str, Any]]:
    """按 trace_id 聚合后的 trace 列表（最新在前）。"""
    return get_recorder().traces(limit=limit)


def trace_summary(limit: int = 20) -> str:
    """人类可读的 trace 摘要（每个 trace 的总耗时、span 数、错误数）。"""
    traces = get_traces(limit=limit)
    if not traces:
        return "暂无 trace 记录"

    lines = [f"最近 {len(traces)} 条 trace:"]
    for t in traces:
        lines.append(
            f"  [{t['trace_id']}] {t['root_name'] or '(未命名)'} "
            f"({t['root_kind'] or 'root'}) | span {t['span_count']} | "
            f"错误 {t['error_count']} | 总耗时 {t['total_duration_ms']:.1f}ms"
        )
        for s in t["spans"]:
            indent = "    "
            marker = "✗" if s["status"] == STATUS_ERROR else "✓"
            lines.append(
                f"{indent}{marker} {s['name']} [{s['kind']}] "
                f"{(s['duration_ms'] or 0.0):.1f}ms"
            )
    return "\n".join(lines)


__all__ = [
    "TraceSpan",
    "TraceRecorder",
    "KIND_ROOT",
    "KIND_LLM",
    "KIND_TOOL",
    "KIND_AGENT",
    "STATUS_OK",
    "STATUS_ERROR",
    "ENV_TRACE_ENABLE",
    "ENV_TRACE_DIR",
    "new_trace_id",
    "current_span",
    "start_span",
    "get_recorder",
    "reset_recorder",
    "get_recent_spans",
    "get_traces",
    "trace_summary",
]
