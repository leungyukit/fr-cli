"""
Bot 守护进程 —— 脱离 REPL 独立运行

v2.8.7 新增。

用法::

    python -m fr_cli.bot.runtime.daemon --host 127.0.0.1 --port 8790

进程模型（照抄 ``fr_cli/agent/builtins/rag_watcher_daemon.py`` 的成熟范式）：
  - pid 文件：``~/.fr_cli/bot/bot.pid``
  - 停止标记：``~/.fr_cli/bot/bot.stop``（主循环每 2 秒检查）
  - 日志：``~/.fr_cli/bot/bot.log``
  - SIGTERM / SIGINT → 清理后退出
  - 启动看门狗：120 秒内没进主循环就自裁（防止半死不活）
"""
from __future__ import annotations

import argparse
import atexit
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

__all__ = ["run_daemon", "main"]

#: 停止检查间隔（秒）
POLL_INTERVAL = 2
#: 启动看门狗（秒）
WATCHDOG = 120


def _paths():
    from fr_cli.conf.paths import (
        BOT_LOG_FILE, BOT_PID_FILE, BOT_STOP_FILE,
    )
    return Path(BOT_PID_FILE), Path(BOT_STOP_FILE), Path(BOT_LOG_FILE)


PID_FILE, STOP_FILE, LOG_FILE = _paths()


def _log(msg: str) -> None:
    """写日志文件并输出到 stderr。"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    try:
        sys.stderr.write(line + "\n")
        sys.stderr.flush()
    except Exception:
        pass


def _write_pid(pid: int) -> None:
    try:
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(pid), encoding="utf-8")
    except Exception as e:
        _log(f"写入 PID 文件失败: {e}")


def _clear_stop_marker() -> None:
    try:
        if STOP_FILE.exists():
            STOP_FILE.unlink()
    except Exception:
        pass


def _cleanup() -> None:
    _clear_stop_marker()
    try:
        if PID_FILE.exists():
            PID_FILE.unlink()
    except Exception:
        pass
    _log("Bot 守护进程已清理并退出。")


def _setup_signal_handlers() -> None:
    def _handler(signum, frame):
        _log(f"收到信号 {signum}，准备退出...")
        _cleanup()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _handler)
    if hasattr(signal, "SIGINT"):
        signal.signal(signal.SIGINT, _handler)


def _parse_args():
    parser = argparse.ArgumentParser(description="fr-cli Bot 守护进程")
    parser.add_argument("--host", default=None, help="监听地址（默认读配置）")
    parser.add_argument("--port", type=int, default=None, help="监听端口（默认读配置）")
    return parser.parse_args()


def run_daemon() -> int:
    """守护进程主函数。"""
    args = _parse_args()

    _clear_stop_marker()
    _write_pid(os.getpid())
    atexit.register(_cleanup)
    _setup_signal_handlers()

    _log("=" * 56)
    _log("fr-cli Bot 守护进程启动")
    _log("=" * 56)

    # 配置
    try:
        from fr_cli.conf.config import init_config
        cfg = init_config()
    except Exception as e:
        _log(f"加载主配置失败: {e}")
        _cleanup()
        return 1

    try:
        from fr_cli.bot.runtime.engine import BotEngine, load_bot_config
        bot_cfg = load_bot_config()
        if args.host:
            bot_cfg["host"] = args.host
        if args.port:
            bot_cfg["port"] = args.port

        engine = BotEngine(cfg, bot_cfg)
        dispatcher, gateway = engine.build()
    except Exception as e:
        _log(f"初始化失败: {e}")
        _cleanup()
        return 1

    try:
        result = gateway.start()
    except Exception as e:
        _log(f"网关启动异常: {e}")
        _cleanup()
        return 1

    if not result.get("ok"):
        _log(f"网关启动失败: {result.get('error')}")
        _cleanup()
        return 1

    _log(f"网关地址: {result.get('url')}")
    _log(f"访问令牌: {result.get('token')}")
    _log(f"已启用通道: {', '.join(result.get('channels') or []) or '无'}")
    _log(f"入站路径: POST {result.get('url')}/bot/<channel>")
    _log("-" * 56)

    started = time.time()
    while True:
        time.sleep(POLL_INTERVAL)
        if STOP_FILE.exists():
            _log("检测到停止标记，准备退出...")
            break
        # 看门狗：正常情况下主循环一直在跑，这里只做兜底心跳
        if time.time() - started > WATCHDOG:
            _log("看门狗心跳正常，继续运行。")
            started = time.time()

    try:
        gateway.stop()
    except Exception:
        pass
    _cleanup()
    return 0


def main() -> None:
    sys.exit(run_daemon())


if __name__ == "__main__":
    main()
