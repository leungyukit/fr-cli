"""
凡人打字机 —— 主脑控制台（精简版 v2.4.0+）

主循环本身（~150 行），所有子任务下放：
- fr_cli.repl.bootstrap —— 启动引导
- fr_cli.repl.queue    —— 对话队列管理器
- fr_cli.repl.router   —— 命令路由
- fr_cli.repl.actions  —— e/r/u 快捷键动作

主循环只做：
1. 调用 bootstrap() 启动应用
2. 创建 TUI 输入面板
3. 循环：打印分隔线 → 读取输入 → 分发到 router 或 queue
4. 退出
"""
import sys, os
from datetime import datetime

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from fr_cli.ui.ui import enable_win_ansi, print_bye, DIM, RESET, YELLOW, BLUE
from fr_cli.ui.banner import print_input_separator
from fr_cli.ui.prompt import create_prompt
from fr_cli.repl.bootstrap import bootstrap
from fr_cli.repl.router import dispatch as dispatch_command
from fr_cli.repl.queue import ChatQueueManager
from fr_cli.repl.actions import action_edit_last_ai, action_retry_last_user, action_undo_last


def main():
    enable_win_ansi()
    cfg, state = bootstrap()
    if state is None:
        return

    # 创建 TUI 输入面板
    prompt = create_prompt(state)
    state._prompt = prompt  # 供 scenario 等模块使用
    prompt.update_status(
        model=state.model_name,
        provider=state.provider,
        directory=cfg.get("allowed_dirs", [""])[0] if cfg.get("allowed_dirs") else "",
        session=state.sn,
        limit=state.limit,
        mode=state.thinking_mode,
    )

    # 创建对话队列管理器（普通 AI 对话走队列，支持并发输入）
    state._queue_mgr = ChatQueueManager(state, prompt)

    # ================= 主循环 =================
    first_iter = True
    while True:
        # 分隔线 ── input ────（Kimi Code 风格：自带"input"标签）
        print_input_separator()

        # 第一次引导提示（只在 TTY 下显示）
        prefix_hint = ""
        if first_iter and (not hasattr(prompt, "_is_tty") or prompt._is_tty):
            prefix_hint = "首次使用？输入 /tutorial 开始教程，或 /help 查看所有命令"
        first_iter = False

        u = prompt.get_input(prefix_hint=prefix_hint)
        if u is None:  # Ctrl+D 退出
            if state._queue_mgr.is_processing or state._queue_mgr.peek():
                print(f"{YELLOW}正在处理队列中的问题，请稍候...{RESET}")
                state._queue_mgr.wait_for_complete()
            print_bye()
            break
        if not u:
            continue

        # 时间戳
        input_time = datetime.now()
        time_str = input_time.strftime("%H:%M:%S")
        print(f"{DIM}输入时间: {time_str}{RESET}")

        # 处理 e/r/u 动作（来自 TUI 快捷键）
        if u == "__ACTION__:edit":
            action_edit_last_ai(state, prompt)
            continue
        if u == "__ACTION__:retry":
            action_retry_last_user(state, prompt)
            continue
        if u == "__ACTION__:undo":
            action_undo_last(state)
            continue

        # /undo N 撤销多轮
        if u.startswith("/undo "):
            try:
                n = int(u.split()[1])
                action_undo_last(state, n=n)
            except (ValueError, IndexError):
                print(f"{YELLOW}用法: /undo N（撤销 N 轮对话）{RESET}")
            continue

        # 别名替换
        if u in state.aliases:
            u = state.aliases[u]

        # 命令分发（/ 开头走 router，普通文本走 AI 对话队列）
        if u.startswith("/"):
            should_break = dispatch_command(state, u)
            if should_break:
                # _cmd_exit 已经打印过 print_bye，这里不再重复
                break
        else:
            # 普通对话走队列（支持用户在 AI 回答期间继续输入）
            queue_mgr = state._queue_mgr
            if queue_mgr.is_processing:
                print(f"{DIM}▍ {u}{RESET}")
            else:
                print(f"{BLUE}▍ {u}{RESET}")
            queue_mgr.process(u)


if __name__ == "__main__":
    main()