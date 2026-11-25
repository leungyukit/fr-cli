"""
Telegram 通道 —— Bot API Webhook 入站 + sendMessage 出站

v2.8.7 新增。

背景：Telegram 的 Bot API 是最「标准」的 webhook 形态：POST 一个 update
对象，回一个 ``{"ok": true, ...}``。本通道按 Bot API 语义实现，差异点：

  - ``chat.id`` 是整数，统一转成字符串（上层只认字符串 id）；
  - 群里命令常见写法是 ``/cmd@botname args``，需要把 ``@botname`` 剥掉，
    否则命令名会被当成 ``cmd@botname`` 而匹配不到；
  - Telegram 群里 bot 默认只收到「被 @ 的消息」（隐私模式），因此
    ``requires_mention_in_group = False``，收到即可视为在跟机器人说话。

验签：Telegram 用 header ``X-Telegram-Bot-Api-Secret-Token`` 携带共享口令，
与配置的 ``secret`` 常量时间比较即可。
"""
from __future__ import annotations

import hmac
from typing import Any, Dict, Optional

import requests

from fr_cli.bot.core.channel import Channel, ChannelError, register_channel
from fr_cli.bot.core.message import BotMessage, BotReply

__all__ = ["TelegramChannel"]

# Telegram Bot API 地址
TELEGRAM_API_BASE = "https://api.telegram.org"

# 出站 HTTP 默认超时（秒）
DEFAULT_TIMEOUT = 10


def _get_header(headers: Any, name: str, default: str = "") -> str:
    """大小写不敏感地取一个 header（dict 与 http.server Message 都兼容）。"""
    if headers is None:
        return default
    getter = getattr(headers, "get", None)
    if getter is not None:
        try:
            value = getter(name)
        except Exception:  # pragma: no cover - 防御 exotic header 对象
            value = None
        if value is not None:
            return value if isinstance(value, str) else str(value)
    try:
        items = headers.items()
    except Exception:
        return default
    for key, value in items:
        if str(key).lower() == name.lower():
            return value if isinstance(value, str) else str(value)
    return default


def strip_bot_suffix(text: str) -> str:
    """把命令里的 ``@botname`` 后缀剥掉。

    ``"/cmd@bot args"`` → ``"/cmd args"``；``"/cmd args"`` → 原样返回。
    """
    if not text.startswith("/"):
        return text
    head, sep, tail = text.partition(" ")
    if "@" in head:
        head = head.split("@", 1)[0]
    return f"{head}{sep}{tail}"


def _secure_equal(left: str, right: str) -> bool:
    """恒定时间比较两个字符串（按 UTF-8 字节比较，兼容非 ASCII 口令）。"""
    try:
        return hmac.compare_digest(str(left).encode("utf-8"), str(right).encode("utf-8"))
    except Exception:
        return False


@register_channel
class TelegramChannel(Channel):
    """Telegram 通道。"""

    name = "telegram"
    supports_threads = False
    supports_streaming = False
    # Telegram 群里 bot 只收到被 @ 的消息，收到即视为在跟机器人说话
    requires_mention_in_group = False

    # ---------- 入站 ----------

    def verify(self, headers: Dict[str, Any], payload: Any) -> bool:
        """校验 ``X-Telegram-Bot-Api-Secret-Token``。"""
        secret = str(self.config.get("secret") or "")
        if not secret:
            return True
        provided = _get_header(headers, "X-Telegram-Bot-Api-Secret-Token")
        if not provided:
            return False
        return _secure_equal(provided, secret)

    def parse(self, headers: Dict[str, Any], payload: Any) -> Optional[BotMessage]:
        """把 update 翻译成统一消息。"""
        if not isinstance(payload, dict):
            raise ChannelError("Telegram payload 必须是 JSON 对象")

        message = (payload.get("message")
                   or payload.get("edited_message")
                   or payload.get("channel_post"))
        if not isinstance(message, dict):
            # 非消息更新（callback_query 等）——上层不关心
            return None

        chat = message.get("chat") or {}
        chat_id = str(chat.get("id") or "")
        if not chat_id:
            raise ChannelError("Telegram update 缺少 chat.id")

        sender = message.get("from") or {}
        user_id = str(sender.get("id") or "")
        user_name = str(sender.get("first_name") or sender.get("username") or "")

        raw_text = str(message.get("text") or message.get("caption") or "")
        text = strip_bot_suffix(raw_text).strip()

        reply_to_message = message.get("reply_to_message") or {}
        reply_to = str(reply_to_message.get("message_id") or "") if isinstance(reply_to_message, dict) else ""

        chat_type = str(chat.get("type") or "")
        return BotMessage(
            channel=self.name,
            chat_id=chat_id,
            user_id=user_id,
            user_name=user_name,
            thread_id="",
            text=text,
            raw_text=raw_text,
            message_id=str(message.get("message_id") or ""),
            mentioned=self._mentioned(chat_type, message),
            is_command=text.startswith("/"),
            reply_to=reply_to,
            raw=payload,
        )

    # ---------- 出站 ----------

    def send(self, reply: BotReply) -> BotReply:
        """通过 Bot API sendMessage 把回复发回会话。"""
        bot_token = str(self.config.get("bot_token") or "")
        if not bot_token:
            reply.error = "Telegram 未配置 bot_token"
            return reply

        body: Dict[str, Any] = {
            "chat_id": reply.chat_id,
            "text": reply.text,
        }
        if reply.reply_to:
            body["reply_to_message_id"] = reply.reply_to
        if reply.markdown:
            body["parse_mode"] = "Markdown"

        url = f"{TELEGRAM_API_BASE}/bot{bot_token}/sendMessage"
        try:
            response = requests.post(url, json=body, timeout=self._timeout())
        except Exception as exc:
            reply.error = f"Telegram 发送失败: {exc}"
            return reply

        if response.status_code != 200:
            reply.error = f"Telegram 返回 {response.status_code}: {response.text[:200]}"
            return reply

        data: Dict[str, Any] = {}
        try:
            data = response.json() or {}
        except Exception:
            data = {}

        if not data.get("ok"):
            reply.error = f"Telegram 错误: {data.get('description', data)}"
            return reply

        message_id = str((data.get("result") or {}).get("message_id") or "")
        if message_id:
            reply.extra.setdefault("message_id", message_id)
        return reply

    # ---------- 内部 ----------

    def _timeout(self) -> int:
        try:
            return int(self.config.get("timeout", DEFAULT_TIMEOUT))
        except (TypeError, ValueError):
            return DEFAULT_TIMEOUT

    def _mentioned(self, chat_type: str, message: Dict[str, Any]) -> bool:
        """判断是否 @ 了机器人。

        私聊天然指向机器人；群里看 entities 里有没有 mention —— Telegram
        隐私模式下 bot 只收到被 @ 的消息，故没有 entities 时按「已提及」处理。
        """
        if chat_type == "private":
            return True
        entities = message.get("entities") or []
        for entity in entities:
            if isinstance(entity, dict) and entity.get("type") in ("mention", "text_mention"):
                return True
        return not entities

    def describe(self) -> Dict[str, Any]:
        info = super().describe()
        info.update({
            "can_send": bool(self.config.get("bot_token")),
            "require_secret": bool(self.config.get("secret")),
        })
        return info
