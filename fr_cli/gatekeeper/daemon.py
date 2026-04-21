"""
Gatekeeper 守护进程 —— 后台结界主宰
负责在主进程退出后继续维持核心服务运转。
支持：Agent HTTP 服务、全局定时任务（shell/agent）、配置热重载。

启动方式（不应由用户直接调用）：
    python -m fr_cli.gatekeeper.daemon

停止方式：
    创建 ~/.fr_cli_gatekeeper.stop 标记文件，守护进程检测到后自行退出。
"""
import os
import sys
import time
import json
import signal
import atexit
from pathlib import Path

# 确保项目根目录在 Python 路径中
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

PID_FILE = Path.home() / ".fr_cli_gatekeeper.pid"
STOP_FILE = Path.home() / ".fr_cli_gatekeeper.stop"
DAEMON_CONFIG_FILE = Path.home() / ".fr_cli_gatekeeper.json"

# 配置热重载间隔（秒）
RELOAD_INTERVAL = 30


def _write_pid(pid):
    try:
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(pid))
    except Exception:
        pass


def _clear_stop_marker():
    if STOP_FILE.exists():
        try:
            STOP_FILE.unlink()
        except Exception:
            pass


def _cleanup():
    _clear_stop_marker()
    if PID_FILE.exists():
        try:
            PID_FILE.unlink()
        except Exception:
            pass


def _setup_signal_handlers():
    def _sigterm_handler(signum, frame):
        _cleanup()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _sigterm_handler)
    if hasattr(signal, "SIGINT"):
        signal.signal(signal.SIGINT, _sigterm_handler)


def _load_daemon_config():
    if DAEMON_CONFIG_FILE.exists():
        try:
            with open(DAEMON_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _reload_cron_jobs(cron_mgr, daemon_cfg, state):
    """热重载定时任务配置：对比当前运行任务与配置文件，增删同步。"""
    cfg_jobs = daemon_cfg.get("cron_jobs", [])
    # 过滤出 shell 类型的全局定时任务
    shell_jobs = [j for j in cfg_jobs if j.get("job_type", "shell") == "shell"]
    cron_mgr.sync_jobs(shell_jobs, lang=daemon_cfg.get("lang", "zh"))


def _reload_agent_crons(cron_mgr, daemon_cfg, state):
    """热重载 Agent 分身定时任务：对比当前运行任务与配置文件，增删同步。"""
    import copy
    cfg_jobs = daemon_cfg.get("agent_crons", [])
    # 深拷贝避免修改原始配置 dict，防止无限重载循环
    cfg_jobs = copy.deepcopy(cfg_jobs)
    for j in cfg_jobs:
        j["job_type"] = "agent"
    cron_mgr.sync_jobs(cfg_jobs, lang=daemon_cfg.get("lang", "zh"), state=state)


def _init_services(daemon_cfg):
    """初始化并启动核心子系统"""
    from fr_cli.conf.config import load_config
    from fr_cli.core.core import AppState
    from fr_cli.agent.server import AgentHTTPServer
    from fr_cli.weapon.cron import CronManager

    # 加载用户主配置（不触发交互式向导）
    cfg = load_config()
    state = AppState(cfg)

    services = {
        "state": state,
        "agent_server": None,
        "cron_manager": None,
    }

    # 启动 Agent HTTP 服务
    agent_port = daemon_cfg.get("agent_server_port")
    if agent_port:
        try:
            agent_port = int(agent_port)
            agent_server = AgentHTTPServer(state, port=agent_port)
            ok, msg = agent_server.start()
            if ok:
                services["agent_server"] = agent_server
        except Exception:
            pass

    # 初始化 CronManager 并恢复所有定时任务
    cron_mgr = CronManager()

    # 恢复 shell 类型全局定时任务
    cron_jobs = daemon_cfg.get("cron_jobs", [])
    for job in cron_jobs:
        try:
            jtype = job.get("job_type", "shell")
            if jtype == "shell":
                cron_mgr.add_job(
                    cmd=job["cmd"],
                    interval=job["interval"],
                    lang=job.get("lang", "zh"),
                    job_type="shell",
                )
        except Exception:
            pass

    # 恢复 Agent 分身定时任务（需要 AppState）
    agent_crons = daemon_cfg.get("agent_crons", [])
    for job in agent_crons:
        try:
            cron_mgr.add_job(
                cmd=job.get("cmd", job.get("agent_name", "")),
                interval=job["interval"],
                lang=job.get("lang", "zh"),
                job_type="agent",
                agent_name=job.get("agent_name"),
                agent_input=job.get("agent_input", ""),
                state=state,
            )
        except Exception:
            pass

    services["cron_manager"] = cron_mgr
    return services


def run_daemon():
    """守护进程主循环"""
    _clear_stop_marker()
    _write_pid(os.getpid())
    atexit.register(_cleanup)
    _setup_signal_handlers()

    daemon_cfg = _load_daemon_config()
    services = _init_services(daemon_cfg)
    cron_mgr = services["cron_manager"]
    state = services["state"]

    last_reload = time.time()

    # 主循环：定期检查停止标记 + 热重载配置
    while True:
        time.sleep(2)

        if STOP_FILE.exists():
            break

        # 每 RELOAD_INTERVAL 秒热重载一次配置
        if time.time() - last_reload >= RELOAD_INTERVAL:
            last_reload = time.time()
            new_cfg = _load_daemon_config()
            if new_cfg != daemon_cfg:
                daemon_cfg = new_cfg
                _reload_cron_jobs(cron_mgr, daemon_cfg, state)
                _reload_agent_crons(cron_mgr, daemon_cfg, state)

    # 停止所有子服务
    agent_server = services.get("agent_server")
    if agent_server and getattr(agent_server, "is_running", lambda: False)():
        try:
            agent_server.stop()
        except Exception:
            pass

    # 取消所有定时任务
    cron_mgr = services.get("cron_manager")
    if cron_mgr:
        for job in list(cron_mgr.jobs):
            if job.get("timer"):
                try:
                    job["timer"].cancel()
                except Exception:
                    pass

    _cleanup()


if __name__ == "__main__":
    run_daemon()
