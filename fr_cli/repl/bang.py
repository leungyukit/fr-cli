"""
! <cmd> 直执行 / ! <cmd> | <prompt> 管道模式

输入框 placeholder 与 /help shell 都承诺过这两种用法,本模块落地实现:
- 普通模式:执行 shell 命令,输出仅展示(截断 3000 字符),不进 AI 上下文
- 管道模式:命令输出截断后作为 user 消息进入对话上下文,问题走队列交给 AI

安全口径:命令由用户显式键入(非 AI 发起),不再二次确认 —— 与 /shell 模式一致;
AI 发起的调用仍走 security.check("sec_shell", ...) 四阶确认。
"""
from fr_cli.ui.ui import DIM, RESET, YELLOW


def handle_bang(state, body: str) -> bool:
    """处理 ! 开头(不含 ! 本身)的输入。

    :param state: REPL 状态(需要 _queue_mgr / lang / messages)
    :param body: ! 后面的原始文本
    :return: True 表示已处理,调用方应 continue
    """
    from fr_cli.agent.shell_mode import get_shell_manager

    body = body.strip()
    if not body:
        print(f"{DIM}用法: !<shell 命令>（如 !ls -la）｜ !<cmd> | <问题> 把输出喂给 AI{RESET}")
        return True

    # 管道模式: !cmd | prompt(注意 shell 命令本身也可能含 |,取第一个 | 分割,
    # 因此 prompt 侧不允许再出现 | 开头的续接——与 /help 示例一致)
    shell_cmd, sep, pipe_prompt = body.partition("|")
    shell_cmd = shell_cmd.strip()
    pipe_prompt = pipe_prompt.strip() if sep else ""
    if not shell_cmd:
        print(f"{YELLOW}[!]! 后面需要跟命令{RESET}")
        return True

    out, code = get_shell_manager().execute_command(shell_cmd)

    if pipe_prompt:
        _pipe_to_ai(state, shell_cmd, out, pipe_prompt)
        return True

    _display_only(out, code)
    return True


def _display_only(out: str, code: int) -> None:
    """普通模式:只展示,不进上下文"""
    if out.strip():
        if len(out) > 3000:
            out = out[:3000] + f"\n... (输出共 {len(out)} 字符，已截断)"
        print(f"{DIM}{out.rstrip()}{RESET}")
    if code != 0:
        print(f"{YELLOW}[!] 命令退出码 {code}{RESET}")


def _pipe_to_ai(state, shell_cmd: str, out: str, prompt: str) -> None:
    """管道模式:输出截断后进上下文,问题入队"""
    from fr_cli.lang.i18n import T

    pipe_data = out.strip()
    if len(pipe_data) > 3000:
        pipe_data = pipe_data[:3000] + f"\n... (输出共 {len(out.strip())} 字符，已截断)"
    state.messages.append({
        "role": "user",
        "content": f"{T('pipe_prefix', state.lang)}{shell_cmd}\n{pipe_data}",
    })

    queue_mgr = state._queue_mgr
    if queue_mgr.is_processing:
        print(f"{DIM}已加入队列，AI 回答完成后自动处理...{RESET}")
    queue_mgr.process(prompt)
