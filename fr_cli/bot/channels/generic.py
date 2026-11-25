"""
通用 webhook 通道 —— 所有平台适配的基准实现

v2.8.7 新增。

背景：fr-cli 此前只有出站推送（``fr_cli/weapon/notifier.py``），没有任何入站
消息接收。做 bot 的第一步不是去接某个具体平台，而是先立一个**基准通道**：
把「验签 → 解析 → 回发」这三件事的骨架定下来，其余平台（飞书 / Telegram）
照抄骨架、只替换平台差异。

职责边界：
  - 网关层（HTTP 路由）负责把 ``POST /webhook/<channel>/<chat_id>`` 的
    path 与 query 拆出来，通道**只处理 payload**；
  - 通道把平台 payload 翻译成统一消息 :class:`BotMessage`，把统一回复
    :class:`BotReply` 翻译成平台请求；
  - 上层（路由 / 会话 / 去重 / 确认）**不认识任何平台**，因此新增平台时
    不需要改动上层一行代码。

配置（``self.config``）：
    token       共享口令 —— 请求须带 header ``X-Bot-Token`` 或 query ``?token=``
    secret      共享密钥 —— 若请求带 header ``X-Bot-Signature``，按 HMAC-SHA256
                校验原始 body；不带签名头则跳过（便于只配 token 的场景）
    field_map   字段映射 —— ``{"统一字段": "payload 路径"}``，路径支持 ``a.b.c``
    reply_url   回发地址 —— 不配置则退化为「仅接收不发送」模式
"""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Dict, Optional
from urllib.parse import parse_qs

import requests

from fr_cli.bot.core.channel import Channel, ChannelError, register_channel
from fr_cli.bot.core.message import BotMessage, BotReply

__all__ = ["GenericChannel", "DEFAULT_FIELD_MAP"]

# 默认字段映射：统一字段名 → payload 内路径
DEFAULT_FIELD_MAP: Dict[str, str] = {
    "text": "text",
    "chat_id": "chat_id",
    "user_id": "user_id",
    "message_id": "message_id",
    "thread_id": "thread_id",
}

# 出站 HTTP 默认超时（秒）
DEFAULT_TIMEOUT = 10


def get_header(headers: Any, name: str, default: str = "") -> str:
    """大小写不敏感地取一个 header。

    网关层可能传 ``dict``，也可能传 ``http.server`` 的 ``Message`` 对象，
    这里统一处理；找不到返回 ``default``。
    """
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


def extract_field(payload: Dict[str, Any], path: str) -> Any:
    """按路径从 payload 取值，路径支持 ``a.b.c`` 与 ``a.0.b``。"""
    if not path:
        return None
    current: Any = payload
    for part in str(path).split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.lstrip("-").isdigit():
            index = int(part)
            if -len(current) <= index < len(current):
                current = current[index]
            else:
                return None
        else:
            return None
    return current


