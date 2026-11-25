"""
Bot 进程管理 —— 启停独立守护进程

v2.8.7 新增。

照抄 ``fr_cli/agent/hermes_manager.py`` 的成熟范式：
  - ``subprocess.Popen`` + ``start_new_session=True``（POSIX 脱离终端）
  - 停止顺序：停止标记 → 等待 → SIGTERM → SIGKILL
  - PID 文件判定存活
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

__all__ = ["BotManager"]


def _paths():
    from fr_cli.conf.paths import (
        BOT_LOG_FILE, BOT_PID_FILE, BOT_STOP_FILE, BOT_TOKEN_FILE,
    )
    return (Path(BOT_PID_FILE), Path(BOT_STOP_FILE),
            Path(BOT_LOG_FILE), Path(BOT_TOKEN_FILE))


PID_FILE, STOP_FILE, LOG_FILE, TOKEN_FILE = _paths()


class BotManager:
    """Bot 守护进程的启停管理。"""

    def __init__(self):
        self._proc: Optional[subprocess.Popen] = None

    # ---------- 状态 ----------

    def _read_pid(self) -> Optional[int]:
        try:
            if PID_FILE.exists():
                return int(PID_FILE.read_text(encoding="utf-8").strip())
        except Exception:
            return None
        return None

    @staticmethod
    def _alive(pid: int) -> bool:
        """判断进程是否存活。

        注意：僵尸进程对 ``os.kill(pid, 0)`` 仍返回成功。若不回收子进程，
        已退出的守护进程会被误判为"还活着" —— 停止流程就会一路走到
        SIGKILL，还留下僵尸。这里先尝试非阻塞回收自己的子进程。
        """
        try:
            # 若是本进程的子进程，顺手回收（避免僵尸）
            reaped, _status = os.waitpid(pid, os.WNOHANG)
            if reaped == pid:
                return False
        except ChildProcessError:
            pass  # 不是本进程的子进程，走下面的探测
        except (OSError, AttributeError):
            pass
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False
        except Exception:
            return False

    def is_running(self) -> bool:
        pid = self._read_pid()
        return bool(pid and self._alive(pid))

    def status(self) -> Dict[str, Any]:
        pid = self._read_pid()
        running = bool(pid and self._alive(pid))
        info: Dict[str, Any] = {
            "running": running,
            "pid": pid if running else None,
            "pid_file": str(PID_FILE),
            "log_file": str(LOG_FILE),
            "stop_file": str(STOP_FILE),
        }
        if running:
            try:
                info["cmdline"] = Path(f"/proc/{pid}/cmdline").read_bytes().decode(
                    "utf-8", errors="replace").replace("\x00", " ").strip()
            except Exception:
                pass
        return info

    # ---------- 启停 ----------

    def start(self, host: Optional[str] = None, port: Optional[int] = None,
              wait: float = 10.0) -> Dict[str, Any]:
        """拉起守护进程。

        等待条件是**网关健康检查通过**，而不是 PID 文件出现 ——
        守护进程先写 PID 再起网关，只等 PID 会让调用方在网关监听前
        就发请求，直接连接被拒。
        """
        if self.is_running():
            return {"ok": False, "error": f"Bot 已在运行 (pid={self._read_pid()})"}

        # 清掉旧的停止标记
        try:
            if STOP_FILE.exists():
                STOP_FILE.unlink()
        except Exception:
            pass

        # 未显式指定时,用配置里的 host/port —— 守护进程读的也是配置，
        # 探测端口必须一致，否则会一直探错端口(表现为"启动超时")
        if host is None or port is None:
            try:
                from fr_cli.bot.runtime.engine import load_bot_config
                bot_cfg = load_bot_config()
                host = host or bot_cfg.get("host") or "127.0.0.1"
                port = port or int(bot_cfg.get("port") or 8790)
            except Exception:
                host = host or "127.0.0.1"
                port = port or 8790

        cmd = [sys.executable, "-m", "fr_cli.bot.runtime.daemon"]
        if host:
            cmd += ["--host", str(host)]
        if port:
            cmd += ["--port", str(int(port))]

        try:
            kwargs: Dict[str, Any] = {"cwd": str(Path.cwd())}
            if os.name == "posix":
                kwargs["start_new_session"] = True
            else:  # pragma: no cover - Windows
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                **kwargs,
            )
        except Exception as e:
            return {"ok": False, "error": f"启动失败: {e}"}

        # 等待网关就绪
        deadline = time.time() + max(2.0, wait)
        while time.time() < deadline:
            if self._proc.poll() is not None:
                return {"ok": False, "error": f"进程已退出 (code={self._proc.returncode})，"
                                            f"查看日志: {LOG_FILE}"}
            if self._healthy(host, port):
                return {"ok": True, "pid": self._read_pid(),
                        "url": f"http://{host}:{port}"}
            time.sleep(0.25)

        return {"ok": False, "error": f"启动超时，请查看日志: {LOG_FILE}"}

    @staticmethod
    def _healthy(host: Optional[str], port: Optional[int], timeout: float = 1.0) -> bool:
        """探测网关健康端点。"""
        import urllib.error
        import urllib.request

        target = f"http://{host or '127.0.0.1'}:{port or 8790}/bot/health"
        try:
            with urllib.request.urlopen(target, timeout=timeout) as resp:
                return resp.status == 200
        except Exception:
            return False

    def stop(self, timeout: float = 5.0) -> Dict[str, Any]:
        """停止守护进程。"""
        pid = self._read_pid()
        if not pid or not self._alive(pid):
            # 清理残留
            try:
                if STOP_FILE.exists():
                    STOP_FILE.unlink()
                if PID_FILE.exists():
                    PID_FILE.unlink()
            except Exception:
                pass
            return {"ok": False, "error": "Bot 未运行"}

        # 1) 停止标记
        try:
            STOP_FILE.parent.mkdir(parents=True, exist_ok=True)
            STOP_FILE.write_text("stop", encoding="utf-8")
        except Exception:
            pass

        # 2) 等待优雅退出
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self._alive(pid):
                return {"ok": True, "note": "已优雅退出"}
            time.sleep(0.2)

        # 3) SIGTERM
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
        deadline = time.time() + 3
        while time.time() < deadline:
            if not self._alive(pid):
                return {"ok": True, "note": "已通过 SIGTERM 退出"}
            time.sleep(0.2)

        # 4) SIGKILL
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass
        time.sleep(0.3)
        return {"ok": True, "note": "已强制终止"}

    def log(self, lines: int = 50) -> str:
        """读取日志尾部。"""
        try:
            if not LOG_FILE.exists():
                return "(暂无日志)"
            content = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
            return "\n".join(content[-max(1, lines):])
        except Exception as e:
            return f"(读取日志失败: {e})"
