#!/usr/bin/env python3
"""
Hermes 独立守护进程 —— 脱离 REPL 终端的后台子进程

负责：
- 初始化 AppState 与 HermesEngine
- 启动 HTTP 任务接收接口
- 独立调度并执行后台任务
- 检测停止标记后优雅退出

启动方式（不应由用户直接调用）：
    python -m fr_cli.agent.hermes_daemon_process

停止方式：
    创建 ~/.fr_cli/hermes/daemon.stop 标记文件，守护进程检测到后自行退出。

守护进程配置从 ~/.fr_cli/config.json 的 hermes.daemon 命名空间读取；
旧文件 ~/.fr_cli/hermes/daemon.json 会在首次加载时一次性迁移。
"""

import os
import sys
import time
import signal
import atexit

# 确保项目根目录在 Python 路径中
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from fr_cli.conf.paths import (
    HERMES_DAEMON_PID_FILE,
    HERMES_DAEMON_STOP_FILE,
    HERMES_DAEMON_CONFIG_FILE,
)

PID_FILE = HERMES_DAEMON_PID_FILE
STOP_FILE = HERMES_DAEMON_STOP_FILE
# 保留用于一次性迁移（已弃用，新数据写入 ~/.fr_cli/config.json）
CONFIG_FILE = HERMES_DAEMON_CONFIG_FILE


def _write_pid(pid):
    try:
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
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


def _load_config():
    """从主配置 hermes.daemon 命名空间读取（首次会从老文件迁移）"""
    try:
        from fr_cli.conf.config import load_namespace
        cfg = load_namespace("hermes.daemon", default={"port": 8765, "host": "127.0.0.1", "lang": "zh"}, old_path=CONFIG_FILE)
        return cfg
    except Exception:
        return {"port": 8765, "host": "127.0.0.1", "lang": "zh"}


def _init_services(daemon_cfg):
    from fr_cli.conf.config import load_config
    from fr_cli.core.core import AppState

    cfg = load_config()
    state = AppState(cfg)

    port = daemon_cfg.get("port", 8765)
    host = daemon_cfg.get("host", "127.0.0.1")
    state.hermes.start_daemon(port=port, host=host)
    return state


def run_daemon():
    _clear_stop_marker()
    _write_pid(os.getpid())
    atexit.register(_cleanup)
    _setup_signal_handlers()

    daemon_cfg = _load_config()
    state = _init_services(daemon_cfg)

    # 主循环：定期检查停止标记，保持子进程存活
    while True:
        time.sleep(2)
        if STOP_FILE.exists():
            break

    # 优雅关闭
    try:
        state.hermes.shutdown()
    except Exception:
        pass

    _cleanup()


if __name__ == "__main__":
    run_daemon()
