"""
fr_cli.core.chat 包 —— AI 对话处理核心(按职责拆分)

模块:
  pipeline    handle_ai_chat 主入口 + 5 个阶段方法
  plan_mode   _handle_plan_mode 计划模式
  helpers     auto_compress / record_usage / fetch_mcp / fold_result

向后兼容:
  from fr_cli.core.chat import handle_ai_chat  仍可用(老 shim)
  from fr_cli.core.chat import _handle_plan_mode  仍可用(老 shim)
"""
from fr_cli.core.chat.pipeline import handle_ai_chat
from fr_cli.core.chat.plan_mode import handle_plan_mode as _handle_plan_mode

__all__ = ["handle_ai_chat", "_handle_plan_mode"]
