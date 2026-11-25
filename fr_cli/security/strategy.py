"""
安全确认策略层 —— 可注入的确认机制

v2.8.7 新增。

背景：原 ``fr_cli/security/security.py::ask()`` 把确认逻辑硬编码为终端
``input()`` —— 无超时、无重试上限、非 TTY 下抛 EOFError。这让 fr-cli
无法被当作 bot / 服务端进程运行（每个需要确认的工具调用都会挂死）。

本模块把"谁来决定放不放行"抽象为策略对象：

  - :class:`TerminalStrategy`  终端交互（默认，行为与 v2.8.6 完全一致）
  - :class:`AutoDenyStrategy`   非交互默认拒绝（fail-closed）
  - :class:`AutoAllowStrategy`  批量放行（脚本 / CI）
  - :class:`CallbackStrategy`   外部回调决策（bot：把问题发回聊天窗口等人回答）

``SecurityManager`` 持有策略并委托之；策略可随时替换，无需改动工具层。

设计约束：
  - 策略层**不感知终端**，只有 TerminalStrategy 打印提示
  - 策略返回 :class:`ConfirmDecision` 而非裸 bool，便于携带 scope 与理由
  - 全部策略共享同一套 fconfirm(永久) / sconfirm(本次会话) 语义
"""
from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional

__all__ = [
    "ConfirmDecision",
    "ConfirmStrategy",
    "TerminalStrategy",
    "AutoDenyStrategy",
    "AutoAllowStrategy",
    "CallbackStrategy",
    "build_default_strategy",
]


class ConfirmDecision:
    """一次确认的结果。

    Attributes:
        allowed: 是否放行
        reason:  理由（拒绝时展示给用户）
        scope:   放行范围 —— "once" / "session" / "forever" / ""(不放行)
    """

    __slots__ = ("allowed", "reason", "scope")

    def __init__(self, allowed: bool, reason: str = "", scope: str = ""):
        self.allowed = bool(allowed)
        self.reason = reason
        self.scope = scope

    def __bool__(self) -> bool:
        return self.allowed

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"ConfirmDecision(allowed={self.allowed}, scope={self.scope!r}, reason={self.reason!r})"

    @classmethod
    def allow(cls, scope: str = "once", reason: str = "") -> "ConfirmDecision":
        return cls(True, reason, scope)

    @classmethod
    def deny(cls, reason: str = "") -> "ConfirmDecision":
        return cls(False, reason, "")


class ConfirmStrategy:
    """确认策略基类。

    子类只需实现 :meth:`check`。
    """

    name = "base"

    def __init__(self, lang: str = "zh", config: Optional[Dict[str, Any]] = None):
        self.lang = lang
        self.config = config if config is not None else {}
        # 永久放行（按 sec_* 类别）—— 与 v2.4.4+ 的 dict 语义一致
        self.fconfirm: Dict[str, bool] = dict(self.config.get("auto_confirm") or {})
        # 本次会话放行（按 sec_* 类别）—— 不持久化
        self.sconfirm: Dict[str, bool] = {}

    # ---------- 子类实现 ----------

    def check(self, key: str, target: str, tool_name: str = "",
              args: Optional[Dict[str, Any]] = None) -> ConfirmDecision:
        """判断是否放行。

        Args:
            key:       安全类别（sec_read / sec_write / sec_exec / sec_shell ...）
            target:    确认提示里展示的目标（路径或工具名）
            tool_name: 工具名（供 tool 级权限与 bot 决策使用）
            args:      工具参数（供 tool 级路径规则使用）
        """
        raise NotImplementedError

    # ---------- 公共状态管理 ----------

    def clear_session(self) -> None:
        """清除本次会话放行状态。"""
        self.sconfirm = {}

    def clear_all(self) -> None:
        """清除全部永久放行状态（/unconfirm 语义）。"""
        self.fconfirm = {}
        self.sconfirm = {}

    def _persisted_auto_confirm(self) -> None:
        """把 fconfirm 写回配置（供 TerminalStrategy 的 F 选项使用）。"""
        if self.fconfirm:
            self.config["auto_confirm"] = dict(self.fconfirm)
        else:
            self.config.pop("auto_confirm", None)


