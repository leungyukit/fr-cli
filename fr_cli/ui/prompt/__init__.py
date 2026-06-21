"""
fr-cli TUI 输入面板 —— 自动选择 TUI / fallback

降级策略：
- 真 TTY + prompt_toolkit → FanRenPrompt（TUI 多列补全 + 状态栏）
- non-TTY / CI / HTTP / pipe → FallbackPrompt（纯 input + 命令列表打印）
"""
import sys

try:
    from prompt_toolkit import PromptSession  # noqa: F401  (检测可用性)
    HAS_PT = True
except ImportError:
    HAS_PT = False

from fr_cli.ui.prompt.completer import FanRenCompleter
from fr_cli.ui.prompt.fallback import FallbackPrompt
from fr_cli.ui.prompt.status import StatusState
from fr_cli.ui.prompt.tui import FanRenPrompt

# 保持向后兼容 —— 旧代码可能直接 import 这些符号
__all__ = [
    "FanRenCompleter",
    "FanRenPrompt",
    "FallbackPrompt",
    "StatusState",
    "create_prompt",
]


def create_prompt(state):
    """工厂函数：自动选择 TUI 或 fallback

    - 真 TTY 终端 + prompt_toolkit 可用 → FanRenPrompt（TUI 多列补全）
    - non-TTY / CI / HTTP / pipe → FallbackPrompt（纯 input + 命令列表打印）
    """
    if HAS_PT and sys.stdin.isatty() and sys.stdout.isatty():
        return FanRenPrompt(state)
    return FallbackPrompt(state)
