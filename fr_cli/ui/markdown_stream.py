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
from typing import Optional, Dict

from fr_cli.ui import ui as _ui

# 本模块支持的动态颜色常量名(其余名字不走代理, 直接 AttributeError)
_COLOR_NAMES = (
    "RESET", "BOLD", "DIM", "RED", "GREEN", "YELLOW",
    "BLUE", "MAGENTA", "CYAN", "WHITE",
)


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


class StreamingMarkdownRenderer:
    """流式 Markdown 渲染器

    用法:
        renderer = StreamingMarkdownRenderer()
        for chunk in stream:
            rendered = renderer.feed(chunk)
            print(rendered, end="")
        remaining = renderer.flush()
        print(remaining)
    """

    def __init__(self, use_color: bool = True, code_lang_colors: bool = True):
        self.use_color = use_color
        self.buffer = ""          # 未完成的 chunk
        self.state = "NORMAL"     # NORMAL / IN_CODE / IN_HEADING / IN_LIST / IN_TABLE
        self.code_lang = ""       # 当前代码块的语言
        self.code_buffer = []     # 代码块内容
        self.list_indent = 0      # 当前列表缩进
        self.in_table = False     # 是否在表格里
        self.line_count = 0       # 已输出行数
        self.block_count = 0      # block 数

    def feed(self, chunk: str) -> str:
        """喂入新 chunk,返回渲染后的输出"""
        self.buffer += chunk
        output_lines = []

        # 处理完整的行
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            rendered = self._process_line(line)
            if rendered:
                output_lines.append(rendered)
                self.line_count += 1

        # 处理代码块结束标记(可能在 buffer 里没换行)
        if self.state == "IN_CODE":
            # 暂时不输出,等 \n
            pass

        return "\n".join(output_lines) + ("\n" if output_lines else "")

    def _process_line(self, line: str) -> Optional[str]:
        """处理单行"""
        if self.state == "IN_CODE":
            return self._process_code_line(line)

        stripped = line.rstrip()

        # 检测代码块开始
        if stripped.startswith("```"):
            self.state = "IN_CODE"
            self.code_lang = stripped[3:].strip()
            self.code_buffer = []
            self.block_count += 1
            lang_label = self.code_lang or "code"
            sep = "─" * 60
            return _color(sep, _ui.DIM, self.use_color) + "\n" + _color(f"{lang_label}", _ui.CYAN + _ui.BOLD, self.use_color)

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
            return _color("\n" + "─" * 60 + "\n", _ui.DIM, self.use_color)

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

        # 表格行( | ... | ):表头/数据行都按表格渲染,分隔行(---|---)淡化
        if stripped.startswith("|") and stripped.endswith("|") and len(stripped) > 1:
            self.in_table = True
            if re.match(r'^\|?[\s:|-]+\|?$', stripped):
                return _color(stripped, _ui.DIM, self.use_color)
            return self._render_table_row(stripped)

        if self.in_table and not stripped.startswith("|"):
            self.in_table = False

        # 普通段落:渲染行内格式
        if not stripped:
            return ""  # 空行
        return self._render_inline(stripped)

    def _process_code_line(self, line: str) -> Optional[str]:
        """处理代码块内的行"""
        if line.rstrip().startswith("```"):
            # 代码块结束
            self.state = "NORMAL"
            sep = "─" * 60
            rendered = "\n" + _color(sep, _ui.DIM, self.use_color)
            self.code_buffer = []
            self.code_lang = ""
            return rendered
        # 代码内容
        self.code_buffer.append(line)
        return _color(line, _ui.DIM, self.use_color)

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

    def _render_table_row(self, line: str) -> str:
        """渲染表格行"""
        cells = [c.strip() for c in line.strip("|").split("|")]
        rendered_cells = []
        for cell in cells:
            rendered_cells.append(_color(cell, _ui.WHITE, self.use_color))
        return _color("│ ", _ui.DIM, self.use_color) + _color(" │ ", _ui.DIM, self.use_color).join(rendered_cells)

    def flush(self) -> str:
        """flush 剩余 buffer（幂等：重复调用返回空，不会重复输出）"""
        if not self.buffer.strip():
            return ""
        if self.state == "IN_CODE":
            # 代码块未结束
            self.state = "NORMAL"
            self.code_buffer.append(self.buffer)
            out = "\n" + _color(self.buffer, _ui.DIM, self.use_color)
            self.buffer = ""  # 必须清空：否则二次 flush 会经 _process_line 再输出一遍
            return out
        rendered = self._process_line(self.buffer)
        self.buffer = ""
        return rendered or ""

    def stats(self) -> Dict[str, int]:
        """渲染统计"""
        return {
            "lines": self.line_count,
            "blocks": self.block_count,
            "state": self.state,
        }


