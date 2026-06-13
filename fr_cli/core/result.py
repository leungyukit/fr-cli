"""
统一错误返回风格 —— Result 容器

目标：逐步将项目中混乱的返回风格收敛为单一形式：
  - 旧风格 1: (result, error) 元组
  - 旧风格 2: (success, message) 元组
  - 旧风格 3: 直接抛异常
  - 旧风格 4: 返回 None / bool 并打印错误

新风格：函数返回 Result 对象
  Result.ok(data)    -> 操作成功，data 为有效载荷
  Result.fail(error) -> 操作失败，error 为错误描述

迁移策略：
  - 新增代码优先使用 Result
  - 边界清晰的模块可逐步重构
  - 与 registry/executor 交互的函数，可在边界处用 to_tuple()/from_tuple() 兼容旧接口
"""
from typing import Any, Optional, Tuple


class Result:
    """统一结果容器"""

    __slots__ = ("_ok", "_data", "_error")

    def __init__(self, ok: bool, data: Any = None, error: Optional[str] = None):
        self._ok = ok
        self._data = data
        self._error = error

    @staticmethod
    def ok(data: Any = None) -> "Result":
        """构造成功结果"""
        return Result(True, data, None)

    @staticmethod
    def fail(error: str) -> "Result":
        """构造失败结果"""
        return Result(False, None, error)

    @property
    def data(self) -> Any:
        return self._data

    @property
    def error(self) -> Optional[str]:
        return self._error

    def is_ok(self) -> bool:
        return self._ok

    def is_fail(self) -> bool:
        return not self._ok

    def unwrap(self) -> Any:
        """成功时返回 data；失败时抛 RuntimeError"""
        if self.is_fail():
            raise RuntimeError(self._error or "Result unwrap failed")
        return self._data

    def unwrap_or(self, default: Any) -> Any:
        """成功时返回 data；失败时返回 default"""
        return self._data if self._ok else default

    def to_tuple(self) -> Tuple[Any, Optional[str]]:
        """转换为 (data, error) 元组，兼容旧接口"""
        return self._data, self._error

    @classmethod
    def from_tuple(cls, data: Any, error: Optional[str]) -> "Result":
        """从 (data, error) 元组构造 Result"""
        if error is not None:
            return cls.fail(error)
        return cls.ok(data)

    def __iter__(self):
        """支持 `data, error = result` 元组解包，兼容旧接口"""
        return iter((self._data, self._error))

    def __repr__(self) -> str:
        if self._ok:
            return f"Result.ok({self._data!r})"
        return f"Result.fail({self._error!r})"
