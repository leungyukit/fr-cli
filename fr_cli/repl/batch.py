"""
批处理 / 非交互模式执行器

让 fr-cli 可以在不进入 REPL 的情况下执行单条命令或单次对话，
适用于脚本、管道、cron、CI 等非激活/非交互场景。
"""
import os
import sys
import threading
from typing import Optional

from fr_cli.ui.ui import RED, RESET, YELLOW


def _ensure_queue_manager(state):
    """为批处理模式创建轻量队列管理器（仅用于等待异步任务）"""
    if getattr(state, "_queue_mgr", None):
        return state._queue_mgr

    class _DummyPrompt:
        def set_busy(self, busy: bool):
            pass

        def update_last_stats(self, **kwargs):
            pass

    from fr_cli.repl.queue import ChatQueueManager
    state._queue_mgr = ChatQueueManager(state, _DummyPrompt())
    return state._queue_mgr


def run_batch(state, text: str, is_command: bool = False, quiet: bool = False) -> int:
    """
    非交互模式执行一次输入后退出。

    Args:
        state: AppState 实例
        text: 用户输入文本
        is_command: 是否强制按 / 命令处理
        quiet: 静默模式，只输出核心结果

    Returns:
        int: 进程退出码，0 表示成功
    """
    # 批处理环境下默认拒绝需要交互确认的危险操作
    if "FR_CLI_NON_INTERACTIVE" not in os.environ:
        os.environ["FR_CLI_NON_INTERACTIVE"] = "1"

    u = text.strip()
    if not u:
        if not quiet:
            print(f"{YELLOW}输入为空，未执行任何操作。{RESET}")
        return 0

    try:
        if is_command or u.startswith("/"):
            from fr_cli.repl.router import dispatch
            should_exit = dispatch(state, u)
            # /exit /quit 等命令在批处理模式下直接退出即可
            if should_exit:
                return 0
        else:
            from fr_cli.core.chat import handle_ai_chat
            handle_ai_chat(state, u)
    except (EOFError, KeyboardInterrupt):
        if not quiet:
            print(f"{YELLOW}已取消。{RESET}")
        return 130
    except Exception as e:
        print(f"{RED}执行出错: {e}{RESET}", file=sys.stderr)
        return 1

    # 等待队列中可能存在的后台任务完成
    queue_mgr = _ensure_queue_manager(state)
    if queue_mgr.is_processing or queue_mgr.peek():
        if not quiet:
            print(f"{YELLOW}等待后台任务完成...{RESET}")
        queue_mgr.wait_for_complete()

    return 0
