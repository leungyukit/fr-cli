"""
Bot 统一适配层 —— 让 fr-cli 能以机器人的身份收发消息

v2.8.7 新增。

fr-cli 此前只有**出站**通知（``fr_cli/weapon/notifier.py``：飞书/钉钉/
企微/Slack/Discord/Telegram 的 webhook 推送），**没有任何入站通道** ——
机器人在 IM 里说话，没人听得见。

本包提供「统一适配层」：

  ==================  ====================================================
  模块                 职责
  ==================  ====================================================
  ``core/message.py``  跨平台统一消息模型（BotMessage / BotReply）
  ``core/channel.py``  通道抽象基类 + 通道注册表（新增平台只需实现 3 个方法）
  ``core/router.py``   路由：群里要不要理（@ 判定 / 群白名单）
  ``core/idempotency.py`` 去重：平台会重投 webhook
  ``core/session_store.py`` 会话隔离：按 session_key 隔离消息与摘要
  ``core/confirm.py``  安全确认：把 Y/A/F/N 搬到聊天窗口
  ``core/confirm_broker.py`` 确认请求的跨线程配对
  ``core/state_pool.py`` 状态池：多个会话安全共享运行时
  ``core/dispatcher.py`` 调度器：入站消息 → 执行 → 回复
  ``runtime/gateway.py`` HTTP 网关：统一接收平台 webhook
  ``runtime/engine.py``  引擎：从配置装配出全部组件
  ``runtime/daemon.py``  守护进程：脱离 REPL 独立运行
  ``runtime/manager.py`` 进程管理：启停
  ``channels/``         各平台实现
  ==================  ====================================================

典型流程::

    平台 webhook ──► BotGateway(POST /bot/lark)
                        │ verify → parse → BotMessage
                        ▼
                     BotDispatcher
                        │ route → dedup → 执行
                        ▼
                     StatePool.acquire() → handle_ai_chat（无头模式）
                        │
                        ▼
                     回复经 Channel.send() 发回平台
"""
from fr_cli.bot.core.channel import (
    Channel,
    ChannelError,
    get_channel,
    get_channel_class,
    list_channel_classes,
    register_channel,
)
from fr_cli.bot.core.message import BotMessage, BotReply

__all__ = [
    "BotMessage",
    "BotReply",
    "Channel",
    "ChannelError",
    "register_channel",
    "get_channel",
    "get_channel_class",
    "list_channel_classes",
]
