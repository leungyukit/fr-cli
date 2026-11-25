"""
状态池 —— 让多个 bot 会话安全地共享 fr-cli 的运行时

v2.8.7 新增。

问题：``AppState`` 持有全局状态（messages / client / executor / security /
mcp / plugins …）。两个会话同时用同一个 state 必然串台 —— 这正是
``state.messages`` 无锁写造成的经典故障。

两种解法：

  1. **每会话一个 AppState** —— 正确但昂贵。每个 AppState 构造都会
     ``_restore_cron_jobs()`` + ``_bootstrap_dynamic_tools()`` +
     起 LLM 客户端预热，几十个会话就是几十倍开销。
  2. **状态池**（本实现）—— 预建 N 个无头 AppState，每个同一时刻只服务
     一个会话；用完归还。N 决定并发上限，且内存开销可控。

会话与状态的绑定关系由池管理，调用方不需要关心。
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Optional

__all__ = ["StatePool"]


class StatePool:
    """AppState 池（线程安全）。

    Args:
        cfg:      基础配置（会被复制后注入 headless=True）
        size:     池大小（并发上限）
        factory:  自定义构造器 ``(cfg) -> AppState``；默认用 ``fr_cli.core.core.AppState``
        lazy:     True = 首次 acquire 时才构造（启动更快）；False = 立即全部构造
    """

    def __init__(self, cfg: Dict[str, Any], size: int = 2,
                 factory: Optional[Callable[[Dict[str, Any]], Any]] = None,
                 lazy: bool = True):
        self.cfg = dict(cfg or {})
        self.size = max(1, int(size))
        self._factory = factory or self._default_factory
        self._lazy = lazy
        self._states: List[Any] = []
        self._free: List[Any] = []
        # ⚠️ 必须是 **RLock**：Condition 的底层锁在"取出状态"与"归还状态"
        # 两段里都会被重新获取。用普通 Lock 会在归还时自锁死。
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._created = 0
        self._in_use = 0
        self._closed = False

    @staticmethod
    def _default_factory(cfg: Dict[str, Any]):
        from fr_cli.core.core import AppState
        return AppState(cfg)

    def _new_state(self):
        cfg = dict(self.cfg)
        cfg["headless"] = True
        state = self._factory(cfg)
        self._created += 1
        return state

    def _ensure_pool(self) -> None:
        """按需把池补满。"""
        with self._lock:
            while self._created < self.size and not self._closed:
                self._states.append(self._new_state())
                self._free.append(self._states[-1])

    @contextmanager
    def acquire(self, timeout: Optional[float] = None):
        """借出一个状态（用完自动归还）。

        Yields:
            一个无头 AppState 实例。
        """
        if self._closed:
            raise RuntimeError("状态池已关闭")
        if not self._lazy:
            self._ensure_pool()

        with self._cond:
            while True:
                if self._free:
                    state = self._free.pop()
                    self._in_use += 1
                    break
                if self._created < self.size:
                    # 还有名额就现造一个（避免为等锁而阻塞）
                    state = self._new_state()
                    self._states.append(state)
                    self._in_use += 1
                    break
                if not self._cond.wait(timeout):
                    raise TimeoutError("等待可用状态超时（池已满）")
        # ⚠️ 必须已释放锁再 yield —— 否则调用方执行期间锁一直被占着，
        # 其他会话拿不到状态；归还时重新获取锁也可能自锁死。
        try:
            yield state
        finally:
            with self._cond:
                self._in_use -= 1
                self._free.append(state)
                self._cond.notify()

    def stats(self) -> Dict[str, Any]:
        """统计信息（用于 /bot_status）。"""
        with self._lock:
            return {
                "size": self.size,
                "created": self._created,
                "in_use": self._in_use,
                "idle": len(self._free),
            }

    def close(self) -> None:
        """关闭池（释放状态引用）。"""
        with self._cond:
            self._closed = True
            self._free.clear()
            self._states.clear()
            self._cond.notify_all()
