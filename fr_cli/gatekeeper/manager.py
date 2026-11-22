"""
Gatekeeper 管理器 —— 守护进程管理器
在主进程中控制守护进程的启动、停止与状态查询。

守护进程配置统一收敛到 ~/.fr_cli/config.json 的 gatekeeper 命名空间。
旧文件 ~/.fr_cli/daemon/config.json 会在首次加载时一次性迁移。
"""
import os
import sys
import time
import signal
import subprocess
from pathlib import Path
from fr_cli.conf import paths as _paths
from fr_cli.conf.paths import (
    DAEMON_PID_FILE,
    DAEMON_STOP_FILE,
    DAEMON_CONFIG_FILE,
    DAEMON_LOG_FILE,
)
from fr_cli.conf.config import load_namespace, save_namespace
from fr_cli.core.procutil import (
    DAEMON_HOME_FLAG,
    pid_alive,
    pid_matches_daemon,
    scan_daemon_pids,
)
from fr_cli.core.result import Result

PID_FILE = DAEMON_PID_FILE
STOP_FILE = DAEMON_STOP_FILE
# 保留用于一次性迁移（已弃用，新数据写入 ~/.fr_cli/config.json）
DAEMON_CONFIG_FILE = DAEMON_CONFIG_FILE
# 守护进程 stderr 日志（替代 DEVNULL，启动挂起时可诊断）
LOG_FILE = DAEMON_LOG_FILE

_GATEKEEPER_NS = "gatekeeper"
# 守护进程命令行标记：脚本路径最后两段，跨安装位置稳定
_DAEMON_SCRIPT_NAME = "daemon.py"


class _GatekeeperStore:
    """JsonStore 兼容接口，对应 gatekeeper 命名空间"""

    def read(self):
        return load_namespace(_GATEKEEPER_NS, default={}, old_path=DAEMON_CONFIG_FILE)

    def write(self, cfg):
        save_namespace(_GATEKEEPER_NS, cfg)


def _daemon_store():
    """返回 JsonStore 兼容的对象，用于读写 gatekeeper 命名空间"""
    return _GatekeeperStore()


