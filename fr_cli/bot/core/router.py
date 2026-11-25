"""
消息路由 —— 决定一条入站消息要不要理、怎么处理

v2.8.7 新增。

fr-cli 此前完全没有这层：REPL 里用户主动输入，天然都是"要处理的"。
bot 面对的是**公共消息流** —— 群里每个人说的每句话都会推过来，
必须先判定"是不是在叫我"，否则机器人会对着不相干的聊天插嘴。

默认规则（按优先级）：

  1. 空消息 / 只有 @ 噪声 → 忽略
  2. 私聊 → 直接应答
  3. 群聊：
     - 不在群白名单 → 忽略
     - 未 @ 机器人 → 忽略
     - @ 了机器人 → 应答（并剥离 @ 前缀）
  4. 正文以 ``/`` 开头 → 走命令通道（而非 AI 对话）

规则可注册扩展：``router.add_rule(RouteRule(...))``
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from fr_cli.bot.core.message import BotMessage

__all__ = ["RouteDecision", "RouteRule", "Router"]


@dataclass
class RouteDecision:
    """路由结果。

    Attributes:
        handled:  是否要处理（False = 忽略）
        action:   处理方式 —— "chat"（AI 对话）/ "command"（命令）/ "ignore"
        text:     清理后的正文（已剥离 @ 机器人等噪声）
        reason:   忽略 / 处理的原因（用于日志与调试）
    """

    handled: bool
    action: str = "chat"
    text: str = ""
    reason: str = ""

    @classmethod
    def ignore(cls, reason: str = "") -> "RouteDecision":
        return cls(handled=False, action="ignore", reason=reason)

    @classmethod
    def chat(cls, text: str, reason: str = "") -> "RouteDecision":
        return cls(handled=True, action="chat", text=text, reason=reason)

    @classmethod
    def command(cls, text: str, reason: str = "") -> "RouteDecision":
        return cls(handled=True, action="command", text=text, reason=reason)


@dataclass
class RouteRule:
    """一条自定义路由规则。

    Attributes:
        name:     规则名（调试用）
        matcher:  ``(BotMessage) -> bool``
        action:   命中后的动作 —— "chat" / "command" / "ignore"
        priority: 数值越小越先匹配
        strip:    是否剥离 @ 机器人前缀
    """

    name: str
    matcher: Callable[[BotMessage], bool]
    action: str = "chat"
    priority: int = 100
    strip: bool = False


class Router:
    """入站消息路由器。

    Args:
        bot_names:     机器人的名字（用于剥离 @xxx），空则用 ``mentioned`` 标记
        group_whitelist: 允许响应的群 id 列表；None = 不限制
        require_mention_in_group: 群里是否必须 @ 才响应
        command_prefix: 命令前缀（默认 "/"）
    """

    def __init__(self, bot_names: Optional[List[str]] = None,
                 group_whitelist: Optional[List[str]] = None,
                 require_mention_in_group: bool = True,
                 command_prefix: str = "/"):
        self.bot_names = [n for n in (bot_names or []) if n]
        self.group_whitelist = set(group_whitelist) if group_whitelist else None
        self.require_mention_in_group = require_mention_in_group
        self.command_prefix = command_prefix
        self._rules: List[RouteRule] = []

    # ---------- 自定义规则 ----------

    def add_rule(self, rule: RouteRule) -> None:
        """注册一条自定义规则。"""
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority)

    def clear_rules(self) -> None:
        self._rules = []

    # ---------- 路由 ----------

    def route(self, message: BotMessage) -> RouteDecision:
        """判定一条消息如何处理。"""
        text = (message.text or "").strip()

        # 自定义规则优先（优先级数值小 = 先匹配）
        for rule in self._rules:
            try:
                if rule.matcher(message):
                    cleaned = self._strip_mention(text) if rule.strip else text
                    if rule.action == "ignore":
                        return RouteDecision.ignore(f"规则 [{rule.name}] 命中")
                    if rule.action == "command":
                        return RouteDecision.command(cleaned, f"规则 [{rule.name}] 命中")
                    return RouteDecision.chat(cleaned, f"规则 [{rule.name}] 命中")
            except Exception:
                continue

        if not text:
            return RouteDecision.ignore("空消息")

        # 私聊：直接应答
        if message.is_private or not self.require_mention_in_group:
            # 即使是群聊，若通道声明不需要 @（如 Telegram），也直接应答
            pass

        is_group = bool(message.user_id) and message.chat_id != message.user_id
        if is_group:
            if self.group_whitelist is not None and message.chat_id not in self.group_whitelist:
                return RouteDecision.ignore(f"群不在白名单: {message.chat_id}")
            if self.require_mention_in_group and not message.mentioned:
                return RouteDecision.ignore("群聊中未被 @")

        cleaned = self._strip_mention(text)
        if not cleaned:
            return RouteDecision.ignore("剥离 @ 后为空")

        if cleaned.startswith(self.command_prefix):
            return RouteDecision.command(cleaned, "命令前缀")

        return RouteDecision.chat(cleaned, "正常对话")

    # ---------- 工具 ----------

    def _strip_mention(self, text: str) -> str:
        """剥离正文开头的 @机器人 提及。

        支持 ``@botname`` 与 ``@botname:`` 两种写法（飞书/Telegram 常见）。
        """
        if not text:
            return ""
        out = text.strip()
        for name in self.bot_names:
            for prefix in (f"@{name}:", f"@{name}"):
                if out.lower().startswith(prefix.lower()):
                    out = out[len(prefix):].strip()
                    break
        return out.strip()

    def describe(self) -> dict:
        """路由配置自述（用于 /bot_status）。"""
        return {
            "bot_names": self.bot_names,
            "group_whitelist": sorted(self.group_whitelist) if self.group_whitelist else None,
            "require_mention_in_group": self.require_mention_in_group,
            "command_prefix": self.command_prefix,
            "custom_rules": [r.name for r in self._rules],
        }
