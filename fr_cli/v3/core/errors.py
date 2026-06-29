"""
v3 Errors —— 统一错误类型

v2.x:错误用 string 或 tuple `(result, error)`,分散在 Result / Exception / dict 之间。
v3:统一 FrCliError 基类 + 具体子类 + severity 分级。

优势:
- 可以 except 特定错误类型
- 携带上下文(trace_id / source / data)
- 可以序列化为 JSON / log
- 可以通过 EventBus 自动发布
"""
from __future__ import annotations

import traceback
from typing import Any, Dict, Optional


class FrCliError(Exception):
    """fr-cli 错误基类

    Attributes:
        message: 人类可读消息
        code: 错误代码(如 "TOOL_FAILED", "LLM_TIMEOUT")
        data: 附加上下文(dict)
        source: 错误来源(组件名)
        severity: 严重等级(info / warning / error / fatal)
        cause: 原始异常(chained)
        traceback: 完整 traceback 字符串
    """
    severity = "error"

    def __init__(self, message: str,
                 code: Optional[str] = None,
                 data: Optional[Dict[str, Any]] = None,
                 source: Optional[str] = None,
                 cause: Optional[BaseException] = None):
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__
        self.data = data or {}
        self.source = source
        self._cause = cause
        self._tb = traceback.format_exc() if cause else None

    def to_dict(self) -> Dict[str, Any]:
        """转 dict(用于日志/事件/序列化)"""
        return {
            "type": self.__class__.__name__,
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "source": self.source,
            "data": self.data,
            "cause": str(self._cause) if self._cause else None,
            "traceback": self._tb,
        }

    def __repr__(self):
        return f"{self.__class__.__name__}({self.message!r}, code={self.code!r})"

    def publish(self, bus=None):
        """发布到 EventBus(可选)"""
        try:
            from fr_cli.v3.core.events import EventBus, Events
            if bus is None:
                bus = EventBus.instance()
            bus.emit(Events.APP_STARTED.replace("started", "error"),  # 复用命名空间
                     data=self.to_dict(), source=self.source)
        except ImportError:
            pass  # 循环 import 时跳过


# ---------------- 具体错误类型 ----------------

class ConfigError(FrCliError):
    """配置错误"""
    severity = "error"


class ProviderError(FrCliError):
    """Provider(LLM / MCP / Tool)错误基类"""
    severity = "error"


class APIKeyError(ProviderError):
    """API Key 缺失或无效(v2 兼容)"""


class LLMError(ProviderError):
    """LLM 调用错误"""
    pass


class LLMTimeoutError(LLMError):
    """LLM 调用超时"""
    severity = "warning"


class LLMRateLimitError(LLMError):
    """LLM 速率限制"""
    severity = "warning"


class LLMContextOverflowError(LLMError):
    """上下文超长"""
    severity = "warning"


class ToolError(ProviderError):
    """工具调用错误"""
    pass


class ToolNotFoundError(ToolError):
    """工具不存在"""
    pass


class ToolPermissionDeniedError(ToolError):
    """权限拒绝"""
    severity = "warning"


class MCPError(ProviderError):
    """MCP 服务器错误"""
    pass


class PluginError(FrCliError):
    """插件错误"""
    pass


class SecurityError(FrCliError):
    """安全检查失败"""
    severity = "warning"


class VFSError(FrCliError):
    """虚拟文件系统错误"""
    pass


class NetworkError(FrCliError):
    """网络错误"""
    severity = "warning"


class NotFoundError(FrCliError):
    """找不到资源"""
    pass


class ValidationError(FrCliError):
    """参数验证失败"""
    pass


# ---------------- 错误聚合 / 转换 ----------------

class ErrorAggregator:
    """错误聚合器(收集多个子操作错误,不立即抛出)"""

    def __init__(self):
        self.errors: list = []

    def add(self, error: BaseException):
        """添加一个错误"""
        self.errors.append(error)

    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def to_exception(self, message: str = "Multiple errors") -> FrCliError:
        """聚合为单个异常"""
        if not self.errors:
            return FrCliError(message)
        first = self.errors[0]
        return FrCliError(
            message=f"{message} ({len(self.errors)} errors)",
            code="AGGREGATED",
            data={"errors": [str(e) for e in self.errors]},
            cause=first if isinstance(first, BaseException) else None,
        )

    def clear(self):
        self.errors.clear()


def to_frcli_error(e: BaseException, source: Optional[str] = None) -> FrCliError:
    """把任意异常转 FrCliError(已是 FrCliError 直接返回)"""
    if isinstance(e, FrCliError):
        if source and not e.source:
            e.source = source
        return e
    return FrCliError(str(e), cause=e, source=source)


def collect_errors(*funcs, reraise: bool = False):
    """运行多个函数,收集错误

    Args:
        *funcs: 可调用对象列表
        reraise: True 时把第一个错误重新抛出

    Returns:
        (results, errors): 函数返回值列表与错误列表
    """
    results = []
    errors = []
    for fn in funcs:
        try:
            results.append(fn())
        except Exception as e:
            errors.append(to_frcli_error(e))
            if reraise:
                raise errors[-1] from e
    return results, errors