class GatekeeperManager:
    """守护进程管理器"""

    def __init__(self):
        pass

    @staticmethod
    def _daemon_script_path():
        return Path(__file__).with_name(_DAEMON_SCRIPT_NAME)

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
        """进程是否存在（不校验身份）——停止等待循环用"""
        return pid_alive(pid)

    def _daemon_marker(self):
        """守护进程命令行标记（取脚本路径最后两段，跨安装位置稳定）"""
        p = self._daemon_script_path()
        parts = p.parts
        return os.sep.join(parts[-2:]) if len(parts) >= 2 else p.name

    def _daemon_home(self):
        """本实例的配置根，作为守护进程的归属标记（跨实例隔离）。

        两个 fr-cli 实例跑同一仓库时 daemon 脚本路径相同，只有这个值
        能区分「我的 daemon」和「别人的 daemon」（含沙盒 HOME 实例）。
        """
        return str(_paths.ROOT)

    def _pid_is_daemon(self, pid):
        """pid 存活且确认为本守护进程（防 pid 回收误报「在运行」）

        注意不传 home：pid 文件本身按配置根隔离，且升级前启动的旧版
        daemon（命令行无归属标记）仍要能被识别和停止。
        """
        return pid_matches_daemon(pid, self._daemon_marker())

    def _scan_daemon_pids(self):
        """扫描归属本实例的现存守护进程（别的实例/旧版无标记的一律不认）"""
        return scan_daemon_pids(self._daemon_marker(), home=self._daemon_home())

    def _adopt_running_daemon(self):
        """收养现存守护进程：把其 pid 写回 pid 文件并返回 pid。

        直接消灭「守护进程活着但没写 pid 文件 → 每次启动都再 spawn
        一个 → 进程无限累积」的链条。找不到返回 None。
        """
        for pid in self._scan_daemon_pids():
            try:
                PID_FILE.parent.mkdir(parents=True, exist_ok=True)
                PID_FILE.write_text(str(pid), encoding="utf-8")
            except Exception:
                pass
            return pid
        return None

    def _resolve_pid(self):
        """返回可信的守护进程 pid；没有则 None（顺带清理失效 pid 文件）"""
        pid = self._read_pid()
        if pid and self._pid_is_daemon(pid):
            return pid
        adopted = self._adopt_running_daemon()
        if adopted is not None:
            return adopted
        if PID_FILE.exists():
            self._cleanup_files()
        return None

    @staticmethod
    def _spawn_kwargs():
        """spawn 卫生：POSIX 独立会话，脱离终端进程组"""
        if sys.platform == "win32":
            return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        return {"start_new_session": True}

    def _open_daemon_log(self):
        """打开 stderr 日志文件；失败返回 None（调用方退化到 DEVNULL）"""
        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            return open(LOG_FILE, "a", encoding="utf-8")
        except Exception:
            return None

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
        """保存守护进程配置供下次启动使用，返回 Result"""
        try:
            store = _daemon_store()
            try:
                if store.read() == cfg:
                    return Result.ok("配置未变化，跳过写入")
            except Exception:
                pass
            store.write(cfg)
            return Result.ok("配置已保存")
        except Exception as e:
            return Result.fail(str(e))

    def is_running(self):
        return self._resolve_pid() is not None

    def start(self):
        """启动守护进程，返回 Result"""
        pid = self._resolve_pid()
        if pid:
            return Result.fail(f"Gatekeeper 守护进程已在运行 (PID: {pid})")

        self._cleanup_files()
        daemon_script = self._daemon_script_path()
        if not daemon_script.exists():
            return Result.fail(f"守护进程脚本不存在: {daemon_script}")

        log_fh = self._open_daemon_log()
        try:
            proc = subprocess.Popen(
                [sys.executable, str(daemon_script), DAEMON_HOME_FLAG, self._daemon_home()],
                stdout=subprocess.DEVNULL,
                stderr=log_fh if log_fh is not None else subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                close_fds=True,
                **self._spawn_kwargs(),
            )
        except Exception as e:
            return Result.fail(f"启动失败: {e}")
        finally:
            if log_fh is not None:
                try:
                    log_fh.close()
                except Exception:
                    pass

        # 等待 PID 文件写入
        for _ in range(10):
            time.sleep(0.3)
            pid = self._read_pid()
            if pid and self._pid_is_daemon(pid):
                return Result.ok(f"Gatekeeper 守护进程已启动 (PID: {pid})")
            if proc.poll() is not None:
                return Result.fail("守护进程启动后立即退出，请检查配置。")

        return Result.ok(f"Gatekeeper 守护进程已启动 (PID: {proc.pid})")

    def stop(self):
        """停止守护进程，返回 Result"""
        pid = self._resolve_pid()
        if not pid:
            self._cleanup_files()
            return Result.fail("Gatekeeper 守护进程未运行。")

        # 写入停止标记
        try:
            STOP_FILE.write_text("1", encoding="utf-8")
        except Exception as e:
            return Result.fail(f"发送停止信号失败: {e}")

        # 等待进程自行退出
        for _ in range(15):
            if not self._is_pid_alive(pid):
                self._cleanup_files()
                return Result.ok("Gatekeeper 守护进程已停止。")
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
                return Result.ok("Gatekeeper 守护进程已停止。")
            time.sleep(0.5)

        # SIGTERM 无效（可能卡在无法被信号中断的 C 调用里）：SIGKILL 兜底，
        # 否则挂起的守护进程会永远占着资源、且下次启动再累积一个
        try:
            if sys.platform != "win32":
                os.kill(pid, signal.SIGKILL)
        except Exception:
            pass

        for _ in range(5):
            if not self._is_pid_alive(pid):
                break
            time.sleep(0.3)

        self._cleanup_files()
        return Result.ok("Gatekeeper 守护进程已强制停止。")

    def status(self):
        """查询守护进程状态"""
        pid = self._resolve_pid()
        if pid:
            return f"Gatekeeper 守护进程运行中 (PID: {pid})"
        return "Gatekeeper 守护进程未运行。"


def get_manager():
    return GatekeeperManager()


def read_daemon_config():
    """读取当前守护进程配置"""
    return _daemon_store().read()


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
        _daemon_store().write(cfg)
        return True
    except Exception:
        return False
