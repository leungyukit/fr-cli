"""
Bot 核心层 —— 与平台无关的部分

消息模型 / 通道抽象 / 路由 / 去重 / 会话隔离 / 确认 / 状态池 / 调度器。
"""
from fr_cli.bot.core.channel import (
    Channel,
    ChannelError,
    get_channel,
    get_channel_class,
    list_channel_classes,
    register_channel,
)
from fr_cli.bot.core.confirm import BotConfirmStrategy, format_confirm_question
from fr_cli.bot.core.confirm_broker import ConfirmBroker
from fr_cli.bot.core.dispatcher import BotDispatcher, BotResult
from fr_cli.bot.core.idempotency import IdempotencyGuard
from fr_cli.bot.core.message import BotMessage, BotReply
from fr_cli.bot.core.router import RouteDecision, RouteRule, Router
from fr_cli.bot.core.session_store import SessionStore
from fr_cli.bot.core.state_pool import StatePool

__all__ = [
    "BotMessage",
    "BotReply",
    "Channel",
    "ChannelError",
    "register_channel",
    "get_channel",
    "get_channel_class",
    "list_channel_classes",
    "Router",
    "RouteRule",
    "RouteDecision",
    "IdempotencyGuard",
    "SessionStore",
    "StatePool",
    "BotDispatcher",
    "BotResult",
    "BotConfirmStrategy",
    "format_confirm_question",
    "ConfirmBroker",
]
