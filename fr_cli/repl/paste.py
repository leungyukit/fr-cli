"""
多行粘贴降级 —— ``/paste`` 命令

问题
----
多行粘贴在**不支持 bracketed paste 协议**的终端里会被拆成多次回车：
粘 3 行代码 → 提交 3 条残缺消息 → AI 收到三段被截断的输入。

现状（别误判）
--------------
prompt_toolkit 的渲染器会**自动开启** bracketed paste
（``prompt_toolkit/renderer.py`` → ``output.enable_bracketed_paste()``），
所以绝大多数终端（iTerm2 / Windows Terminal / GNOME Terminal / Alacritty /
WezTerm …）**粘贴多行 = 一条消息**，这条路本来就是通的。

真正缺的是**降级出路**：协议不可用时（老终端 / 精简终端 / SSH 到不支持的
tty / 某些 pty 包装），用户只能一行一行敲。

``/paste`` 就是这条出路 —— 进入多行输入模式，读到 EOF（Ctrl+D）或单独一行
``.`` 为止，整段作为**一条消息**提交。任何终端都能用，不依赖终端能力。

另外两个既有的多行入口仍然有效：
- ``Esc+Enter`` / ``Ctrl+J`` 在输入框里插换行（交互式改写用）
- ``/write <文件>`` 等命令用 Ctrl+D 收尾（写文件用）
"""
from __future__ import annotations

from typing import List, Optional

#: 提前结束多行输入的单独一行标记（Ctrl+D 同样可以）
TERMINATOR = "."

#: 提示语
HINT = "粘贴多行内容，Ctrl+D 结束（单独一行 . 提前结束）:"


def is_paste_command(text: str) -> bool:
    """判断输入是否是 ``/paste``（可带空白）"""
    return (text or "").strip() == "/paste"


def _read_lines(terminator: str) -> List[str]:
    """逐行读 stdin，直到 EOF 或终止标记。

    单独抽出来是为了能在 TUI 挂起态里跑（见 :func:`collect_multiline`）。
    """
    lines: List[str] = []
    while True:
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            break
        if terminator and line.strip() == terminator:
            break
        lines.append(line)
    return lines


def collect_multiline(prompt=None, terminator: Optional[str] = None) -> str:
    """收集多行输入，返回整段文本（换行用 ``\\n`` 连接）。

    Args:
        prompt: 当前输入组件（TUI 时用它把读取挪到挂起态，避免与渲染打架）；
            None 或无 ``_run_in_terminal`` 时直接读 stdin
        terminator: 提前结束的标记行（默认 ``.``）

    Returns:
        收集到的文本（可能为空）
    """
    term = terminator if terminator is not None else TERMINATOR
    captured = {"text": ""}

    def _run() -> None:
        try:
            print(HINT)
            captured["text"] = "\n".join(_read_lines(term))
        except Exception:
            captured["text"] = ""

    runner = getattr(prompt, "_run_in_terminal", None)
    if callable(runner):
        # TUI：挂起渲染 → 终端回到普通行模式 → input() 正常可用。
        # 注意 run_in_terminal 会吞掉返回值，所以用闭包捕获。
        runner(_run)
    else:
        _run()
    return captured["text"]
