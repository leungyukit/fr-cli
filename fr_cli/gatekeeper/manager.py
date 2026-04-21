"""
Gatekeeper 管理器 —— 结界主宰
在主进程中控制守护进程的启动、停止与状态查询。
"""
import os
import sys
import time
import json
import signal
import subprocess
from pathlib import Path

PID_FILE = Path.home() / ".fr_cli_gatekeeper.pid"
STOP_FILE = Path.home() / ".fr_cli_gatekeeper.stop"
DAEMON_CONFIG_FILE = Path.home() / ".fr_cli_gatekeeper.json"


class GatekeeperManager:
    """守护进程管理器"""

    def __init__(self):
        pass

    @staticmethod
    def _daemon_script_path():
        return Path(__file__).with_name("daemon.py")

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
        for f in (PID_FILE, STOP_FILE):
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass

    @staticmethod
    def save_daemon_config(cfg):
        """保存守护进程配置供下次启动使用"""
        try:
            with open(DAEMON_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            return False, str(e)
        return True, "配置已保存"

    def is_running(self):
        pid = self._read_pid()
        if pid and self._is_pid_alive(pid):
            return True
        # 残留文件清理
        if PID_FILE.exists():
            self._cleanup_files()
        return False

    def start(self):
        """启动守护进程"""
        if self.is_running():
            pid = self._read_pid()
            return False, f"Gatekeeper 守护进程已在运行 (PID: {pid})"

        self._cleanup_files()
        daemon_script = self._daemon_script_path()
        if not daemon_script.exists():
            return False, f"守护进程脚本不存在: {daemon_script}"

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
                **kwargs
            )

            # 等待 PID 文件写入
            for _ in range(10):
                time.sleep(0.3)
                pid = self._read_pid()
                if pid and self._is_pid_alive(pid):
                    return True, f"Gatekeeper 守护进程已启动 (PID: {pid})"
                if proc.poll() is not None:
                    return False, "守护进程启动后立即退出，请检查配置。"

            return True, f"Gatekeeper 守护进程已启动 (PID: {proc.pid})"
        except Exception as e:
            return False, f"启动失败: {e}"

    def stop(self):
        """停止守护进程"""
        pid = self._read_pid()
        if not pid:
            self._cleanup_files()
            return False, "Gatekeeper 守护进程未运行。"

        if not self._is_pid_alive(pid):
            self._cleanup_files()
            return False, "Gatekeeper 守护进程未运行（已清理残留状态）。"

        # 写入停止标记
        try:
            STOP_FILE.write_text("1", encoding="utf-8")
        except Exception as e:
            return False, f"发送停止信号失败: {e}"

        # 等待进程自行退出
        for _ in range(15):
            if not self._is_pid_alive(pid):
                self._cleanup_files()
                return True, "Gatekeeper 守护进程已停止。"
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

        # 再等待一次
        for _ in range(5):
            if not self._is_pid_alive(pid):
                self._cleanup_files()
                return True, "Gatekeeper 守护进程已停止。"
            time.sleep(0.5)

        self._cleanup_files()
        return True, "Gatekeeper 守护进程已强制停止。"

    def status(self):
        """查询守护进程状态"""
        pid = self._read_pid()
        if not pid:
            return "Gatekeeper 守护进程未运行。"
        if self._is_pid_alive(pid):
            return f"Gatekeeper 守护进程运行中 (PID: {pid})"
        self._cleanup_files()
        return "Gatekeeper 守护进程未运行（已清理残留状态）。"


def get_manager():
    return GatekeeperManager()


def read_daemon_config():
    """读取当前守护进程配置"""
    if DAEMON_CONFIG_FILE.exists():
        try:
            with open(DAEMON_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def sync_gatekeeper_cron_jobs(cron_jobs=None, agent_crons=None, append=False):
    """同步定时任务配置到 gatekeeper 配置文件。

    Args:
        cron_jobs: shell 类型任务列表，每项为 dict
        agent_crons: Agent 类型任务列表，每项为 dict
        append: 是否追加模式（False 则替换对应字段）
    """
    cfg = read_daemon_config()
    if cron_jobs is not None and not append:
        cfg["cron_jobs"] = cron_jobs
    elif cron_jobs is not None and append:
        existing = cfg.get("cron_jobs", [])
        cfg["cron_jobs"] = existing + [j for j in cron_jobs if j not in existing]

    if agent_crons is not None and not append:
        cfg["agent_crons"] = agent_crons
    elif agent_crons is not None and append:
        existing = cfg.get("agent_crons", [])
        cfg["agent_crons"] = existing + [j for j in agent_crons if j not in existing]

    try:
        with open(DAEMON_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False
