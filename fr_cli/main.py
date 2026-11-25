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
import argparse
from datetime import datetime
from fr_cli.ui.ui import RED

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def _should_disable_colors_early() -> bool:
    """
    早期颜色控制。

    历史背景: 旧版 prompt_toolkit 的 patch_stdout 会把原始 ANSI 转义序列
    当作纯文本显示为 ?[92m 等乱码, 因此曾在 REPL 模式全局禁色。
    实测 prompt_toolkit 3.0.52 的 patch_stdout 已正确解析 ANSI(直通不损坏),
    全局禁色反而让整个 REPL 变成无彩色, 体验降级。

    现在的策略:
    - NO_COLOR 环境变量 → 禁色(标准约定)
    - 非 TTY(管道/重定向) → 禁色
    - 交互式 TTY → 保留颜色; 流式输出路径内部仍有
      _ColorDisable / _is_prompt_toolkit_stdout 局部保护兜底
    用户可通过 FORCE_COLOR=1 / CLICOLOR_FORCE=1 强制启用颜色。
    """
    if os.environ.get("FORCE_COLOR") or os.environ.get("CLICOLOR_FORCE"):
        return False
    if os.environ.get("NO_COLOR"):
        return True
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return True
    return False


if _should_disable_colors_early():
    os.environ["NO_COLOR"] = "1"

from fr_cli.ui.ui import set_no_color, enable_win_ansi, print_bye, DIM, RESET, YELLOW
if os.environ.get("NO_COLOR"):
    set_no_color(True)
from fr_cli.ui.banner import print_input_separator
from fr_cli.ui.prompt import create_prompt
from fr_cli.repl.bootstrap import bootstrap
from fr_cli.repl.router import dispatch as dispatch_command
from fr_cli.repl.queue import ChatQueueManager
from fr_cli.repl.actions import action_edit_last_ai, action_retry_last_user, action_undo_last


def _dispatch_app_stopped(reason: str) -> None:
    """广播 app.stopped 事件(主循环退出前调用)

    v3.0+:此前该事件只在 metrics 里注册了钩子,却没有任何生产派发点,
    指标恒为 0。这里补上派发点(Ctrl+D 与 /exit 两条退出路径都覆盖)。

    同时停掉所有定时任务:它们的计时器是 daemon 线程,进程退出时不会
    挡住收尾,但在退出流程里继续触发会用 prompt_toolkit.patch_stdout
    抢走 stdout,把告别语/统计输出搅乱。

    Args:
        reason: 退出原因(如 "eof" / "exit")
    """
    try:
        from fr_cli.weapon.cron import stop_all
        stop_all()
    except Exception:
        pass
    try:
        from fr_cli.core.events import V2Events, dispatch_event
        dispatch_event(
            V2Events.APP_STOPPED,
            data={"reason": reason},
            source="main",
        )
    except Exception:
        pass


def _build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        prog="fr-cli",
        description="凡人打字机 (fr-cli) —— 终端 AI 助手",
        add_help=False,
    )
    parser.add_argument(
        "-h", "--help",
        action="store_true",
        help="显示帮助信息并退出",
    )
    parser.add_argument(
        "-logo",
        action="store_true",
        help="启动时显示韩立全身细节字符画（REPL 模式有效）",
    )
    parser.add_argument(
        "-noart",
        action="store_true",
        help="启动时不显示韩立字符画，只显示信息框",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="静默模式，减少非必要输出",
    )
    parser.add_argument(
        "-c", "--command",
        metavar="CMD",
        help="执行一条 / 命令后退出（例如：-c '/model current'）",
    )
    parser.add_argument(
        "-p", "--prompt",
        dest="prompt_text",
        metavar="TEXT",
        help="向 AI 提问后退出（例如：-p '总结当前目录'）",
    )
    parser.add_argument(
        "-f", "--file",
        metavar="PATH",
        help="从文件读取提示词并交给 AI 处理后退出",
    )
    parser.add_argument(
        "-s", "--stdin",
        action="store_true",
        help="从标准输入读取提示词并交给 AI 处理后退出",
    )
    parser.add_argument(
        "prompt",
        nargs="*",
        help="直接传入的提示词（与 -p 二选一）",
    )
    return parser


