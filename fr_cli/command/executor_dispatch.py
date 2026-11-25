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

import contextlib
import contextvars
import os
from types import SimpleNamespace
from typing import Any, Dict, Optional

from fr_cli.addon.plugin import exec_plugin
from fr_cli.core.result import Result
from fr_cli.core.trace import start_span

#: 当前工具调用的来源（谁发起的这次调用）
#:
#: 用 ContextVar 而不是函数参数层层透传 —— Agent 内部代码是用户自己写的，
#: 它们调 ``context["executor"].invoke_tool(...)`` 时不会传来源，
#: 只能在**外层**用 :func:`tool_source_scope` 圈一段上下文。
_TOOL_SOURCE: contextvars.ContextVar[str] = contextvars.ContextVar(
    "fr_cli_tool_source", default=""
)


@contextlib.contextmanager
def tool_source_scope(source: str):
    """标记本上下文内工具调用的来源（状态栏显示用）。

    用法::

        with tool_source_scope("local"):
            result = agent.run(context)      # 内部任意 invoke_tool 都会带上 local

    Args:
        source: 来源标识，如 ``master`` / ``local`` / ``workflow:xx`` / ``plan``

    Yields:
        None
    """
    token = _TOOL_SOURCE.set(source or "")
    try:
        yield
    finally:
        _TOOL_SOURCE.reset(token)


def _summarize_value(value: Any, max_len: int = 120) -> Any:
    """把单个参数值压成可安全放进 span 属性的摘要（超长截断，容器只记规模）。"""
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        if len(value) <= max_len:
            return value
        return value[:max_len] + f"...(已截断,原长 {len(value)})"
    if isinstance(value, dict):
        return f"<dict:{len(value)} 个键>"
    if isinstance(value, (list, tuple, set)):
        return f"<{type(value).__name__}:{len(value)} 项>"
    return f"<{type(value).__name__}>"


def _tool_args_digest(kwargs: Dict[str, Any], max_len: int = 28) -> str:
    """把工具参数压成状态栏用的一行摘要。

    只取"最能说明在干什么"的那个参数（路径 / 查询 / 命令 / 名称），
    值截断到 max_len —— 状态栏只有一行宽，塞不下完整参数。
    """
    if not kwargs:
        return ""
    # 优先展示这些语义明确的键
    preferred = ("path", "file_path", "query", "command", "cmd", "url",
                 "name", "target", "pattern")
    picked = None
    for key in preferred:
        if key in kwargs:
            picked = (key, kwargs[key])
            break
    if picked is None:
        picked = next(iter(kwargs.items()))

    key, value = picked
    if not isinstance(value, str):
        value = str(value)
    value = " ".join(value.split())  # 折行压平
    if len(value) > max_len:
        value = value[:max_len] + "…"
    return f"{key}={value}" if value else str(key)


def _report_tool_start(state, tool_name: str, kwargs: Dict[str, Any], source: str = ""):
    """上报"工具开始执行"到 REPL 状态栏。

    返回一个上下文对象（供 _report_tool_end 还原状态）；没有 TUI 时返回 None。
    """
    prompt = getattr(state, "_prompt", None)
    if prompt is None:
        return None
    try:
        import time
        prompt.status.tool_name = tool_name
        prompt.status.tool_args = _tool_args_digest(kwargs)
        prompt.status.tool_source = source or ""
        prompt.status.tool_error = ""
        prompt.status.tool_started = time.time()
        prompt._invalidate()
        return prompt
    except Exception:
        return None


def _report_tool_end(prompt, error: str = "", tool_name: str = "") -> None:
    """工具执行结束 —— 成功则清空状态栏工具字段，失败则保留失败现场。

    失败时**不清**工具名与参数：工具结果本身不会回显给用户，
    状态栏是失败原因唯一可见的地方（保留到本轮对话结束）。

    Args:
        prompt: 上报的 TUI 组件
        error: 失败原因（空串 = 成功）
        tool_name: 本次执行的工具名 —— 并行执行时用来判断
            "状态栏现在显示的是不是我自己"（不是就不能清，
            否则会把另一个还在跑的工具误显示成"就绪"）
    """
    if prompt is None:
        return
    try:
        if error:
            prompt.status.tool_error = _short_error(error)
        else:
            if tool_name and prompt.status.tool_name != tool_name:
                return  # 状态栏已经切到别的工具了，别覆盖
            prompt.status.tool_name = ""
            prompt.status.tool_args = ""
            prompt.status.tool_source = ""
            prompt.status.tool_error = ""
            prompt.status.tool_started = 0.0
        prompt._invalidate()
    except Exception:
        pass


