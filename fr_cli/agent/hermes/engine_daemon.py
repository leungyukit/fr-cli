"""
HermesEngine 守护进程 mixin —— HTTP daemon lifecycle

负责:
- start_daemon:启动独立 HTTP daemon 监听 8765
- stop_daemon:停止 daemon
- is_daemon_running:查询状态

daemon 实现: fr_cli.agent.hermes_daemon.HermesDaemon
"""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


class HermesEngineDaemonMixin:
    """HermesEngine HTTP 守护进程管理"""

    def start_daemon(self, port: int = 8765, host: str = "127.0.0.1") -> Any:
        """启动独立 HTTP daemon(后台线程)"""
        from fr_cli.agent.hermes_daemon import HermesDaemon
        if self._daemon is not None and getattr(self._daemon, "running", False):
            return self
        self._daemon = HermesDaemon(port=port, host=host, engine=self)
        t = threading.Thread(target=self._daemon.start, daemon=True, name="HermesDaemon")
        t.start()
        self._log(f"Hermes daemon started on {host}:{port}")
        return self

    def stop_daemon(self) -> bool:
        if self._daemon is not None:
            self._daemon.running = False
            self._daemon = None
            self._log("Hermes daemon stopped")
            return True
        return False

    def is_daemon_running(self) -> bool:
        return self._daemon is not None and getattr(self._daemon, "running", False)