def _print_help():
    """打印自定义帮助信息"""
    print("""凡人打字机 (fr-cli) —— 终端 AI 助手

用法:
  fr-cli                              进入交互式 REPL（默认）
  fr-cli [选项] <提示词>              单次 AI 对话后退出
  fr-cli -c <命令>                    执行一条 / 命令后退出

选项:
  -h, --help          显示本帮助信息并退出
  -logo               启动时显示韩立全身细节字符画（REPL 模式）
  -noart              启动时不显示韩立字符画，只显示信息框
  -q, --quiet         静默模式，只输出核心结果
  -p, --prompt TEXT   指定要发送给 AI 的提示词
  -c, --command CMD   执行一条 slash 命令（如 /model current）
  -f, --file PATH     从文件读取提示词
  -s, --stdin         从标准输入读取提示词

示例:
  fr-cli "请总结 README.md"
  fr-cli -p "Python 如何读取 JSON？"
  fr-cli -c "/model current"
  cat article.txt | fr-cli -s
  fr-cli -f prompt.txt -q
  fr-cli -logo           # 大幅韩立字符画启动
""")


def _get_batch_input(args) -> tuple:
    """
    根据命令行参数确定是否需要进入批处理模式。

    Returns:
        (text, is_command) 或 (None, False)
    """
    if args.command is not None:
        return args.command, True
    if args.prompt_text is not None:
        return args.prompt_text, False
    if args.prompt:
        return " ".join(args.prompt), False
    if args.file is not None:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                return f.read(), False
        except OSError as e:
            print(f"{RED}无法读取文件 {args.file}: {e}{RESET}", file=sys.stderr)
            sys.exit(1)
    if args.stdin:
        try:
            return sys.stdin.read(), False
        except OSError as e:
            print(f"{RED}无法读取标准输入: {e}{RESET}", file=sys.stderr)
            sys.exit(1)
    if args.prompt:
        return " ".join(args.prompt), False
    return None, False


