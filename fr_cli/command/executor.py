"""
命令执行引擎
负责解析 AI 响应中的调用标记，并调度到统一注册表执行。

模块拆分(原单文件 509 行,按职责拆为 3 个 mixin):
- executor_parse.py:    调用标记 / 参数解析(纯文本,无状态)
- executor_dispatch.py: invoke_tool / execute / _build_deps(依赖装配)
- executor_ai.py:       peek_ai_commands / process_ai_commands(4 种格式)
- executor.py:          本文件——CommandExecutor 组装 + __init__

公共接口（保持向后兼容）：
  - invoke_tool(tool_name, kwargs, msgs=None, client=None, model_name=None, source=None): 结构化工具调用
  - execute(cmd_str, msgs=None, skip_security=False, client=None, model_name=None): 命令字符串调用
  - process_ai_commands(ai_response, msgs=None, client=None, model_name=None, skip_security=False): 解析并执行 AI 回复中的命令标记
"""
from fr_cli.command.executor_parse import CommandParseMixin
from fr_cli.command.executor_dispatch import CommandDispatchMixin, _build_deps  # noqa: F401 (re-export)
from fr_cli.command.executor_ai import CommandAIMixin
from fr_cli.command.registry import get_registry

# 旧导入路径兼容:runner.py / master_loop.py 等仍从本模块取 _build_deps
__all__ = ["CommandExecutor", "_build_deps"]


class CommandExecutor(CommandParseMixin, CommandDispatchMixin, CommandAIMixin):
    """
    命令执行器：解析 AI 回复中的调用标记，并通过注册表统一调度执行。
    直接持有 AppState，每次调用时动态构建依赖快照，彻底消除状态过时问题。

    职责分布(见各 mixin 文件):
    - CommandParseMixin:    _extract_tool_calls / _parse_tool_kwargs / _loose_parse_kwargs
    - CommandDispatchMixin: invoke_tool / execute / _get_deps / 弃用的 push/pop_agent_context
    - CommandAIMixin:       peek_ai_commands / process_ai_commands
    - 本类:                __init__ + _reg 持有

    v2.4.4 行为变更：
      - 取消 `_agent_ctx_stack` 栈式 Agent 上下文覆盖（之前的并发竞态根因）
      - 改为每次调用显式传入 `client` / `model_name`（覆盖全局 default）
      - `push_agent_context` / `pop_agent_context` 仍保留为兼容接口，但实际为 no-op
        （保留调用站点不报错，新代码不要再使用）
    """

    def __init__(self, state):
        self.state = state
        self._reg = get_registry()
