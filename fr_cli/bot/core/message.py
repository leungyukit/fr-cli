"""
Bot 消息领域模型 —— 跨平台统一的消息表示

v2.8.7 新增。

背景：fr-cli 此前**完全没有消息领域模型**（全仓无 chat_id / user_id /
thread_id 概念），所有 IM 平台只有出站 webhook。要做 bot，第一步就是
定义一个与平台无关的消息结构，让上层（路由 / 会话 / 去重 / 确认）只面向
这一种对象编程，平台差异全部收敛在 ``fr_cli/bot/channels/`` 里。
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

__all__ = ["BotMessage", "BotReply"]


@dataclass
class BotMessage:
    """一条入站消息（平台无关）。

    Attributes:
        channel:    通道标识（"lark" / "telegram" / "wecom" / ...）
        chat_id:    会话 id（私聊为用户 id，群聊为群 id）
        user_id:    发送者 id
        user_name:  发送者显示名
        thread_id:  话题 / 线程 id（无则空串）
        text:       正文（已剥离 @机器人 等噪声）
        raw_text:   原始正文（未剥离）
        message_id: 平台消息 id（去重键的来源）
        ts:         时间戳
        mentioned:  是否 @ 了机器人
        is_command: 是否以 / 开头（命令前缀）
        reply_to:   被回复的消息 id
        raw:        平台原始 payload（供通道内部使用）
    """

    channel: str
    chat_id: str
    user_id: str = ""
    user_name: str = ""
    thread_id: str = ""
    text: str = ""
    raw_text: str = ""
    message_id: str = ""
    ts: float = field(default_factory=time.time)
    mentioned: bool = False
    is_command: bool = False
    reply_to: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    # ---------- 派生属性 ----------

    @property
    def session_key(self) -> str:
        """会话键 —— 会话隔离与上下文摘要的索引。

        同一群里的不同话题是不同会话；私聊与群聊也天然分开。
        """
        return f"{self.channel}:{self.chat_id}:{self.thread_id}"

    @property
    def dedup_key(self) -> str:
        """去重键 —— 平台会重投 webhook，必须幂等。

        优先用平台 message_id；缺失时用 时间戳+正文 的哈希兜底。
        """
        if self.message_id:
            return f"{self.channel}:{self.message_id}"
        digest = hashlib.sha1(
            f"{self.chat_id}|{self.user_id}|{self.text}|{self.ts:.3f}".encode("utf-8")
        ).hexdigest()[:16]
        return f"{self.channel}:anon:{digest}"

    @property
    def is_private(self) -> bool:
        """是否私聊（群聊里通常需要 @ 才响应）。"""
        return not self.thread_id and self.chat_id == self.user_id

    def with_text(self, text: str) -> "BotMessage":
        """返回替换了正文的新消息（便于通道层剥离 @ 前缀）。"""
        clone = BotMessage(**{**self.__dict__})
        clone.text = text
        return clone

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel": self.channel,
            "chat_id": self.chat_id,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "thread_id": self.thread_id,
            "text": self.text,
            "message_id": self.message_id,
            "ts": self.ts,
            "mentioned": self.mentioned,
            "is_command": self.is_command,
        }

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return (f"BotMessage(channel={self.channel!r}, chat_id={self.chat_id!r}, "
                f"user={self.user_id!r}, text={self.text[:40]!r})")


@dataclass
class BotReply:
    """一条出站回复（平台无关）。

    Attributes:
        chat_id:   目标会话
        text:      正文
        thread_id: 话题 / 线程
        reply_to:  被回复的消息 id
        markdown:  是否按 markdown 渲染（由通道自行降级）
        error:     错误信息（发送失败时）
        extra:     通道特定参数（如卡片、按钮）
    """

    chat_id: str
    text: str
    thread_id: str = ""
    reply_to: str = ""
    markdown: bool = True
    error: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None