def main():
    enable_win_ansi()

    # 解析命令行参数
    parser = _build_parser()
    args = parser.parse_args()

    if args.help:
        _print_help()
        return 0

    # 批处理模式：无需 banner 和 TUI
    batch_text, batch_is_cmd = _get_batch_input(args)
    batch_mode = batch_text is not None
    show_logo = args.logo and not batch_mode and not args.quiet

    cfg, state = bootstrap(show_logo=show_logo, show_banner=not batch_mode and not args.quiet,
                           show_art=not args.noart)
    if state is None:
        return 1

    # 批处理模式：执行单次输入后退出
    if batch_mode:
        from fr_cli.repl.batch import run_batch
        return run_batch(state, batch_text, is_command=batch_is_cmd, quiet=args.quiet)

    # 创建 TUI 输入面板
    prompt = create_prompt(state)
    state._prompt = prompt  # 供 scenario 等模块使用
    prompt.update_status(
        model=state.display_model,
        provider=state.display_provider,
        directory=cfg.get("allowed_dirs", [""])[0] if cfg.get("allowed_dirs") else "",
        session=state.sn,
        limit=state.limit,
        mode=state.thinking_mode,
    )

    # 创建对话队列管理器（普通 AI 对话走队列，支持并发输入）
    state._queue_mgr = ChatQueueManager(state, prompt)

    # v2.8.7：开启「确认中转站」——
    # 工具执行在后台线程跑，安全确认不能直接 input()（会和主线程的
    # prompt_toolkit 抢同一个 stdin → 用户敲的 Y/A/F/N 全被输入框吞掉 → 假死）。
    # 改为由本线程（拥有 stdin 的那个）代读，答案经中转站送回后台线程。
    from fr_cli.security.interactive import BROKER
    if getattr(prompt, "_session", None) is not None:
        BROKER.enable()

    # ================= 主循环 =================
    first_iter = True
    while True:
        # 分隔线 ── input ────（Kimi Code 风格：自带"input"标签）
        print_input_separator(active=True)

        # 第一次引导提示（只在 TTY 下显示）
        prefix_hint = ""
        if first_iter and (not hasattr(prompt, "_is_tty") or prompt._is_tty):
            prefix_hint = "首次使用？输入 /tutorial 开始教程，或 /help 查看所有命令"
        first_iter = False

        u = prompt.get_input(prefix_hint=prefix_hint)
        if u is None:  # Ctrl+D 退出
            BROKER.cancel_all()  # 待确认的操作按拒绝处理，否则退出会死等
            if state._queue_mgr.is_processing or state._queue_mgr.peek():
                print(f"{YELLOW}正在处理队列中的问题，请稍候...{RESET}")
                state._queue_mgr.wait_for_complete()
            print_bye()
            _dispatch_app_stopped("eof")
            break
        # 输入态结束: 浅灰分隔线打印在已提交输入的下方, 表示当前不在输入态
        print_input_separator(active=False)

        # v2.8.7：待确认的操作 —— Y/A/F/N 优先当作确认答案（不当对话消息）
        if BROKER.has_pending():
            from fr_cli.security.interactive import deliver_if_confirm
            if deliver_if_confirm(u):
                continue
            if u.strip():
                # 不是确认答案 → 照常当对话消息处理，但提醒确认还在等
                print(f"{YELLOW}[!] 还有操作待确认，请在输入框输入 Y / A / F / N{RESET}")

        if not u:
            continue

        # 时间戳（简洁格式）
        input_time = datetime.now()
        time_str = input_time.strftime("%H:%M:%S")
        print(f"{DIM}▸ {time_str}{RESET}")

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

        # /paste —— 多行粘贴降级：读到 EOF 为止，整段作为**一条消息**提交。
        # 背景：不支持 bracketed paste 协议的终端会把多行粘贴拆成多次回车，
        # 粘一段代码就变成三条残缺消息（详见 repl/paste.py）。
        from fr_cli.repl.paste import collect_multiline, is_paste_command
        if is_paste_command(u):
            text = collect_multiline(prompt)
            if not text.strip():
                print(f"{YELLOW}（内容为空，已取消）{RESET}")
                continue
            u = text

        # @agent_name 直接调用 Agent 分身（不走普通 AI 对话队列）
        if u.startswith("@"):
            from fr_cli.agent.dispatch import dispatch_agent_call
            if dispatch_agent_call(state, u):
                continue

        # !<cmd> 直接执行 shell 命令；!<cmd> | <问题> 管道模式把输出喂给 AI
        # （输入框提示里的 "! shell" 承诺，落地在 repl/bang.py）
        if u.startswith("!"):
            from fr_cli.repl.bang import handle_bang
            handle_bang(state, u[1:])
            continue

        # 命令分发（/ 开头走 router，普通文本走 AI 对话队列）
        if u.startswith("/"):
            should_break = dispatch_command(state, u)
            if should_break:
                # _cmd_exit 已经打印过 print_bye，这里不再重复
                BROKER.cancel_all()  # 待确认的操作按拒绝处理，别让后台线程死等
                _dispatch_app_stopped("exit")
                break
        else:
            # 普通对话走队列（支持用户在 AI 回答期间继续输入）
            queue_mgr = state._queue_mgr
            if queue_mgr.is_processing:
                print(f"{DIM}已加入队列，AI 回答完成后自动处理...{RESET}")
            queue_mgr.process(u)


if __name__ == "__main__":
    sys.exit(main() or 0)
