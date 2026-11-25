"""
Bot 调度器 —— 入站消息 → 执行内核 → 回复文本

v2.8.7 新增。

这是「统一适配层」的执行入口：**平台无关**。
上层通道只需把平台 payload 解析成 :class:`BotMessage` 交给这里，
剩下的（路由 / 去重 / 会话隔离 / 确认 / 执行 / 落盘）全部复用。

执行路径：

    BotMessage
      → Router.route()          要不要理（群里是否 @ 我）
      → IdempotencyGuard        是不是重投
      → 命令？ → registry.dispatch_cmd()
      → 否则  → handle_ai_chat()（无头模式）
      → SessionStore            读写该会话的消息与摘要（按 session_key 隔离）

安全：
  - 每次执行都把 ``state.security`` 的策略换成 :class:`BotConfirmStrategy`，
    高危工具的确认会被发回聊天窗口；超时按拒绝处理
  - 会话之间绝不共享 messages —— 由 :class:`StatePool` 保证
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Dict, Optional

from fr_cli.bot.core.confirm import BotConfirmStrategy
from fr_cli.bot.core.confirm_broker import ConfirmBroker
from fr_cli.bot.core.idempotency import IdempotencyGuard
from fr_cli.bot.core.message import BotMessage
from fr_cli.bot.core.router import Router
from fr_cli.bot.core.session_store import SessionStore
from fr_cli.bot.core.state_pool import StatePool

__all__ = ["BotDispatcher", "BotResult"]


class BotResult:
    """一次处理的果。

    Attributes:
        reply:      要发给用户的文本（空串表示不回复）
        handled:    是否被处理
        action:     "chat" / "command" / "ignore"
        error:      错误信息
        session_key: 归属会话
    """

    __slots__ = ("reply", "handled", "action", "error", "session_key", "reason")

    def __init__(self, reply: str = "", handled: bool = False, action: str = "ignore",
                 error: Optional[str] = None, session_key: str = "", reason: str = ""):
        self.reply = reply
        self.handled = handled
        self.action = action
        self.error = error
        self.session_key = session_key
        self.reason = reason

    @property
    def ok(self) -> bool:
        return self.error is None

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return (f"BotResult(handled={self.handled}, action={self.action!r}, "
                f"reply={self.reply[:40]!r}, error={self.error!r})")


class BotDispatcher:
    """入站消息调度器。

    Args:
        state_pool:    状态池（提供隔离的运行时）
        session_store: 会话存储（按 session_key 隔离）
        router:        路由器
        idempotency:   去重守卫
        confirm_broker: 确认请求配对中心
        ask_user:      发消息给用户的回调 ``(channel, chat_id, thread_id, text) -> None``
                       —— 用于把确认问题发回聊天窗口
        command_handler: 自定义命令处理 ``(state, text) -> str``；默认走注册表
    """

    def __init__(self, state_pool: StatePool,
                 session_store: Optional[SessionStore] = None,
                 router: Optional[Router] = None,
                 idempotency: Optional[IdempotencyGuard] = None,
                 confirm_broker: Optional[ConfirmBroker] = None,
                 ask_user: Optional[Callable[..., None]] = None,
                 command_handler: Optional[Callable[[Any, str], str]] = None):
        self.state_pool = state_pool
        self.session_store = session_store or SessionStore()
        self.router = router or Router()
        self.idempotency = idempotency or IdempotencyGuard()
        self.confirm_broker = confirm_broker or ConfirmBroker()
        self.ask_user = ask_user
        self.command_handler = command_handler
        # REPL 命令层靠 stdout 传结果，重定向需串行化
        self._stdout_lock = threading.Lock()

    # ---------- 主入口 ----------

    def handle(self, message: BotMessage) -> BotResult:
        """处理一条入站消息。"""
        session_key = message.session_key

        # 1) 路由：要不要理
        decision = self.router.route(message)
        if not decision.handled:
            return BotResult(action="ignore", reason=decision.reason, session_key=session_key)

        # 2) 去重：平台重投
        if self.idempotency.check_and_mark(message.dedup_key):
            return BotResult(action="ignore", session_key=session_key)

        # 3) 执行
        try:
            if decision.action == "command":
                reply = self._run_command(message, decision.text)
            else:
                reply = self._run_chat(message, decision.text)
        except Exception as e:
            return BotResult(action=decision.action, error=str(e), session_key=session_key)

        return BotResult(reply=reply or "", handled=True, action=decision.action,
                         session_key=session_key)

    def deliver_answer(self, message: BotMessage) -> bool:
        """把一条用户回复投给正在等待的确认请求。

        Returns:
            True 表示这条消息被当作确认应答消费掉了（不应再当作普通提问处理）。
        """
        return self.confirm_broker.deliver(
            message.channel, message.chat_id, message.text or "", message.thread_id
        )

    # ---------- 命令 ----------

    def _run_command(self, message: BotMessage, text: str) -> str:
        """执行一条 slash 命令。

        两级分发：
          1. **注册表工具**（``registry.dispatch_cmd``）—— 覆盖 ``@register`` 的
             全部工具（邮件 / 定时 / 通知 / 云盘 / MCP / Agent / 构建 ...）
          2. **REPL 命令**（``repl.router.dispatch``）—— 覆盖 ``/model``、
             ``/ls`` 这类只在 REPL 层注册的命令；stdout 会被收集成回复正文
        """
        if self.command_handler:
            with self.state_pool.acquire() as state:
                return self.command_handler(state, text)

        from fr_cli.command.executor import _build_deps
        from fr_cli.command.registry import get_registry

        with self.state_pool.acquire() as state:
            deps = _build_deps(state)
            result = get_registry().dispatch_cmd(deps, text, msgs=state.get_messages())
            if result is not None and not (hasattr(result, "error") and result.error):
                data = getattr(result, "data", result)
                if isinstance(data, str):
                    return data
                return "" if data is None else str(data)

            # 注册表不认识 → 退回 REPL 命令层
            return self._run_repl_command(state, text)

    def _run_repl_command(self, state, text: str) -> str:
        """走 REPL 路由执行命令，并把 stdout 收集成回复正文。

        REPL 命令层的处理器直接 print，不返回内容。bot 需要把结果发回
        聊天窗口，所以这里把 stdout 重定向到缓冲区。
        """
        import contextlib
        import io

        from fr_cli.repl.router import dispatch as repl_dispatch

        buf = io.StringIO()
        # stdout 重定向是进程级的 —— 用锁串行化，避免多个会话互相污染
        with self._stdout_lock:
            try:
                with contextlib.redirect_stdout(buf):
                    repl_dispatch(state, text)
            except Exception as e:
                return f"[!] 命令执行失败: {e}"
        return buf.getvalue().strip()

    # ---------- 对话 ----------

    def _run_chat(self, message: BotMessage, text: str) -> str:
        """跑一次 AI 对话（无头模式）。"""
        from fr_cli.core.chat import handle_ai_chat

        session_key = message.session_key
        with self.state_pool.acquire() as state:
            # 装入该会话的上下文（隔离：只取本 session_key 的）
            state.set_messages(self.session_store.get_messages(session_key))
            state.context_summary = self.session_store.get_summary(session_key)

            # 把安全确认接到聊天窗口
            self._install_confirm_strategy(state, message)

            handle_ai_chat(state, text)

            # 回存该会话
            self.session_store.set_messages(session_key, state.get_messages())
            self.session_store.set_summary(session_key, state.context_summary)

            return getattr(state, "last_reply", "") or ""

    def _install_confirm_strategy(self, state, message: BotMessage) -> None:
        """把确认策略换成聊天窗口确认。"""
        broker = self.confirm_broker
        ask_user = self.ask_user

        def _ask(question: str, timeout: int) -> str:
            if ask_user:
                try:
                    ask_user(message.channel, message.chat_id, message.thread_id, question)
                except Exception:
                    pass
            return broker.ask(message.channel, message.chat_id, question,
                              message.thread_id, timeout)

        strategy = BotConfirmStrategy(_ask, timeout=broker.default_timeout,
                                      lang=getattr(state, "lang", "zh"),
                                      config=getattr(state, "cfg", None))
        try:
            state.security.set_strategy(strategy)
        except Exception:
            pass

    # ---------- 自述 ----------

    def stats(self) -> Dict[str, Any]:
        """统计信息（用于 /bot_status）。"""
        return {
            "pool": self.state_pool.stats(),
            "sessions": self.session_store.stats(),
            "idempotency": self.idempotency.stats(),
            "confirm": self.confirm_broker.stats(),
            "router": self.router.describe(),
        }
