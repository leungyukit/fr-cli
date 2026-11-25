"""
通道抽象 —— 统一适配层的基类

v2.8.7 新增。

设计目标：新增一个 IM 平台 = 新增一个 ``fr_cli/bot/channels/<平台>.py``，
只需实现本类定义的 3 个方法（verify / parse / send），上层路由、会话、
去重、确认全部复用，**不做任何平台特判**。

刻意保持**同步**接口：
fr-cli 现有的三套 HTTP 服务（agent/server.py、hermes_api.py、
web/console/handler.py）都基于标准库 ``http.server`` 的同步模型。
若通道层改成 async，就得把这三套一起重写 —— 得不偿失。
Bot 网关用 ``ThreadingHTTPServer``，天然并发。

线程约定：
  - 每个 HTTP 请求在自己的线程里跑
  - ``parse`` / ``send`` 必须**线程安全**（无跨请求可变状态，
    或用 ``threading.Lock`` 保护）
  - 出站发送可能阻塞（网络 IO），建议设置合理超时
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fr_cli.bot.core.message import BotMessage, BotReply

__all__ = ["Channel", "ChannelError", "register_channel", "get_channel_class",
           "list_channel_classes"]


class ChannelError(Exception):
    """通道层异常（验签失败 / 解析失败 / 发送失败）。"""


class Channel:
    """消息通道基类。

    子类必须实现：
      - :meth:`parse`   —— 把平台 payload 解析成 :class:`BotMessage`
      - :meth:`send`    —— 把 :class:`BotReply` 发回平台

    可选覆写：
      - :meth:`verify`  —— 验签 / 鉴权（默认放行）
      - :meth:`describe` —— 通道能力自述（用于 /bot_status）
    """

    # 通道标识（子类覆盖）
    name: str = "base"
    # 是否支持话题 / 线程
    supports_threads: bool = False
    # 是否支持流式分段推送（否则整段发）
    supports_streaming: bool = False
    # 是否需要在群里被 @ 才响应
    requires_mention_in_group: bool = True

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    # ---------- 入站 ----------

    def verify(self, headers: Dict[str, Any], payload: Any) -> bool:
        """校验请求来源（签名 / token / challenge）。

        Returns:
            True 表示校验通过；False 表示拒绝。
        异常同样视为拒绝（由网关层捕获）。
        """
        return True

    def parse(self, headers: Dict[str, Any], payload: Any) -> Optional[BotMessage]:
        """把平台 payload 解析成统一消息。

        Returns:
            :class:`BotMessage`；该 payload 不是消息（如 challenge 响应）时返回 None。
        """
        raise NotImplementedError(f"{type(self).__name__} 未实现 parse()")

    def challenge_response(self, headers: Dict[str, Any], payload: Any) -> Optional[Dict[str, Any]]:
        """平台握手挑战（飞书 url_verification 等）。

        Returns:
            需要回给平台的 JSON dict；无挑战时返回 None。
        """
        return None

    # ---------- 出站 ----------

    def send(self, reply: BotReply) -> BotReply:
        """把回复发回平台。

        Returns:
            同一个 :class:`BotReply` 对象（失败时填入 ``error``）。
        """
        raise NotImplementedError(f"{type(self).__name__} 未实现 send()")

    def send_stream(self, chat_id: str, chunks: List[str], thread_id: str = "") -> BotReply:
        """分段推送（默认退化为一次性发送）。

        不支持流式的通道直接拼接后发送。
        """
        return self.send(BotReply(chat_id=chat_id, text="".join(chunks), thread_id=thread_id))

    # ---------- 自述 ----------

    def describe(self) -> Dict[str, Any]:
        """通道能力自述（用于 /bot_status 与健康检查）。"""
        return {
            "name": self.name,
            "supports_threads": self.supports_threads,
            "supports_streaming": self.supports_streaming,
            "requires_mention_in_group": self.requires_mention_in_group,
        }


# ------------------------------------------------------------------
# 通道注册表
# ------------------------------------------------------------------

_channel_classes: Dict[str, type] = {}


def register_channel(cls):
    """类装饰器 —— 把通道实现登记到全局注册表。

    用法::

        @register_channel
        class LarkChannel(Channel):
            name = "lark"
    """
    name = getattr(cls, "name", "")
    if not name or name == "base":
        raise ValueError(f"通道类 {cls.__name__} 必须定义唯一的 name")
    _channel_classes[name] = cls
    return cls


def get_channel_class(name: str) -> Optional[type]:
    """按名字取通道类。"""
    return _channel_classes.get(name)


def list_channel_classes() -> List[str]:
    """列出所有已登记的通道名。"""
    return sorted(_channel_classes.keys())


def get_channel(name: str, config: Optional[Dict[str, Any]] = None) -> Optional[Channel]:
    """实例化一个通道。"""
    cls = get_channel_class(name)
    if cls is None:
        return None
    return cls(config or {})
