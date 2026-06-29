"""
shim —— 向后兼容老 import 路径

老代码:
    from fr_cli.core.chat import handle_ai_chat
    from fr_cli.core.chat import _handle_plan_mode

实际实现见 fr_cli/core/chat/ 包。
"""
from fr_cli.core.chat import _handle_plan_mode, handle_ai_chat

__all__ = ["handle_ai_chat", "_handle_plan_mode"]
