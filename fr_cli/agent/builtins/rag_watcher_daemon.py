"""
RAG 知识库守护进程 —— 后台藏经阁守护
负责在主进程退出后继续监控知识库目录，新文件自动向量化入库。

启动方式（不应由用户直接调用）：
    python -m fr_cli.agent.builtins.rag_watcher_daemon --kb_dir <目录> [--db_path <路径>] [--interval <秒>]

停止方式：
    创建 ~/.fr_cli_rag_watcher.stop 标记文件，守护进程检测到后自行退出。
"""
import os
import sys
import time
import signal
import atexit
import argparse
from pathlib import Path
from datetime import datetime

# 确保项目根目录在 Python 路径中
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

PID_FILE = Path.home() / ".fr_cli_rag_watcher.pid"
STOP_FILE = Path.home() / ".fr_cli_rag_watcher.stop"
LOG_FILE = Path.home() / ".fr_cli_rag_watcher.log"
DB_PATH = Path.home() / ".fr_cli_rag_db"

DEFAULT_INTERVAL = 30


def _log(msg):
    """写入日志文件并打印到 stderr（便于调试）"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    sys.stderr.write(line + "\n")
    sys.stderr.flush()


def _write_pid(pid):
    try:
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(pid))
    except Exception as e:
        _log(f"写入 PID 文件失败: {e}")


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
    _log("守护进程已清理并退出。")


def _setup_signal_handlers():
    def _sigterm_handler(signum, frame):
        _log(f"收到信号 {signum}，准备退出...")
        _cleanup()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _sigterm_handler)
    if hasattr(signal, "SIGINT"):
        signal.signal(signal.SIGINT, _sigterm_handler)


def _parse_args():
    parser = argparse.ArgumentParser(description="RAG Knowledge Base Watcher Daemon")
    parser.add_argument("--kb_dir", required=True, help="知识库目录路径")
    parser.add_argument("--db_path", default=str(DB_PATH), help="ChromaDB 持久化路径")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL, help="扫描间隔（秒，默认30）")
    return parser.parse_args()


def run_daemon():
    """守护进程主循环"""
    args = _parse_args()
    kb_dir = Path(args.kb_dir)
    db_path = Path(args.db_path)
    interval = max(5, args.interval)

    _clear_stop_marker()
    _write_pid(os.getpid())
    atexit.register(_cleanup)
    _setup_signal_handlers()

    _log("=" * 50)
    _log(f"RAG 知识库守护进程启动")
    _log(f"  知识库目录: {kb_dir}")
    _log(f"  向量数据库: {db_path}")
    _log(f"  扫描间隔:   {interval} 秒")
    _log("=" * 50)

    if not kb_dir.exists():
        _log(f"错误: 知识库目录不存在: {kb_dir}")
        _cleanup()
        sys.exit(1)

    # 延迟导入，减少启动开销
    try:
        from fr_cli.agent.builtins.rag import RAGManager
    except Exception as e:
        _log(f"导入 RAGManager 失败: {e}")
        _cleanup()
        sys.exit(1)

    mgr = RAGManager(kb_dir=str(kb_dir), db_path=str(db_path))

    # 首次全量同步
    _log("开始首次全量同步...")
    try:
        ok, msg = mgr.sync_directory()
        _log(f"首次同步结果: {msg}")
    except Exception as e:
        _log(f"首次同步异常: {e}")

    # 主循环：定期检查停止标记并同步目录
    scan_count = 0
    while True:
        time.sleep(interval)

        if STOP_FILE.exists():
            _log("检测到停止标记，准备退出...")
            break

        scan_count += 1
        try:
            ok, msg = mgr.sync_directory()
            if ok and "已是最新状态" not in msg:
                _log(f"扫描 #{scan_count}: {msg}")
            elif scan_count % 120 == 0:  # 每约1小时（120次×30秒）记录一次心跳
                _log(f"心跳 #{scan_count}: 知识库监控正常，{msg}")
        except Exception as e:
            _log(f"扫描 #{scan_count} 异常: {e}")

    _cleanup()


if __name__ == "__main__":
    run_daemon()
