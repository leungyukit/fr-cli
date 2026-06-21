"""
Hermes 独立守护进程管理器 —— 在主进程中控制 Hermes 后台子进程。

用法（内部）：
    manager = HermesManager()
    manager.start(port=8765)
    manager.stop()
    manager.is_running()
    manager.status()
"""

import os
import sys
import time
import signal
import subprocess
from pathlib import Path

from fr_cli.conf.paths import (
    HERMES_DAEMON_PID_FILE,
    HERMES_DAEMON_STOP_FILE,
    HERMES_DAEMON_CONFIG_FILE,
)
from fr_cli.core.result import Result
from fr_cli.core.store import JsonStore

PID_FILE = HERMES_DAEMON_PID_FILE
STOP_FILE = HERMES_DAEMON_STOP_FILE
CONFIG_FILE = HERMES_DAEMON_CONFIG_FILE


def _config_store():
    return JsonStore(CONFIG_FILE, default=dict)


def _write_pid(pid):
    try:
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(pid))
    except Exception:
        pass


class HermesManager:
    """Hermes 守护进程管理器"""

    @staticmethod
    def _daemon_script_path():
        return Path(__file__).with_name("hermes_daemon_process.py")

    @staticmethod
    def _read_pid():
        if PID_FILE.exists():
            try:
                return int(PID_FILE.read_text(encoding="utf-8").strip())
            except Exception:
                pass
        return None

    @staticmethod
    def _is_pid_alive(pid):
        try:
            if sys.platform == "win32":
                import ctypes
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(1, False, pid)
                if handle:
                    kernel32.CloseHandle(handle)
                    return True
                return False
            else:
                os.kill(pid, 0)
                return True
        except (OSError, ProcessLookupError):
            return False

    @staticmethod
    def _cleanup_files():
        for f in (PID_FILE, STOP_FILE):
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass

    def is_running(self):
        pid = self._read_pid()
        if pid and self._is_pid_alive(pid):
            return True
        if PID_FILE.exists():
            self._cleanup_files()
        return False

    def save_config(self, cfg):
        try:
            _config_store().write(cfg)
            return Result.ok("配置已保存")
        except Exception as e:
            return Result.fail(str(e))

    def start(self, port=8765, host="127.0.0.1", lang="zh"):
        """启动独立 Hermes 守护进程，返回 Result"""
        if self.is_running():
            pid = self._read_pid()
            return Result.fail(f"Hermes 守护进程已在运行 (PID: {pid})")

        self._cleanup_files()
        daemon_script = self._daemon_script_path()
        if not daemon_script.exists():
            return Result.fail(f"守护进程脚本不存在: {daemon_script}")

        # 持久化启动配置
        cfg = {"port": port, "host": host, "lang": lang}
        self.save_config(cfg)

        try:
            kwargs = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

            proc = subprocess.Popen(
                [sys.executable, str(daemon_script)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                close_fds=True,
                **kwargs,
            )

            for _ in range(10):
                time.sleep(0.3)
                pid = self._read_pid()
                if pid and self._is_pid_alive(pid):
                    return Result.ok(f"Hermes 守护进程已启动 (PID: {pid})")
                if proc.poll() is not None:
                    return Result.fail("Hermes 守护进程启动后立即退出，请检查配置。")

            return Result.ok(f"Hermes 守护进程已启动 (PID: {proc.pid})")
        except Exception as e:
            return Result.fail(f"启动失败: {e}")

    def stop(self):
        """停止独立 Hermes 守护进程，返回 Result"""
        pid = self._read_pid()
        if not pid:
            self._cleanup_files()
            return Result.fail("Hermes 守护进程未运行。")

        if not self._is_pid_alive(pid):
            self._cleanup_files()
            return Result.fail("Hermes 守护进程未运行（已清理残留状态）。")

        try:
            STOP_FILE.write_text("1", encoding="utf-8")
        except Exception as e:
            return Result.fail(f"发送停止信号失败: {e}")

        for _ in range(15):
            if not self._is_pid_alive(pid):
                self._cleanup_files()
                return Result.ok("Hermes 守护进程已停止。")
            time.sleep(0.5)

        try:
            if sys.platform == "win32":
                os.kill(pid, signal.CTRL_BREAK_EVENT)
            else:
                os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except Exception:
            pass

        for _ in range(5):
            if not self._is_pid_alive(pid):
                self._cleanup_files()
                return Result.ok("Hermes 守护进程已停止。")
            time.sleep(0.5)

        self._cleanup_files()
        return Result.ok("Hermes 守护进程已强制停止。")

    def status(self):
        pid = self._read_pid()
        if not pid:
            return "Hermes 守护进程未运行。"
        if self._is_pid_alive(pid):
            return f"Hermes 守护进程运行中 (PID: {pid})"
        self._cleanup_files()
        return "Hermes 守护进程未运行（已清理残留状态）。"


def get_manager():
    return HermesManager()


def read_daemon_config():
    return _config_store().read()
