"""
Streaming Markdown 实时渲染 —— 边输出边渲染

痛点:
- 当前 stream_cnt 是逐 token 输出,Markdown 在结束时才被渲染(等 markdown.py)
- 用户看到的是原始字符,标题/代码块/列表都没样式

方案:
- 状态机:跟踪当前在哪个 block(heading / paragraph / code / list / table)
- 逐行/逐 chunk 渲染:每次新行到来时,如果是新 block 就输出 block 头
- ANSI 颜色:标题 / 代码块 / 链接 / 粗体 / 列表项符号
- 性能:不要全文本重渲染,只渲染新行

状态机:
- NORMAL: 默认,等待新 block
- IN_CODE: 在 ``` 代码块里,等结束 ```
- IN_HEADING: 标题行
- IN_LIST: 列表项(支持嵌套)
- IN_TABLE: 表格
"""
import re
import shutil
from collections import deque
from typing import Dict, List, Optional

from fr_cli.ui import ui as _ui
from fr_cli.ui.syntax import highlight_code

# 本模块支持的动态颜色常量名(其余名字不走代理, 直接 AttributeError)
_COLOR_NAMES = (
    "RESET", "BOLD", "DIM", "RED", "GREEN", "YELLOW",
    "BLUE", "MAGENTA", "CYAN", "WHITE",
)


# ------------------------------------------------------------------
# 折叠参数
#
# 为什么阈值定在 60 行而不是 30：AI 回答**边生成边看**是这个产品的核心
# 体验，过早折叠会让用户在几十秒里看不到任何新内容（"卡住"感）。
# 60 行以上的回答已经足够长到把输入区顶出屏幕，这时折叠才有意义；
# 绝大多数正常回答（< 60 行）完全不受影响，流式体验零损失。
# ------------------------------------------------------------------
FOLD_THRESHOLD_LINES = 60   # 超过这么多行才折叠
FOLD_HEAD_LINES = 20        # 折叠前保留的头部行数
FOLD_TAIL_LINES = 10        # 折叠后保留的尾部行数（结论通常在最后）


def __getattr__(name: str) -> str:
    """颜色常量动态代理(PEP 562): 每次访问实时取 ui 模块当前值。

    历史漏洞(已修): 旧版在 import 时若发现 ui 处于禁色态(非 TTY / NO_COLOR),
    就把空常量"回填"成硬编码 ANSI 码, 等于主动推翻全局禁色决定。之后任何
    恢复颜色的路径(set_no_color(False) / reset_color)都会让本模块向非 TTY
    裸吐 \\033[96m 等序列, 在日志/文件/PTY 捕获端显示为 ?[96m 乱码。
    现在改为实时跟随: ui 禁色 → 这里就是空串, 拼不出任何转义序列。
    """
    if name in _COLOR_NAMES:
        return getattr(_ui, name, "")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _color(text: str, color: str, use_color: bool = True) -> str:
    """上色; use_color=False 或拿不到颜色码(全局禁色)时原样返回"""
    if not use_color or not color:
        return text
    reset = _ui.RESET
    return f"{color}{text}{reset}" if reset else text


def _sep_width() -> int:
    """分隔线宽度 —— 跟随终端宽度（不再硬编码 60）。

    窄终端下硬编码 60 会折行（变成两行横线，破坏版面）；宽终端下则右侧
    大片留白。取终端宽度并夹在 [20, 78] 之间。
    """
    try:
        cols = shutil.get_terminal_size(fallback=(80, 24)).columns
    except Exception:
        cols = 80
    return max(20, min(cols - 2, 78))


