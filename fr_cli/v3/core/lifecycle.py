"""
v3 Lifecycle —— App 生命周期管理

v2.x:启动流程散落在 main.py + bootstrap.py + autostart.py 等多个文件
v3:统一 App 类 + lifecycle 阶段(starting / started / stopping / stopped)

每个阶段触发 EventBus 事件,插件/服务可订阅并在对应阶段做事。
"""
from __future__ import annotations

import atexit
import logging
import signal
import sys
import threading
from enum import Enum
from typing import Callable, List, Optional

log = logging.getLogger(__name__)


class LifecyclePhase(str, Enum):
    """应用生命周期阶段"""
    NEW = "new"
    STARTING = "starting"
    STARTED = "started"
    STOPPING = "stopping"
    STOPPED = "stopped"


class Lifecycle:
    """生命周期管理器(支持钩子)"""

    def __init__(self, name: str = "app"):
        self.name = name
        self.phase = LifecyclePhase.NEW
        self._hooks: dict = {}  # phase -> list[hook]
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._stop_callbacks: List[Callable] = []

    def add_hook(self, phase: LifecyclePhase, hook: Callable,
                 priority: int = 0) -> Callable:
        """添加钩子(在指定阶段执行)"""
        with self._lock:
            self._hooks.setdefault(phase, []).append((priority, hook))
            self._hooks[phase].sort(key=lambda x: -x[0])
        return hook

    def on_starting(self, hook: Callable, priority: int = 0) -> Callable:
        return self.add_hook(LifecyclePhase.STARTING, hook, priority)

    def on_started(self, hook: Callable, priority: int = 0) -> Callable:
        return self.add_hook(LifecyclePhase.STARTED, hook, priority)

    def on_stopping(self, hook: Callable, priority: int = 0) -> Callable:
        return self.add_hook(LifecyclePhase.STOPPING, hook, priority)

    def on_stopped(self, hook: Callable, priority: int = 0) -> Callable:
        return self.add_hook(LifecyclePhase.STOPPED, hook, priority)

    def _run_hooks(self, phase: LifecyclePhase, *args, **kwargs):
        """运行一个阶段的所有钩子"""
        with self._lock:
            hooks = list(self._hooks.get(phase, []))
        for _, hook in hooks:
            try:
                hook(*args, **kwargs)
            except Exception as e:
                log.error(f"lifecycle hook {hook} in {phase.value} failed: {e}",
                          exc_info=True)

    def start(self, *args, **kwargs):
        """启动(运行 STARTING → STARTED)"""
        if self.phase != LifecyclePhase.NEW:
            log.warning(f"lifecycle already {self.phase.value}, skip start")
            return
        log.info(f"[{self.name}] starting")
        self.phase = LifecyclePhase.STARTING
        self._run_hooks(LifecyclePhase.STARTING, *args, **kwargs)

        # 注册退出钩子
        atexit.register(self._atexit_cleanup)

        log.info(f"[{self.name}] started")
        self.phase = LifecyclePhase.STARTED
        self._run_hooks(LifecyclePhase.STARTED, *args, **kwargs)

        # 注册信号处理(macOS/Linux)
        self._register_signals()

    def stop(self, *args, **kwargs):
        """停止(运行 STOPPING → STOPPED)"""
        if self.phase not in (LifecyclePhase.STARTED, LifecyclePhase.STARTING):
            log.warning(f"lifecycle {self.phase.value}, skip stop")
            return
        log.info(f"[{self.name}] stopping")
        self.phase = LifecyclePhase.STOPPING
        self._run_hooks(LifecyclePhase.STOPPING, *args, **kwargs)

        log.info(f"[{self.name}] stopped")
        self.phase = LifecyclePhase.STOPPED
        self._run_hooks(LifecyclePhase.STOPPED, *args, **kwargs)

        # 标记 stop event
        self._stop_event.set()

        # 执行 stop callbacks
        for cb in self._stop_callbacks:
            try:
                cb()
            except Exception:
                pass

    def _atexit_cleanup(self):
        """进程退出时清理"""
        if self.phase in (LifecyclePhase.STARTED, LifecyclePhase.STARTING):
            try:
                self.stop()
            except Exception:
                pass

    def _register_signals(self):
        """注册 SIGINT/SIGTERM 处理"""
        def handler(signum, frame):
            log.info(f"received signal {signum}, stopping...")
            self.stop()
            sys.exit(0)
        try:
            signal.signal(signal.SIGINT, handler)
            signal.signal(signal.SIGTERM, handler)
        except (ValueError, OSError):
            # 不在主线程或不支持
            pass

    def on_stop(self, callback: Callable):
        """注册 stop callback(用于非 lifecycle 钩子的清理)"""
        self._stop_callbacks.append(callback)

    def wait_stop(self, timeout: Optional[float] = None) -> bool:
        """阻塞直到 stop"""
        return self._stop_event.wait(timeout=timeout)

    @property
    def is_running(self) -> bool:
        return self.phase in (LifecyclePhase.STARTED, LifecyclePhase.STARTING)


class App:
    """应用门面

    统一访问:
    - lifecycle(生命周期)
    - container(可注入服务)
    - event_bus(事件)

    保留向后兼容:
    - app.state: 类似 v2 AppState 的轻量 facade
    """

    _instances: List["App"] = []

    def __init__(self, name: str = "fr-cli"):
        self.name = name
        self.lifecycle = Lifecycle(name)
        self.container = None  # type: ignore  # Container, 避免循环 import
        try:
            from fr_cli.v3.core.container import Container
            self.container = Container()
        except ImportError:
            pass
        self.event_bus = None  # EventBus
        try:
            from fr_cli.v3.core.events import EventBus
            self.event_bus = EventBus.instance()
        except ImportError:
            pass
        self._state = None  # 兼容 v2 AppState
        App._instances.append(self)

    def start(self, state=None):
        """启动应用"""
        self._state = state
        self.lifecycle.start()

    def stop(self):
        self.lifecycle.stop()

    def run(self, state=None):
        """启动并阻塞"""
        self.start(state=state)
        self.lifecycle.wait_stop()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stop()

    @property
    def state(self):
        """兼容 v2 AppState"""
        if self._state is not None:
            return self._state
        # 自动构建轻量 state
        try:
            from fr_cli.core.core import AppState
            self._state = AppState()
            return self._state
        except Exception:
            return None