def _echo_tool_result(state, tool_name: str, ok: bool, error: str = "", source: str = "") -> None:
    """把工具执行结果**回显**一行（成功绿 / 失败红）。

    v2.8.7 第四阶段：此前工具结果**只回给模型**、不回显给用户 ——
    状态栏是失败现场唯一可见的地方，但状态栏会被下一次刷新覆盖，
    用户往往事后才发现工具其实失败了。这里补一行摘要：
    成功打勾、失败带原因，颜色即语义（绿=成功 / 红=失败）。

    静默场景（headless / 批处理 / 服务端）不打扰输出。
    """
    try:
        if state is not None and getattr(state, "headless", False):
            return
        if os.environ.get("FR_CLI_NON_INTERACTIVE"):
            return
    except Exception:
        pass

    from fr_cli.ui.ui import GREEN, RED, DIM, RESET, print_styled
    head = f"{DIM}[{source}]{RESET} " if source else ""
    if ok:
        print_styled(f"{head}{GREEN}✓ {tool_name}{RESET}")
    else:
        print_styled(f"{head}{RED}✗ {tool_name}: {_short_error(error)}{RESET}")


def _short_error(error: Any, max_len: int = 48) -> str:
    """把错误压成状态栏能塞下的一行（换行压平 + 截断）。"""
    if error is None:
        return ""
    text = " ".join(str(error).split())
    if len(text) > max_len:
        text = text[:max_len] + "…"
    return text


def _summarize_kwargs(kwargs: Dict[str, Any], max_keys: int = 8) -> Dict[str, Any]:
    """把工具参数压缩成摘要字典（避免把整段文件内容/长文本塞进 trace）。"""
    if not kwargs:
        return {}
    summary: Dict[str, Any] = {}
    items = list(kwargs.items())
    for key, value in items[:max_keys]:
        summary[key] = _summarize_value(value)
    if len(items) > max_keys:
        summary["__truncated__"] = f"省略 {len(items) - max_keys} 个参数"
    return summary


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
                    client=None, model_name=None, source: Optional[str] = None):
        """根据工具名和结构化参数，通过注册表调度执行。返回 Result。

        Args:
            skip_security: 跳过安全确认。默认为 False（走 sec_* 检查）。
            client / model_name: v2.4.4 起，显式覆盖 LLM 上下文（取代 push_agent_context 栈）。
                传 None 时使用 AppState 默认。
            source: 工具调用来源（状态栏显示用，如 ``master`` / ``local``）。
                传 None 时取当前上下文的来源标记（见 :func:`tool_source_scope`）。
        """
        # 结构化 trace：一次工具调用 = 一个 span（kind="tool"）
        # 没有上层 span 时，start_span 会自成一个独立 trace（trace_id 自成一体）
        with start_span(tool_name, kind="tool", tool=tool_name,
                        args=_summarize_kwargs(kwargs)) as span:
            # v2.8.7(UX)：把"正在调什么工具、传了什么参数、谁在调"上报到状态栏。
            # 此前状态栏的 tool_name 字段从未被赋值，工具执行分支是死代码 ——
            # 用户只能看到 spinner，看不到到底在跑什么。
            src = source if source is not None else _TOOL_SOURCE.get()
            status_ctx = _report_tool_start(self.state, tool_name, kwargs, src)
            try:
                result = self._invoke_tool_impl(tool_name, kwargs, msgs=msgs,
                                                skip_security=skip_security,
                                                client=client, model_name=model_name)
            except Exception as e:
                _report_tool_end(status_ctx, error=str(e), tool_name=tool_name)
                _echo_tool_result(self.state, tool_name, ok=False, error=str(e), source=src)
                raise
            _report_tool_end(status_ctx,
                             error=result.error if not result.is_ok() else "",
                             tool_name=tool_name)
            _echo_tool_result(self.state, tool_name,
                              ok=result.is_ok(),
                              error=result.error if not result.is_ok() else "",
                              source=src)
            if result.is_ok():
                span.set_attribute("success", True)
            else:
                span.set_attribute("success", False)
                span.mark_error(result.error or "工具执行失败")
            return result

    def _invoke_tool_impl(self, tool_name, kwargs, msgs=None, skip_security=False,
                          client=None, model_name=None):
        """invoke_tool 的实际执行体（trace 埋点见 invoke_tool）。

        事件派发逻辑（dispatch_event）保持原样，不受埋点影响。
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
