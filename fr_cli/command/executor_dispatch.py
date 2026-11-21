"""
CommandExecutor 调度 mixin —— invoke_tool / execute / 依赖装配

从 fr_cli.command.executor 拆出(原文件 509 行)。
包含:
- _build_deps: 根据 AppState 动态构建依赖命名空间(每次实时反射,避免快照过时)
- invoke_tool: 第一层,结构化工具调用(PreToolUse hook -> dispatch -> PostToolUse hook -> 事件广播)
- execute: 第二层,命令字符串调用(插件优先,其余走注册表内部接口)

_build_deps 经 executor.py re-export 保持旧导入路径可用:
    from fr_cli.command.executor import _build_deps
"""
from __future__ import annotations

from types import SimpleNamespace

from fr_cli.addon.plugin import exec_plugin
from fr_cli.command.registry import get_registry
from fr_cli.core.result import Result


def _build_deps(state, client=None, model_name=None):
    """根据 AppState 动态构建依赖命名空间（每次调用实时反射，避免快照过时）

    Args:
        client: 可选的覆盖 client（如 Agent 专属模型）
        model_name: 可选的覆盖模型名
    """
    return SimpleNamespace(
        vfs=state.vfs,
        mail_c=state.mail_c,
        web_c=state.web_c,
        disk_c=state.disk_c,
        plugins=state.plugins,
        lang=state.lang,
        security=state.security,
        cfg=state.cfg,
        client=client or state.client,
        model_name=model_name or state.model_name,
        mcp=getattr(state, "mcp", None),
    )


class CommandDispatchMixin:
    """工具调度与依赖装配"""

    # ------------------------------------------------------------------
    # Agent 上下文覆盖（v2.4.4 弃用接口，保留仅为兼容）
    # ------------------------------------------------------------------
    def push_agent_context(self, client, model_name):
        """v2.4.4 弃用：此接口现在为 no-op，client/model_name 改为显式传入 invoke_tool/execute/process_ai_commands。

        保留此接口仅为兼容旧代码（agent/executor.py / agent/workflow.py），新代码请改用
        invoke_tool(tool_name, kwargs, client=..., model_name=...) 直接传参。
        """
        # no-op：避免调用方报错，但行为不再依赖于全局栈
        return

    def pop_agent_context(self):
        """v2.4.4 弃用：no-op（与 push_agent_context 配对的占位接口）"""
        return

    def _get_deps(self, client=None, model_name=None):
        """构建依赖命名空间，client/model_name 显式覆盖（v2.4.4 取代 push/pop 栈）"""
        return _build_deps(self.state, client=client, model_name=model_name)

    # ------------------------------------------------------------------
    # 第一层：结构化工具调用
    # ------------------------------------------------------------------
    def invoke_tool(self, tool_name, kwargs, msgs=None, skip_security=False,
                    client=None, model_name=None):
        """根据工具名和结构化参数，通过注册表调度执行。返回 Result。

        Args:
            skip_security: 跳过安全确认。默认为 False（走 sec_* 检查）。
            client / model_name: v2.4.4 起，显式覆盖 LLM 上下文（取代 push_agent_context 栈）。
                传 None 时使用 AppState 默认。
        """
        # v2.7+:PreToolUse hook(可阻止/修改)
        if not skip_security:
            try:
                from fr_cli.agent.hooks import get_hook_manager
                cfg = getattr(self.state, "cfg", None)
                hook_mgr = get_hook_manager(cfg=cfg)
                pre_result = hook_mgr.run_pre_tool_use(tool_name, kwargs)
                if pre_result.blocked:
                    # v3 事件总线:被 hook 阻止
                    try:
                        from fr_cli.core.events import dispatch_event, V2Events
                        dispatch_event(
                            V2Events.TOOL_BLOCKED,
                            data={"name": tool_name, "args": kwargs, "reason": pre_result.reason},
                            source="command_executor",
                        )
                    except Exception:
                        pass
                    return Result.fail(f"工具被 hook 阻止: {pre_result.reason}")
                if pre_result.modified_args:
                    kwargs.update(pre_result.modified_args)
            except Exception:
                pass  # hook 失败不影响主流程

        # v3.0+:工具被调用事件(广播,不影响控制流)
        try:
            from fr_cli.core.events import dispatch_event, V2Events
            dispatch_event(
                V2Events.TOOL_INVOKED,
                data={"name": tool_name, "args": kwargs},
                source="command_executor",
            )
        except Exception:
            pass

        data, err = self._reg.dispatch(
            self._get_deps(client=client, model_name=model_name),
            tool_name, msgs=msgs, skip_security=skip_security, **kwargs
        )

        # v2.7+:PostToolUse hook(可修改结果)
        try:
            from fr_cli.agent.hooks import get_hook_manager
            cfg = getattr(self.state, "cfg", None)
            hook_mgr = get_hook_manager(cfg=cfg)
            post_result = hook_mgr.run_post_tool_use(tool_name, kwargs, data)
            if post_result.modified_args.get("tool_result"):
                data = post_result.modified_args["tool_result"]
        except Exception:
            pass

        # v3.0+:事件总线广播(解耦观察者:日志/监控/Web Console 推送等)
        try:
            from fr_cli.core.events import dispatch_event, V2Events
            if err is None:
                dispatch_event(
                    V2Events.TOOL_SUCCEEDED,
                    data={"name": tool_name, "args": kwargs, "result": data},
                    source="command_executor",
                )
            else:
                dispatch_event(
                    V2Events.TOOL_FAILED,
                    data={"name": tool_name, "args": kwargs, "error": err},
                    source="command_executor",
                )
        except Exception:
            pass

        return Result.ok(data) if err is None else Result.fail(err)

    # ------------------------------------------------------------------
    # 第二层：传统命令解析（用户输入 / 插件调用）
    # ------------------------------------------------------------------
    def execute(self, cmd_str, msgs=None, skip_security=False, client=None, model_name=None):
        """执行单个命令并返回 Result。
        已分词检查插件后，直接通过注册表内部接口调度，避免重复 split。

        Args:
            skip_security: 跳过 sec_* 确认。
                - 用户在 REPL 输入 /cmd 时为 False（保留安全确认语义）
                - AI 通过【命令：...】触发时为 False（v2.4.4 修复：AI 命令串也走 sec_*）
                - 内部已确认过的批量调度可显式传 True
            client / model_name: v2.4.4 起，显式覆盖 LLM 上下文。
        """
        parts = cmd_str.strip().split()
        if not parts:
            return Result.fail("Empty command")
        cmd = parts[0].lstrip("/")
        # 插件命令优先直接处理（保持 mock 路径兼容）
        if cmd in self.state.plugins:
            p_args = ' '.join(parts[1:]) if len(parts) > 1 else ""
            exec_plugin(cmd, self.state.plugins[cmd], p_args, self.state.lang)
            return Result.ok(f"Plugin {cmd} executed")
        # 其余命令通过注册表内部接口直接调度，避免 dispatch_cmd 再次 split
        data, err = self._reg._dispatch_cmd_parts(
            self._get_deps(client=client, model_name=model_name),
            parts, msgs=msgs, skip_security=skip_security
        )
        return Result.ok(data) if err is None else Result.fail(err)