class StreamingMarkdownRenderer:
    """流式 Markdown 渲染器

    用法:
        renderer = StreamingMarkdownRenderer()
        for chunk in stream:
            rendered = renderer.feed(chunk)
            print(rendered, end="")
        remaining = renderer.flush()
        print(remaining)

    v2.8.7(UX) 新增
    ----------------
    * **代码块语法高亮**：走 ``fr_cli/ui/syntax.py``（零依赖），
      关键字/字符串/注释/数字分色，不再整块灰。
    * **超长回答折叠**：超过 ``fold_threshold`` 行后，中间内容折叠，
      尾部保留（结论通常在最后）；折叠掉的内容存进
      ``fr_cli/core/collapse.py``，REPL 里按 Ctrl+O 可原样展开。
    * **分隔线跟随终端宽度**：不再硬编码 60 列。
    * **表格列宽对齐**：中英混排不再列列歪斜。
    """

    def __init__(
        self,
        use_color: bool = True,
        code_lang_colors: bool = True,
        fold_threshold: int = FOLD_THRESHOLD_LINES,
        fold_tail: int = FOLD_TAIL_LINES,
    ):
        self.use_color = use_color
        self.code_lang_colors = code_lang_colors
        self.buffer = ""          # 未完成的 chunk
        self.state = "NORMAL"     # NORMAL / IN_CODE / IN_HEADING / IN_LIST / IN_TABLE
        self.code_lang = ""       # 当前代码块的语言
        self.code_buffer = []     # 代码块内容
        self.list_indent = 0      # 当前列表缩进
        self.in_table = False     # 是否在表格里
        self.line_count = 0       # 已输出行数
        self.block_count = 0      # block 数

        # ---- 折叠状态 ----
        self.fold_threshold = fold_threshold   # 超过这么多行才开始折叠
        self.fold_tail = fold_tail             # 折叠段末尾保留几行
        self._total_lines = 0                  # 已处理的总行数
        self._fold_started = False             # 是否已进入折叠态
        self._folded_lines: List[str] = []     # 被折叠的行（渲染后）
        self._tail_buffer: deque = deque(maxlen=fold_tail) if fold_tail else deque()

        # ---- 表格缓冲（对齐需要看到全部列宽）----
        self._table_rows: List[str] = []

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def feed(self, chunk: str) -> str:
        """喂入新 chunk,返回渲染后的输出"""
        self.buffer += chunk
        output_lines = []

        # 处理完整的行
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            rendered = self._process_line(line)
            if not rendered:
                continue

            self._total_lines += 1

            # 折叠判定：只在"回答确实很长"时才折叠，正常回答流式体验零损失
            if self._should_fold():
                if not self._fold_started:
                    self._fold_started = True
                    output_lines.append(self._fold_notice())
                self._folded_lines.append(rendered)
                self._tail_buffer.append(rendered)
                continue

            output_lines.append(rendered)
            self.line_count += 1

        # 处理代码块结束标记(可能在 buffer 里没换行)
        if self.state == "IN_CODE":
            # 暂时不输出,等 \n
            pass

        return "\n".join(output_lines) + ("\n" if output_lines else "")

    def flush(self) -> str:
        """flush 剩余 buffer（幂等：重复调用返回空，不会重复输出）"""
        # 表格缓冲：流结束时把没等到结束标记的表格也吐出来
        table_out = self._flush_table()
        # 折叠收尾：打印准确行数 + 尾部若干行，并把折叠内容登记待展开
        fold_out = self._flush_fold()

        if not self.buffer.strip():
            return table_out + fold_out

        if self.state == "IN_CODE":
            # 代码块未结束
            self.state = "NORMAL"
            self.code_buffer.append(self.buffer)
            out = "\n" + _color(self.buffer, _ui.DIM, self.use_color)
            self.buffer = ""  # 必须清空：否则二次 flush 会经 _process_line 再输出一遍
            return table_out + out + fold_out

        rendered = self._process_line(self.buffer)
        self.buffer = ""

        pieces = [p for p in (table_out, rendered or "", fold_out) if p]
        return "".join(pieces)

    def stats(self) -> Dict[str, int]:
        """渲染统计"""
        return {
            "lines": self.line_count,
            "blocks": self.block_count,
            "state": self.state,
        }

    # ------------------------------------------------------------------
    # 折叠
    # ------------------------------------------------------------------

    def _should_fold(self) -> bool:
        """当前这一行是否该进折叠区。

        只有当"总行数超过阈值"且"已输出行数到达阈值"时才折叠 —— 这样
        正常长度的回答完全不受影响（流式逐行可见），只有几百行的异常
        回答才会被折叠，避免把输入区顶出屏幕。
        """
        if not self.fold_threshold or self.fold_tail <= 0:
            return False
        if self._fold_started:
            return True
        return (self._total_lines > self.fold_threshold
                and self.line_count <= self.fold_threshold)

    def _fold_notice(self) -> str:
        """折叠开始时的提示行（此时行数还未知，用简短说法）

        结束时 :meth:`_flush_fold` 会再给一条带准确行数的总结提示 ——
        这条只负责告诉用户"内容停在这里了"，不重复行数信息。
        """
        return _color(
            "…（后续内容已折叠）…",
            _ui.YELLOW, self.use_color,
        )

    def _flush_fold(self) -> str:
        """折叠收尾：打印准确行数 + 尾部若干行，并把折叠内容登记待展开"""
        if not self._fold_started or not self._folded_lines:
            return ""

        total = len(self._folded_lines)
        tail = list(self._tail_buffer)
        # 中间被折叠掉的部分（尾部已经显示，不重复登记）
        middle = self._folded_lines[:max(0, total - len(tail))]

        # 登记 —— Ctrl+O 时原样打印
        try:
            from fr_cli.core.collapse import register
            register("\n".join(middle), meta=f"AI 回答 {total} 行")
        except Exception:
            pass

        self._fold_started = False
        self._folded_lines = []
        self._tail_buffer = deque(maxlen=self.fold_tail) if self.fold_tail else deque()

        notice = _color(
            f"… 已折叠 {total} 行 · Ctrl+O 展开 …",
            _ui.YELLOW, self.use_color,
        )
        tail_text = "\n".join(tail)
        return f"\n{notice}\n{tail_text}" if tail_text else f"\n{notice}"

    # ------------------------------------------------------------------
    # 单行处理
    # ------------------------------------------------------------------

    def _process_line(self, line: str) -> Optional[str]:
        """处理单行"""
        if self.state == "IN_CODE":
            return self._process_code_line(line)

        stripped = line.rstrip()

        # 表格行：先缓冲，等表格结束再统一对齐输出
        if stripped.startswith("|") and stripped.endswith("|") and len(stripped) > 1:
            self.in_table = True
            self._table_rows.append(stripped)
            return None

        # 不是表格行 —— 若有缓冲的表格，先把表格吐出来
        if self._table_rows:
            table_text = self._flush_table()
            rest = self._process_plain_line(stripped)
            if rest:
                return table_text + "\n" + rest
            return table_text

        if self.in_table:
            self.in_table = False

        return self._process_plain_line(stripped)

    def _process_plain_line(self, stripped: str) -> Optional[str]:
        """处理非代码块、非表格的普通行"""
        # 检测代码块开始
        if stripped.startswith("```"):
            self.state = "IN_CODE"
            self.code_lang = stripped[3:].strip()
            self.code_buffer = []
            self.block_count += 1
            lang_label = self.code_lang or "code"
            sep = "─" * _sep_width()
            return (_color(sep, _ui.DIM, self.use_color) + "\n"
                    + _color(f"{lang_label}", _ui.CYAN + _ui.BOLD, self.use_color))

        # 标题
        m = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            colors = [
                _ui.CYAN + _ui.BOLD, _ui.BLUE + _ui.BOLD, _ui.GREEN + _ui.BOLD, _ui.YELLOW + _ui.BOLD,
                _ui.MAGENTA + _ui.BOLD, _ui.RED + _ui.BOLD,
            ]
            color = colors[min(level - 1, len(colors) - 1)]
            self.block_count += 1
            prefix = "#" * level
            return _color(f"\n{prefix} {title}", color, self.use_color)

        # 水平线
        if re.match(r"^[-*_]{3,}\s*$", stripped):
            return _color("\n" + "─" * _sep_width() + "\n", _ui.DIM, self.use_color)

        # 列表
        list_match = re.match(r"^(\s*)([-*+]|\d+\.)\s+(.+)$", stripped)
        if list_match:
            indent = len(list_match.group(1))
            marker = list_match.group(2)
            content = list_match.group(3)
            bullet = "•" if marker in "-*+" else marker
            indent_str = "  " * (indent // 2)
            return indent_str + _color(bullet, _ui.CYAN + _ui.BOLD, self.use_color) + " " + self._render_inline(content)

        # 引用
        if stripped.startswith(">"):
            text = stripped[1:].strip()
            return _color("│ ", _ui.DIM, self.use_color) + _color(text, _ui.DIM, self.use_color)

        # 普通段落:渲染行内格式
        if not stripped:
            return ""  # 空行
        return self._render_inline(stripped)

    def _process_code_line(self, line: str) -> Optional[str]:
        """处理代码块内的行"""
        if line.rstrip().startswith("```"):
            # 代码块结束
            self.state = "NORMAL"
            sep = "─" * _sep_width()
            rendered = "\n" + _color(sep, _ui.DIM, self.use_color)
            self.code_buffer = []
            self.code_lang = ""
            return rendered
        # 代码内容 —— 语法高亮
        self.code_buffer.append(line)
        if self.code_lang_colors:
            return highlight_code(line, self.code_lang, use_color=self.use_color)
        return _color(line, _ui.DIM, self.use_color)

    # ------------------------------------------------------------------
    # 表格
    # ------------------------------------------------------------------

    def _flush_table(self) -> str:
        """把缓冲的表格按列宽对齐后输出"""
        rows = self._table_rows
        self._table_rows = []
        if not rows:
            return ""

        parsed = []
        sep_idx = set()
        for i, row in enumerate(rows):
            cells = [c.strip() for c in row.strip("|").split("|")]
            parsed.append(cells)
            # 分隔行（|---|---|）单独处理
            if cells and all(
                re.match(r"^:?-{2,}:?$", c.replace(" ", "")) for c in cells if c
            ):
                sep_idx.add(i)

        data_rows = [c for i, c in enumerate(parsed) if i not in sep_idx]
        ncols = max((len(c) for c in data_rows), default=0)
        if not ncols:
            return "\n".join(_color(r, _ui.DIM, self.use_color) for r in rows)

        # 列宽取各列最长单元格（按显示宽度算，中文占 2 列）
        from fr_cli.ui.ui import get_display_width
        widths = [0] * ncols
        for cells in data_rows:
            for j, cell in enumerate(cells):
                if j < ncols:
                    widths[j] = max(widths[j], get_display_width(cell))

        out = []
        for i, cells in enumerate(parsed):
            if i in sep_idx:
                out.append(_color("─" * (sum(widths) + 3 * ncols), _ui.DIM, self.use_color))
                continue
            padded = []
            for j in range(ncols):
                cell = cells[j] if j < len(cells) else ""
                pad = max(0, widths[j] - get_display_width(cell))
                padded.append(cell + " " * pad)
            out.append(
                _color("│ ", _ui.DIM, self.use_color)
                + _color(" │ ", _ui.DIM, self.use_color).join(padded)
                + _color(" │", _ui.DIM, self.use_color)
            )
        return "\n".join(out)

    # ------------------------------------------------------------------
    # 行内格式
    # ------------------------------------------------------------------

    def _render_inline(self, text: str) -> str:
        """行内格式渲染(粗体 / 斜体 / 代码 / 链接)"""
        result = text
        # 行内代码
        result = re.sub(
            r"`([^`]+)`",
            lambda m: _color(f"`{m.group(1)}`", _ui.YELLOW, self.use_color),
            result,
        )
        # 粗体
        result = re.sub(
            r"\*\*([^*]+)\*\*",
            lambda m: _color(m.group(1), _ui.BOLD, self.use_color),
            result,
        )
        # 斜体
        result = re.sub(
            r"(?<!\*)\*([^*]+)\*(?!\*)",
            lambda m: _color(m.group(1), _ui.DIM, self.use_color),
            result,
        )
        # 链接 [text](url)
        result = re.sub(
            r"\[([^\]]+)\]\(([^)]+)\)",
            lambda m: _color(m.group(1), _ui.CYAN, self.use_color) +
                     (_color(f" ({m.group(2)})", _ui.DIM, self.use_color) if self.use_color else f" ({m.group(2)})"),
            result,
        )
        return result
