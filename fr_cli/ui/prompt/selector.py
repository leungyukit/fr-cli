"""
方向键选择器 —— 多选项确认的 TUI 交互

v2.8.7 第四阶段。

问题
----
TUI 里"提示用户选择"此前一律让用户**敲选项的值**（安全确认是 y/a/f/n）：

    [!] 检测到高危神通，请选择因果:
      >> 写入法宝: /tmp/a.txt
        [Y]仅此  [A]本轮  [F]永世  [N]拒绝

两个实际缺陷：
1. 用户得先记住该敲哪个字母，敲错要重试一轮；
2. 选项信息印在**上方**，而输入框在下方 —— 视线要来回切，还容易把字母
   打进输入框里当成聊天消息发出去。

改法
----
把选项直接渲染在输入区**上方一行**，用 **↑↓（或 ←→）移动、Enter 确认**：

    ⚠ 待确认 写入法宝: /tmp/a.txt
      ❯ Y 仅此     A 本轮     F 永世     N 拒绝
                        ↑ 当前选中项

约定
----
* 选择器**不感知终端** —— 只管状态与渲染，键盘由调用方（``ui/prompt/tui.py``）
  转发给它；
* 非 TTY 环境（批处理 / HTTP / bot）**没有方向键可按**，仍走文本输入 ——
  见 ``security/security.py::ask`` 的裸 ``input()`` 分支。
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

#: 渲染用的样式类（与 ui/prompt/tui.py 的 _PROMPT_STYLE 对齐）
STYLE_TITLE = "class:status-red"
STYLE_SELECTED = "class:status-cyan"
STYLE_UNSELECTED = "class:status-gray"
STYLE_SEP = "class:status-sep"


class Choice:
    """一个可选项。"""

    __slots__ = ("value", "label", "hint")

    def __init__(self, value: str, label: str, hint: str = ""):
        self.value = value
        self.label = label
        self.hint = hint

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"Choice({self.value!r}, {self.label!r})"


class Selector:
    """一个待用户选择的多选项提示。

    只负责**状态**（当前选中项）与**渲染**，不碰键盘 —— 键盘事件由调用方
    转成 :meth:`move` / :meth:`confirm` 调用。
    """

    def __init__(self, title: str, desc: str = "",
                 choices: Sequence[Choice] = ()):
        self.title = title
        self.desc = desc
        self.choices: List[Choice] = list(choices)
        self.index = 0

    # ---------- 状态 ----------

    @property
    def current(self) -> Optional[Choice]:
        """当前选中的选项（没有选项时返回 None）"""
        if not self.choices:
            return None
        return self.choices[self.index % len(self.choices)]

    @property
    def current_value(self) -> Optional[str]:
        c = self.current
        return c.value if c else None

    def move(self, delta: int) -> bool:
        """移动选中项（循环）。返回是否真的移动了。"""
        if not self.choices or len(self.choices) == 1:
            return False
        self.index = (self.index + delta) % len(self.choices)
        return True

    def select(self, value: str) -> bool:
        """按值定位选中项（找不到返回 False）"""
        for i, c in enumerate(self.choices):
            if c.value == value:
                self.index = i
                return True
        return False

    # ---------- 渲染 ----------

    #: 单行渲染时选项后面的操作提示
    HINT = "↑↓ 选择 · Enter 确认"

    @staticmethod
    def _width(text: str) -> int:
        """显示宽度（CJK 算 2 列）"""
        try:
            from fr_cli.ui.ui import get_display_width
            return get_display_width(text)
        except Exception:
            return len(text)

    def render_items(self, width: int = 0) -> List[Tuple[str, str]]:
        """渲染成 prompt_toolkit 的 FormattedText 列表（**单行**）。

        为什么是单行、且选项排最左：
        prompt_toolkit 的 bottom_toolbar 是 ``dont_extend_height`` 的单行窗口，
        多行会被裁掉；而按显示宽度裁剪时**右边先没** —— 选项若排在末尾，
        窄终端上恰好把最该看见的东西截没了。选项放最左即可保证可见。

        Args:
            width: 可用宽度（列）；<= 0 表示不限制
        """
        out: List[Tuple[str, str]] = []
        if not self.choices:
            return out

        for i, c in enumerate(self.choices):
            if i:
                out.append((STYLE_SEP, "  "))
            selected = (i == self.index)
            label = f"{c.value.upper()} {c.label}"
            if selected:
                out.append((STYLE_SELECTED, f"❯ {label}"))
            else:
                out.append((STYLE_UNSELECTED, f"  {label}"))

        title = self.title or ""
        if self.desc:
            title = f"{title}: {self.desc}"

        if width and width > 8:
            used = sum(self._width(t) for _s, t in out)
            used += self._width(" │ ") * 2
            avail = width - used
            if avail < 4:
                # 没空间放目标了 —— 只留一个省略号（选项与提示仍然可见）
                title = "…"
            elif self._width(title) > avail:
                title = title[:max(2, avail - 1)] + "…"

        out.append((STYLE_SEP, " │ "))
        out.append((STYLE_TITLE, title))
        out.append((STYLE_SEP, " │ "))
        out.append((STYLE_UNSELECTED, self.HINT))
        return out

    def render_line(self) -> str:
        """纯文本一行（给非 TTY / 日志用）"""
        parts = []
        for i, c in enumerate(self.choices):
            mark = "❯" if i == self.index else " "
            parts.append(f"{mark} {c.value} {c.label}")
        return "   ".join(parts)
