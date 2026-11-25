"""
飞书（Lark / Feishu）通道 —— 事件订阅 v2 入站 + 应用消息 API 出站

v2.8.7 新增。

背景：飞书是 fr-cli 用户最常用的协作平台之一，但 ``notifier.py`` 里只有
「飞书机器人 webhook 推送」，**没有入站** —— 用户在飞书里说的话，fr-cli
听不见。本通道把飞书事件订阅的 payload 翻译成统一消息，并把统一回复发回
飞书会话。

入站格式（事件订阅 v2）：
    {
      "schema": "2.0",
      "header": {"event_id": "...", "event_type": "im.message.receive_v1",
                 "token": "...", "create_time": "1700000000000"},
      "event": {
        "sender": {"sender_id": {"open_id": "ou_xxx"}, "sender_type": "user"},
        "message": {"message_id": "om_xxx", "chat_id": "oc_xxx",
                    "chat_type": "group", "message_type": "text",
                    "content": "{\\"text\\":\\"你好\\"}",
                    "root_id": "...", "parent_id": "..."}
      }
    }

两个坑：
  1. ``content`` 是 **JSON 字符串**，要二次 ``json.loads`` 才能拿到 ``text``；
  2. 群聊里飞书要求 @ 机器人 —— 但 mentions 无法从 content 可靠还原，
     只能看 ``mentions`` 字段（每项带 ``key``）。

验签（**简化实现**，非飞书官方 encrypt_key 流程）：
    飞书真实算法是 ``sha256(timestamp + nonce + encrypt_key + body)`` 的
    变体且依赖加密 body。本实现按约定直接对 ``timestamp + nonce + secret +
    body`` 取 SHA256 十六进制，与 header ``X-Lark-Signature`` 比对，并要求
    时间戳与当前时间偏差不超过 1 小时（防重放）。

出站：飞书应用消息 API，需要 ``tenant_access_token``；若只配了
``app_id`` / ``app_secret``，则自动换取 token 并按过期时间缓存。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
import time
from typing import Any, Dict, List, Optional

import requests

from fr_cli.bot.core.channel import Channel, ChannelError, register_channel
from fr_cli.bot.core.message import BotMessage, BotReply

__all__ = ["LarkChannel"]

# 飞书开放平台地址
LARK_API_BASE = "https://open.feishu.cn/open-apis"
LARK_SEND_URL = f"{LARK_API_BASE}/im/v1/messages"
LARK_TOKEN_URL = f"{LARK_API_BASE}/auth/v3/tenant_access_token/internal"

# 消息事件类型
MESSAGE_EVENT = "im.message.receive_v1"

# 时间戳允许的最大偏差（秒）—— 超过即视为重放
MAX_TIMESTAMP_SKEW = 3600

# 出站 HTTP 默认超时（秒）
DEFAULT_TIMEOUT = 10

# 飞书在正文里用来占位的 @ 标记（形如 @_user_1）
MENTION_PLACEHOLDER = re.compile(r"@_user_\d+")


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


def _epoch_seconds(raw: str) -> Optional[float]:
    """把时间戳字符串转成秒（秒 / 毫秒都兼容）。"""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value > 1e11:  # 毫秒
        value = value / 1000.0
    return value


def _secure_equal(left: str, right: str) -> bool:
    """恒定时间比较两个字符串（按 UTF-8 字节比较，兼容非 ASCII 密钥）。"""
    try:
        return hmac.compare_digest(str(left).encode("utf-8"), str(right).encode("utf-8"))
    except Exception:
        return False


def _raw_body(headers: Any, payload: Any) -> str:
    """取出参与签名的原始 body。

    网关层拿到的是原始字节串，最稳妥的做法是把原始 body 透传给通道。
    这里依次尝试常见载体，取不到时用 payload 重新序列化兜底。
    """
    for key in ("body", "raw_body", "REQUEST_BODY"):
        value = _get_header(headers, key)
        if value:
            return value
    if isinstance(payload, dict):
        value = payload.get("raw_body")
        if isinstance(value, str) and value:
            return value
        if isinstance(value, (bytes, bytearray)):
            return bytes(value).decode("utf-8", "replace")
    try:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except Exception:
        return ""


@register_channel
class LarkChannel(Channel):
    """飞书通道。"""

    name = "lark"
    supports_threads = True
    supports_streaming = False
    requires_mention_in_group = True

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        # tenant_access_token 缓存（多线程网关下需加锁）
        self._token_lock = threading.Lock()
        self._token: str = ""
        self._token_expire: float = 0.0

    # ---------- 入站 ----------

    def verify(self, headers: Dict[str, Any], payload: Any) -> bool:
        """验签 + verification_token 校验。

        - 配置了 ``verification_token``：比对 payload ``header.token``；
        - 配置了 ``secret``：比对 header ``X-Lark-Signature``（SHA256 十六进制），
          并要求时间戳与当前时间偏差不超过 1 小时。
        """
        header = {}
        if isinstance(payload, dict):
            header = payload.get("header") or {}

        verification_token = str(self.config.get("verification_token") or "")
        if verification_token:
            token = str(header.get("token") or "")
            if not _secure_equal(token, verification_token):
                return False

        secret = str(self.config.get("secret") or "")
        if not secret:
            return True

        signature = _get_header(headers, "X-Lark-Signature")
        if not signature:
            return False

        timestamp = (_get_header(headers, "X-Lark-Request-Timestamp")
                     or _get_header(headers, "X-Lark-Timestamp")
                     or str(header.get("create_time") or ""))
        if not timestamp:
            return False
        nonce = (_get_header(headers, "X-Lark-Request-Nonce")
                 or _get_header(headers, "X-Lark-Nonce"))

        epoch = _epoch_seconds(timestamp)
        if epoch is None:
            return False
        if abs(time.time() - epoch) > MAX_TIMESTAMP_SKEW:
            return False

        body = _raw_body(headers, payload)
        expect = hashlib.sha256(
            f"{timestamp}{nonce}{secret}{body}".encode("utf-8")
        ).hexdigest()
        return _secure_equal(signature.strip().lower(), expect)

    def challenge_response(self, headers: Dict[str, Any], payload: Any) -> Optional[Dict[str, Any]]:
        """飞书事件订阅的 url_verification 握手。"""
        if not isinstance(payload, dict):
            return None
        if payload.get("type") == "url_verification" and payload.get("challenge"):
            return {"challenge": payload.get("challenge")}
        return None

    def parse(self, headers: Dict[str, Any], payload: Any) -> Optional[BotMessage]:
        """把飞书事件翻译成统一消息。"""
        if not isinstance(payload, dict):
            raise ChannelError("飞书 payload 必须是 JSON 对象")

        header = payload.get("header") or {}
        event = payload.get("event") or {}

        event_type = str(header.get("event_type") or "")
        if event_type and event_type != MESSAGE_EVENT:
            # 非消息事件（卡片回调、通讯录变更等）——上层不关心
            return None

        message = event.get("message") or {}
        chat_id = str(message.get("chat_id") or "")
        if not chat_id:
            raise ChannelError("飞书事件缺少 chat_id")

        raw_text = self._decode_content(message.get("content"), message.get("message_type"))
        mentions = self._mentions(event, message)
        mentioned = any(str(item.get("key") or "") for item in mentions)

        # 群聊里飞书把 @ 机器人写成占位符（@_user_1），需剥离才是干净正文
        text = MENTION_PLACEHOLDER.sub("", raw_text).strip()
        if mentioned and not text:
            text = raw_text.strip()

        sender = event.get("sender") or {}
        sender_id = sender.get("sender_id") or {}
        user_id = str(sender_id.get("open_id") or sender_id.get("user_id") or "")
        user_name = self._sender_name(mentions, user_id)

        parent_id = str(message.get("parent_id") or "")
        root_id = str(message.get("root_id") or "")

        return BotMessage(
            channel=self.name,
            chat_id=chat_id,
            user_id=user_id,
            user_name=user_name,
            # 话题：parent_id 非空说明这是一条话题内消息
            thread_id=parent_id,
            text=text,
            raw_text=raw_text,
            message_id=str(message.get("message_id") or ""),
            mentioned=mentioned,
            is_command=text.startswith("/"),
            # 被回复的消息优先取 parent_id，其次取话题根
            reply_to=parent_id or root_id,
            raw=payload,
        )

    # ---------- 出站 ----------

    def send(self, reply: BotReply) -> BotReply:
        """通过飞书应用消息 API 把回复发回会话。"""
        try:
            token = self._access_token()
        except ChannelError as exc:
            reply.error = str(exc)
            return reply
        if not token:
            reply.error = "飞书未配置 tenant_access_token，也未配置 app_id/app_secret"
            return reply

        body = {
            "receive_id": reply.chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": reply.text}, ensure_ascii=False),
            # 话题内回复时带上 reply_in_thread
            "reply_in_thread": bool(reply.thread_id),
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

        try:
            response = requests.post(
                LARK_SEND_URL,
                params={"receive_id_type": "chat_id"},
                json=body,
                headers=headers,
                timeout=self._timeout(),
            )
        except Exception as exc:
            reply.error = f"飞书发送失败: {exc}"
            return reply

        if response.status_code != 200:
            reply.error = f"飞书返回 {response.status_code}: {response.text[:200]}"
            return reply

        data: Dict[str, Any] = {}
        try:
            data = response.json() or {}
        except Exception:
            data = {}

        code = data.get("code", 0)
        if code != 0:
            reply.error = f"飞书错误(code={code}): {data.get('msg', data)}"
            return reply

        message_id = str((data.get("data") or {}).get("message_id") or "")
        if message_id:
            reply.extra.setdefault("message_id", message_id)
        return reply

    # ---------- 内部 ----------

    def _timeout(self) -> int:
        try:
            return int(self.config.get("timeout", DEFAULT_TIMEOUT))
        except (TypeError, ValueError):
            return DEFAULT_TIMEOUT

    def _decode_content(self, content: Any, message_type: Any) -> str:
        """解析飞书 content（JSON 字符串）里的正文。"""
        if content is None:
            return ""
        if isinstance(content, dict):
            data: Dict[str, Any] = content
        else:
            try:
                data = json.loads(content)
            except (TypeError, ValueError):
                return str(content)
        if not isinstance(data, dict):
            return str(content)
        text = data.get("text")
        if isinstance(text, str):
            return text
        if str(message_type or "text") == "text":
            # 文本消息但没有 text 字段 —— 视为空正文
            return ""
        # 非文本消息（图片 / 文件 / 富文本）——退化为原始 JSON，便于上层判断
        try:
            return json.dumps(data, ensure_ascii=False)
        except Exception:
            return str(content)

    def _mentions(self, event: Dict[str, Any], message: Dict[str, Any]) -> List[Dict[str, Any]]:
        """取 mentions 列表（message 级优先，event 级兜底）。"""
        for source in (message, event):
            mentions = source.get("mentions")
            if isinstance(mentions, list):
                items = [item for item in mentions if isinstance(item, dict)]
                if items:
                    return items
        return []

    def _sender_name(self, mentions: List[Dict[str, Any]], user_id: str) -> str:
        """从 mentions 里反查发送者显示名（飞书事件体本身不带用户名）。"""
        for item in mentions:
            mention_id = item.get("id") or {}
            mention_open_id = str(mention_id.get("open_id") or "")
            if user_id and mention_open_id and mention_open_id != user_id:
                continue
            name = str(item.get("name") or "")
            if name:
                return name
        return ""

    def _access_token(self) -> str:
        """取 tenant_access_token：配置直给，或用 app_id/app_secret 换取并缓存。"""
        configured = str(self.config.get("tenant_access_token") or "")
        if configured:
            return configured

        app_id = str(self.config.get("app_id") or "")
        app_secret = str(self.config.get("app_secret") or "")
        if not app_id or not app_secret:
            return ""

        with self._token_lock:
            now = time.time()
            if self._token and self._token_expire - 60 > now:
                return self._token

            try:
                response = requests.post(
                    LARK_TOKEN_URL,
                    json={"app_id": app_id, "app_secret": app_secret},
                    timeout=self._timeout(),
                )
            except Exception as exc:
                raise ChannelError(f"飞书换取 tenant_access_token 失败: {exc}")

            if response.status_code != 200:
                raise ChannelError(
                    f"飞书换取 tenant_access_token 返回 {response.status_code}: {response.text[:200]}"
                )
            try:
                data = response.json() or {}
            except Exception:
                raise ChannelError("飞书换取 tenant_access_token 返回非 JSON 内容")

            token = str(data.get("tenant_access_token") or "")
            if not token:
                raise ChannelError(f"飞书换取 tenant_access_token 失败: {data.get('msg', data)}")
            try:
                expire = int(data.get("expire", 7200))
            except (TypeError, ValueError):
                expire = 7200

            self._token = token
            self._token_expire = now + expire
            return token

    def describe(self) -> Dict[str, Any]:
        info = super().describe()
        info.update({
            "can_send": bool(self.config.get("tenant_access_token")
                             or (self.config.get("app_id") and self.config.get("app_secret"))),
            "require_signature": bool(self.config.get("secret")),
        })
        return info
