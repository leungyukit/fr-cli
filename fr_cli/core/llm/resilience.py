"""
LLM 调用韧性 —— 错误分类 / 重试 / 降级

v2.8.7 新增（P0-2）。

背景
----
v2.8.6 及以前，``core/stream.py::stream_cnt`` 把 LLM 调用异常**吞成空字符串**：

    except Exception as e:
        ...
    if not full_text:
        return "[错误] 无法获取 AI 回复，请检查 API 密钥配置", usage, response_time, False

后果：

  - 网络抖动 / 限流 / 服务端 5xx 全都被报成"请检查 API 密钥配置" —— **错误信息误导**
  - 一次瞬时失败 = 整轮对话丢失（用户必须重打一遍）
  - ``timeout=60`` 写死，配置层改不动
  - 没有任何降级路径：主模型挂了就是挂了

本模块提供
----------
* :func:`classify_error` —— 把异常分成 transient（可重试）/ auth（凭证问题）/ fatal
* :func:`is_transient` / :func:`describe_error`
* :func:`call_with_retry` —— 指数退避重试
* :func:`resolve_fallback` —— 解析降级用的备用 provider

分类原则
--------
* **transient** —— 网络抖动 / 超时 / 限流 / 5xx：重试有意义
* **auth** —— Key 无效 / 未授权：重试无意义，提示用户改配置
* **fatal** —— 请求本身有问题（参数错、模型名不存在等）：重试无意义
"""
from __future__ import annotations

import re
import time
from typing import Any, Callable, Optional, Tuple

__all__ = [
    "TRANSIENT",
    "AUTH",
    "FATAL",
    "classify_error",
    "is_transient",
    "describe_error",
    "call_with_retry",
    "resolve_fallback",
    "DEFAULT_RETRY",
    "DEFAULT_BACKOFF",
]

#: 分类常量
TRANSIENT = "transient"
AUTH = "auth"
FATAL = "fatal"

#: 默认重试次数（不含首次调用）—— 即最多 3 次尝试
DEFAULT_RETRY = 2
#: 默认退避基数（秒）—— 实际等待 = backoff * 2^(第几次-1)
DEFAULT_BACKOFF = 1.0

#: 按异常类型名匹配的瞬时错误
_TRANSIENT_TYPES = frozenset({
    "TimeoutError", "socket.timeout", "ConnectionError", "ConnectionResetError",
    "ConnectionRefusedError", "ConnectionAbortedError", "BrokenPipeError",
    "APITimeoutError", "APIConnectionError", "RateLimitError",
    "InternalServerError", "ServiceUnavailableError", "TooManyRequests",
    "IncompleteRead", "ReadTimeout", "ConnectTimeout", "ReadError",
    "ProtocolError", "SSLError", "HTTPError", "RemoteProtocolError",
    "ChunkedEncodingError", "JSONDecodeError",
})

#: 按异常类型名匹配的凭证错误
_AUTH_TYPES = frozenset({
    "AuthenticationError", "PermissionDeniedError",
})

_TRANSIENT_RE = re.compile(
    r"(timed?\s*out|timeout|connection (reset|refused|aborted|error|closed)|"
    r"temporarily unavailable|service unavailable|rate limit|too many requests|"
    r"overloaded|bad gateway|gateway timeout|internal server error|"
    r"remote end closed connection|eof occurred|server disconnected|"
    r"failed to establish|ssl error|"
    r"\b(429|500|502|503|504)\b)",
    re.I,
)

_AUTH_RE = re.compile(
    r"(invalid[ _-]?api[ _-]?key|incorrect[ _-]?api[ _-]?key|"
    r"authentication (failed|error)|unauthorized|permission denied|"
    r"invalid[ _-]?token|missing[ _-]?api[ _-]?key|"
    r"\b(401|403)\b)",
    re.I,
)


def classify_error(exc: BaseException) -> str:
    """把异常分类为 transient / auth / fatal。

    Args:
        exc: 捕获到的异常

    Returns:
        :data:`TRANSIENT` / :data:`AUTH` / :data:`FATAL`
    """
    if exc is None:
        return FATAL
    name = type(exc).__name__
    if name in _AUTH_TYPES:
        return AUTH
    if name in _TRANSIENT_TYPES:
        return TRANSIENT
    msg = str(exc) or ""
    # 凭证错误优先判定 —— "invalid api key" 里也可能带 401
    if _AUTH_RE.search(msg):
        return AUTH
    if _TRANSIENT_RE.search(msg):
        return TRANSIENT
    return FATAL


def is_transient(exc: BaseException) -> bool:
    """异常是否值得重试。"""
    return classify_error(exc) == TRANSIENT


def describe_error(exc: BaseException, limit: int = 80) -> str:
    """把异常压成一行短描述（用于重试提示）。"""
    if exc is None:
        return "未知错误"
    msg = (str(exc) or type(exc).__name__).strip().replace("\n", " ")
    if len(msg) > limit:
        msg = msg[:limit] + "…"
    return msg or type(exc).__name__


def call_with_retry(fn: Callable[[int], Any], *,
                    attempts: int = DEFAULT_RETRY + 1,
                    backoff: float = DEFAULT_BACKOFF,
                    should_retry: Optional[Callable[[BaseException], bool]] = None,
                    on_retry: Optional[Callable[[int, int, BaseException, float], None]] = None,
                    ) -> Any:
    """带指数退避的重试封装。

    Args:
        fn: 接收"第几次尝试（1-based）"并返回结果的函数；抛异常即视为失败
        attempts: 总尝试次数（含首次）
        backoff: 退避基数（秒），实际等待 = backoff * 2^(已失败次数-1)
        should_retry: 自定义"是否该重试"判定；默认按 :func:`is_transient`
        on_retry: 重试回调 ``(第几次, 总次数, 异常, 等待秒数)``

    Returns:
        fn 的返回值

    Raises:
        最后一次异常（判定为不可重试时立即抛出）
    """
    attempts = max(1, int(attempts))
    checker = should_retry if should_retry is not None else is_transient
    for i in range(attempts):
        try:
            return fn(i + 1)
        except Exception as e:
            if i == attempts - 1 or not checker(e):
                raise
            delay = max(0.0, float(backoff)) * (2 ** i)
            if on_retry:
                try:
                    on_retry(i + 1, attempts, e, delay)
                except Exception:
                    pass
            if delay:
                time.sleep(delay)
    raise RuntimeError("unreachable")


def resolve_fallback(fallback: Any) -> Optional[Tuple[Any, str]]:
    """解析降级用的备用 (client, model)。

    Args:
        fallback: 可以是
            - ``None`` → 没有降级路径
            - ``(client, model)`` 元组 → 直接用
            - 可调用对象 → 调用它拿元组（异常时视为无降级）

    Returns:
        ``(client, model)`` 或 ``None``
    """
    if fallback is None:
        return None
    target = fallback
    if callable(fallback):
        try:
            target = fallback()
        except Exception:
            return None
    if not target:
        return None
    try:
        client, model = target
    except (TypeError, ValueError):
        return None
    if client is None or not model:
        return None
    return client, model
