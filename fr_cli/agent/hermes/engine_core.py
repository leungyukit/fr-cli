"""
HermesEngine 核心 mixin —— 初始化 / 日志 / 关闭

负责:
- __init__:组装 task_manager / goal_tracker / memory_store / analytics / scheduler
- _log / _log_error:统一日志入口
- shutdown:关闭调度器与守护进程
"""
from __future__ import annotations

import time
from typing import Any, Callable, Optional

from fr_cli.conf.paths import HERMES_DIR, HERMES_LOG_FILE


# 单个 Hermes 后台任务最大执行时间(秒)
DEFAULT_TASK_TIMEOUT = 300


class HermesEngineCoreMixin:
    """HermesEngine 核心:初始化 + 日志 + 关闭"""

    def _init_engine(self, state_provider: Callable[[], Any]):
        """初始化引擎实例(由 __init__ 委托,避免 mixin __init__ 冲突)"""
        self.state_provider = state_provider
        self.task_manager = None      # 由 managers mixin 注入
        self.goal_tracker = None
        self.memory_store = None
        self.analytics = None
        self.scheduler = None
        self._daemon: Optional[Any] = None

    def _log(self, message: str):
        """统一日志入口(写到 ~/.fr_cli/hermes/hermes.log)"""
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {message}\n"
        try:
            HERMES_DIR.mkdir(parents=True, exist_ok=True)
            with open(HERMES_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass

    def _log_error(self, message: str):
        self._log(f"[ERROR] {message}")

    def shutdown(self):
        """完全关闭 Hermes 引擎(停止调度器和守护进程)"""
        if getattr(self, "scheduler", None) is not None:
            self.scheduler.stop()
        if hasattr(self, "stop_daemon"):
            self.stop_daemon()
        self._log("Hermes engine shutdown")
