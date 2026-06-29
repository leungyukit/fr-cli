"""
RAG 知识库独立守护进程管理器

独立于 RAGManager 类,负责:
- 启动独立 daemon 进程(后台监控知识库目录)
- 停止 daemon
- 状态查询 / 日志查看

daemon 脚本本身在 fr_cli.agent.builtins.rag_watcher_daemon (独立模块)

拆分自 fr_cli/agent/builtins/rag.py(v3.0+ 重构)
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from fr_cli.conf.paths import (
    RAG_WATCHER_LOG_FILE,
    RAG_WATCHER_PID_FILE,
    RAG_WATCHER_STOP_FILE,
)


class RAGWatcherManager:
    """RAG 知识库独立守护进程管理器 —— 知识库主宰
    负责在主进程之外独立启动/停止/监控知识库文件监听守护进程。
    守护进程脱离终端运行,用户退出 fr-cli 后仍继续工作。
    """

    @staticmethod
    def _daemon_script_path():
        # 用 parent + filename 而非 with_name,确保模块搬迁后仍正确
        return Path(__file__).parent / "rag_watcher_daemon.py"

    @staticmethod
    def _read_pid():
        if RAG_WATCHER_PID_FILE.exists():
            try:
                return int(RAG_WATCHER_PID_FILE.read_text(encoding="utf-8").strip())
            except Exception:
                pass
        return None

    @staticmethod
    def _is_pid_alive(pid):
        """跨平台检测进程是否存活"""
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
        for f in (RAG_WATCHER_PID_FILE, RAG_WATCHER_STOP_FILE):
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass

    def is_running(self):
        pid = self._read_pid()
        if pid and self._is_pid_alive(pid):
            return True
        if RAG_WATCHER_PID_FILE.exists():
            self._cleanup_files()
        return False

    def start(self, kb_dir, db_path=None, interval=30):
        """启动独立守护进程"""
        if self.is_running():
            pid = self._read_pid()
            return False, f"RAG 守护进程已在运行 (PID: {pid})"

        self._cleanup_files()
        daemon_script = self._daemon_script_path()
        if not daemon_script.exists():
            return False, f"守护进程脚本不存在: {daemon_script}"

        target = Path(kb_dir)
        if not target.exists():
            return False, f"知识库目录不存在: {kb_dir}"

        try:
            kwargs = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

            cmd = [
                sys.executable, str(daemon_script),
                "--kb_dir", str(target.resolve()),
                "--interval", str(max(5, interval)),
            ]
            if db_path:
                cmd.extend(["--db_path", str(db_path)])

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                close_fds=True,
                **kwargs,
            )

            # 等待 PID 文件写入
            for _ in range(10):
                time.sleep(0.3)
                pid = self._read_pid()
                if pid and self._is_pid_alive(pid):
                    return True, f"RAG 守护进程已启动 (PID: {pid})"
                if proc.poll() is not None:
                    return False, "守护进程启动后立即退出,请检查日志: ~/.fr_cli/rag/watcher.log"

            return True, f"RAG 守护进程已启动 (PID: {proc.pid})"
        except Exception as e:
            return False, f"启动失败: {e}"

    def stop(self):
        """停止独立守护进程"""
        pid = self._read_pid()
        if not pid:
            self._cleanup_files()
            return False, "RAG 守护进程未运行。"

        if not self._is_pid_alive(pid):
            self._cleanup_files()
            return False, "RAG 守护进程未运行(已清理残留状态)。"

        # 写入停止标记
        try:
            RAG_WATCHER_STOP_FILE.write_text("1", encoding="utf-8")
        except Exception as e:
            return False, f"发送停止信号失败: {e}"

        # 等待进程自行退出
        for _ in range(15):
            if not self._is_pid_alive(pid):
                self._cleanup_files()
                return True, "RAG 守护进程已停止。"
            time.sleep(0.5)

        # 强制终止
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
                return True, "RAG 守护进程已停止。"
            time.sleep(0.5)

        self._cleanup_files()
        return True, "RAG 守护进程已强制停止。"

    def status(self):
        """查询守护进程状态"""
        pid = self._read_pid()
        if not pid:
            return "RAG 守护进程未运行。"
        if self._is_pid_alive(pid):
            return f"RAG 守护进程运行中 (PID: {pid})"
        self._cleanup_files()
        return "RAG 守护进程未运行(已清理残留状态)。"

    @staticmethod
    def get_log(lines=50):
        """读取守护进程日志最后 N 行"""
        if not RAG_WATCHER_LOG_FILE.exists():
            return "暂无日志。"
        try:
            with open(RAG_WATCHER_LOG_FILE, "r", encoding="utf-8") as f:
                all_lines = f.readlines()
            return "".join(all_lines[-lines:])
        except Exception as e:
            return f"读取日志失败: {e}"
