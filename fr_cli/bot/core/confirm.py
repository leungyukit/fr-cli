"""
Bot 确认策略 —— 把四阶安全确认搬到聊天窗口

v2.8.7 新增。

fr-cli 原有的确认机制是终端 ``input()``（``fr_cli/security/security.py``），
在 bot 里必然挂死。而"直接全部放行 / 全部拒绝"两个极端都不可接受：
高危操作（写文件、发邮件、跑 shell）需要**人**在聊天窗口里点头。

本模块实现 :class:`BotConfirmStrategy`：把 ``security.ask`` 的
Y/A/F/N 四阶语义映射到 IM 对话：

  ==============  ==================================================
  fr-cli 语义      bot 行为
  ==============  ==================================================
  y (本次放行)     用户回复 y/yes → 本次放行
  a (本会话放行)   用户回复 a → 本会话内该类别放行
  f (永久放行)     用户回复 f → 写入 config（谨慎使用）
  n / 空           用户回复 n 或超时 → 拒绝
  ==============  ==================================================

超时**按拒绝处理**（fail-closed）：没人应答时绝不放行。
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fr_cli.security.strategy import ConfirmDecision, ConfirmStrategy

__all__ = ["BotConfirmStrategy", "format_confirm_question"]

#: 用户回复 → 决策的映射
_ANSWER_MAP = {
    "y": ("once", True),
    "yes": ("once", True),
    "是": ("once", True),
    "好": ("once", True),
    "确认": ("once", True),
    "a": ("session", True),
    "always": ("session", True),
    "总是": ("session", True),
    "f": ("forever", True),
    "forever": ("forever", True),
    "永久": ("forever", True),
    "n": ("", False),
    "no": ("", False),
    "否": ("", False),
    "拒绝": ("", False),
}

#: 安全类别 → 中文描述
_CATEGORY_LABEL = {
    "sec_read": "读取文件",
    "sec_write": "写入/修改文件",
    "sec_exec": "执行命令",
    "sec_shell": "执行 Shell 命令",
    "sec_fetch_web": "访问网络",
    "sec_gen_img": "生成图片",
    "sec_mail": "收发邮件",
    "sec_mcp": "调用外部 MCP 工具",
}


def format_confirm_question(key: str, target: str, tool_name: str = "",
                           lang: str = "zh") -> str:
    """生成给用户看的确认问题（IM 里应该是短句 + 明确的操作对象）。"""
    label = _CATEGORY_LABEL.get(key, key)
    lines = [f"需要确认：{label}"]
    if tool_name:
        lines.append(f"工具：{tool_name}")
    lines.append(f"目标：{target}")
    lines.append("请回复 y 允许本次 / a 本会话允许 / f 永久允许 / n 拒绝")
    return "\n".join(lines)


class BotConfirmStrategy(ConfirmStrategy):
    """把安全确认发到聊天窗口，等用户回复。

    Args:
        ask_user: 回调 ``(question: str, timeout: int) -> str``
                   —— 负责把问题发出去并等回答案。超时返回空串。
        timeout:  等待回复的秒数
        lang:     语言
        config:   配置（f 选项会写入这里）
    """

    name = "bot"

    def __init__(self, ask_user: Callable[[str, int], str], timeout: int = 120,
                 lang: str = "zh", config: Optional[Dict[str, Any]] = None):
        super().__init__(lang=lang, config=config)
        self.ask_user = ask_user
        self.timeout = timeout

    def check(self, key: str, target: str, tool_name: str = "",
              args: Optional[Dict[str, Any]] = None) -> ConfirmDecision:
        question = format_confirm_question(key, target, tool_name, self.lang)
        try:
            answer = self.ask_user(question, self.timeout)
        except Exception as e:
            return ConfirmDecision.deny(f"确认通道异常，默认拒绝: {e}")

        answer = (answer or "").strip().lower()
        if not answer:
            return ConfirmDecision.deny("用户未确认或已超时")

        scope, allowed = _ANSWER_MAP.get(answer, ("", False))
        if not allowed:
            return ConfirmDecision.deny(f"用户拒绝（回复: {answer}）")

        if scope == "session":
            self.sconfirm[key] = True
        elif scope == "forever":
            self.sconfirm[key] = True
            self.fconfirm[key] = True
            self.config["auto_confirm"] = dict(self.fconfirm)
        return ConfirmDecision.allow(scope)