class TerminalStrategy(ConfirmStrategy):
    """终端交互确认 —— 与 v2.8.6 行为完全一致。

    委托 ``fr_cli.security.security.ask``，保留 Y/A/F/N 四阶语义：
      y = 本次放行 / a = 本会话本类别放行 / f = 永久放行 / n = 拒绝
    """

    name = "terminal"

    def check(self, key: str, target: str, tool_name: str = "",
              args: Optional[Dict[str, Any]] = None) -> ConfirmDecision:
        from fr_cli.security.security import ask

        allowed, sconfirm, fconfirm = ask(
            key, target, self.lang, self.fconfirm, self.sconfirm, self.config
        )
        self.sconfirm = sconfirm if isinstance(sconfirm, dict) else {}
        self.fconfirm = fconfirm if isinstance(fconfirm, dict) else {}
        return ConfirmDecision.allow("once") if allowed else ConfirmDecision.deny("用户拒绝")


class AutoDenyStrategy(ConfirmStrategy):
    """非交互环境 —— 默认拒绝（fail-closed）。

    这是 bot / 服务端进程在"没有确认通道"时的安全默认值。
    """

    name = "auto_deny"

    def check(self, key: str, target: str, tool_name: str = "",
              args: Optional[Dict[str, Any]] = None) -> ConfirmDecision:
        return ConfirmDecision.deny("非交互环境默认拒绝该操作")


class AutoAllowStrategy(ConfirmStrategy):
    """全部放行 —— 脚本 / CI / 已人工确认过的批量场景。

    ⚠️ 等价于永久按 F，等于沙箱全废。仅在明确受控时使用。
    """

    name = "auto_allow"

    def check(self, key: str, target: str, tool_name: str = "",
              args: Optional[Dict[str, Any]] = None) -> ConfirmDecision:
        return ConfirmDecision.allow("forever", "批量放行")


class CallbackStrategy(ConfirmStrategy):
    """外部回调决策 —— bot 场景专用。

    把"是否放行"的决定权交给外部 resolver。典型用法（IM 机器人）：

        def resolver(key, target, tool_name, args):
            bot.send_confirm_prompt(key, target)          # 在聊天窗口发确认卡片
            answer = bot.wait_for_reply(timeout=120)      # 等用户回复
            if answer in ("y", "yes"):
                return ConfirmDecision.allow("once")
            if answer in ("a",):
                return ConfirmDecision.allow("session")
            return ConfirmDecision.deny("用户拒绝")

    resolver 也可以直接返回 bool / str（"allow" / "deny"），会被归一化。
    resolver 抛异常时**按拒绝处理**（fail-closed），绝不因确认通道故障
    而放行高危操作。
    """

    name = "callback"

    def __init__(self, resolver: Callable[..., Any], lang: str = "zh",
                 config: Optional[Dict[str, Any]] = None):
        super().__init__(lang=lang, config=config)
        self.resolver = resolver

    def check(self, key: str, target: str, tool_name: str = "",
              args: Optional[Dict[str, Any]] = None) -> ConfirmDecision:
        try:
            outcome = self.resolver(key, target, tool_name, args or {})
        except Exception as e:
            return ConfirmDecision.deny(f"确认通道异常，默认拒绝: {e}")

        if isinstance(outcome, ConfirmDecision):
            return outcome
        if isinstance(outcome, bool):
            return ConfirmDecision.allow("once") if outcome else ConfirmDecision.deny("用户拒绝")
        if isinstance(outcome, str):
            lowered = outcome.strip().lower()
            if lowered in ("y", "yes", "allow", "a", "session", "f", "forever", "true", "1"):
                scope = "forever" if lowered in ("f", "forever") else (
                    "session" if lowered in ("a", "session") else "once"
                )
                self._record_scope(key, scope)
                return ConfirmDecision.allow(scope)
            return ConfirmDecision.deny(outcome or "用户拒绝")
        return ConfirmDecision.deny("确认通道返回了无法识别的结果")

    def _record_scope(self, key: str, scope: str) -> None:
        """记录放行范围（session / forever），与终端策略语义保持一致。"""
        if scope == "session":
            self.sconfirm[key] = True
        elif scope == "forever":
            self.sconfirm[key] = True
            self.fconfirm[key] = True
            self.config["auto_confirm"] = dict(self.fconfirm)


def build_default_strategy(lang: str = "zh",
                            config: Optional[Dict[str, Any]] = None,
                            non_interactive: Optional[bool] = None) -> ConfirmStrategy:
    """按环境构造默认策略。

    - ``FR_CLI_NON_INTERACTIVE`` 存在 → AutoDenyStrategy（fail-closed）
    - 否则 → TerminalStrategy（保持 v2.8.6 行为）
    """
    if non_interactive is None:
        non_interactive = bool(os.environ.get("FR_CLI_NON_INTERACTIVE"))
    if non_interactive:
        return AutoDenyStrategy(lang=lang, config=config)
    return TerminalStrategy(lang=lang, config=config)