def as_text(value: Any) -> str:
    """把任意字段值转成正文字符串。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def secure_equal(left: str, right: str) -> bool:
    """恒定时间比较两个字符串（按 UTF-8 字节比较，兼容非 ASCII 口令）。"""
    try:
        return hmac.compare_digest(str(left).encode("utf-8"), str(right).encode("utf-8"))
    except Exception:
        return False


@register_channel
class GenericChannel(Channel):
    """通用 webhook 通道。

    任何「往 fr-cli 推一条 JSON」的场景都能用本通道接住，无需为平台单独
    写代码；字段名不对时用 ``field_map`` 改映射即可。
    """

    name = "generic"
    supports_threads = True
    supports_streaming = False
    requires_mention_in_group = False

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._field_map: Dict[str, str] = dict(DEFAULT_FIELD_MAP)
        self._field_map.update(self.config.get("field_map") or {})

    # ---------- 入站 ----------

    def verify(self, headers: Dict[str, Any], payload: Any) -> bool:
        """共享口令校验。

        配置了 ``token`` 时，请求必须带 header ``X-Bot-Token`` 或 query
        ``?token=``，且值与配置一致；否则直接拒绝（恒定时间比较）。
        """
        token = str(self.config.get("token") or "")
        if not token:
            return True

        provided = get_header(headers, "X-Bot-Token")
        if not provided:
            provided = self._query_token(headers, payload)
        if not provided:
            return False
        return secure_equal(provided, token)

    def parse(self, headers: Dict[str, Any], payload: Any) -> Optional[BotMessage]:
        """按 ``field_map`` 把 payload 翻译成统一消息。"""
        if not isinstance(payload, dict):
            raise ChannelError("generic 通道要求 payload 为 JSON 对象")

        chat_id = as_text(extract_field(payload, self._field_map.get("chat_id", "chat_id")))
        if not chat_id:
            raise ChannelError("generic payload 缺少 chat_id")

        raw_text = as_text(extract_field(payload, self._field_map.get("text", "text")))
        user_id = as_text(extract_field(payload, self._field_map.get("user_id", "user_id")))
        message_id = as_text(extract_field(payload, self._field_map.get("message_id", "message_id")))
        thread_id = as_text(extract_field(payload, self._field_map.get("thread_id", "thread_id")))

        text = raw_text.strip()
        # mentioned 仅在用户显式配置映射时才从 payload 取，否则用配置兜底
        mentioned_path = self._field_map.get("mentioned")
        mentioned = extract_field(payload, mentioned_path) if mentioned_path else None
        if mentioned is None:
            mentioned = bool(self.config.get("always_mentioned", False))
        else:
            mentioned = bool(mentioned)
        return BotMessage(
            channel=self.name,
            chat_id=chat_id,
            user_id=user_id,
            user_name=as_text(extract_field(payload, self._field_map.get("user_name", "user_name"))),
            thread_id=thread_id,
            text=text,
            raw_text=raw_text,
            message_id=message_id,
            mentioned=mentioned,
            is_command=text.startswith("/"),
            raw=payload,
        )

    # ---------- 出站 ----------

    def send(self, reply: BotReply) -> BotReply:
        """把回复 POST 到 ``reply_url``。

        未配置 ``reply_url`` 时不报错地失败，而是回填 ``error`` —— 明确表达
        「本通道只收不发」，而不是抛异常打断上层流程。
        """
        url = str(self.config.get("reply_url") or "")
        if not url:
            reply.error = "generic 通道未配置 reply_url（仅接收不发送模式）"
            return reply

        body: Dict[str, Any] = {
            "chat_id": reply.chat_id,
            "text": reply.text,
            "thread_id": reply.thread_id,
            "reply_to": reply.reply_to,
            "markdown": reply.markdown,
        }
        headers = {"Content-Type": "application/json; charset=utf-8"}
        signature = self._sign(body)
        if signature:
            headers["X-Bot-Signature"] = signature

        try:
            response = requests.post(url, json=body, headers=headers, timeout=self._timeout())
        except Exception as exc:
            reply.error = f"generic 发送失败: {exc}"
            return reply

        if response.status_code >= 400:
            reply.error = f"generic 返回 {response.status_code}: {response.text[:200]}"
            return reply

        try:
            reply.extra.setdefault("response", response.json())
        except Exception:
            reply.extra.setdefault("response", response.text[:200])
        return reply

    # ---------- 内部 ----------

    def _timeout(self) -> int:
        try:
            return int(self.config.get("timeout", DEFAULT_TIMEOUT))
        except (TypeError, ValueError):
            return DEFAULT_TIMEOUT

    def _query_token(self, headers: Any, payload: Any) -> str:
        """从 query 里取 token。

        网关层可能把 query 以原始字符串（``QUERY_STRING``）、dict 形式
        （``query``）透传，两种都兼容。
        """
        raw = get_header(headers, "QUERY_STRING")
        if raw:
            values = parse_qs(raw).get("token") or []
            if values:
                return values[0]
        for source in (headers, payload):
            if not isinstance(source, dict):
                continue
            query = source.get("query")
            if isinstance(query, dict):
                value = query.get("token")
                if value:
                    return str(value)
        return ""

    def _sign(self, body: Dict[str, Any]) -> str:
        """用 ``secret`` 给出站 body 签名（HMAC-SHA256，hex）。"""
        secret = str(self.config.get("secret") or "")
        if not secret:
            return ""
        raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hmac.new(secret.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()

    def describe(self) -> Dict[str, Any]:
        info = super().describe()
        info.update({
            "can_send": bool(self.config.get("reply_url")),
            "require_token": bool(self.config.get("token")),
        })
        return info
