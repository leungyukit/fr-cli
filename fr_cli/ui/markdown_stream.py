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

try:
    from fr_cli.ui.ui import (
        RESET, BOLD, DIM, RED, GREEN, YELLOW, BLUE, CYAN, MAGENTA, WHITE,
    )
    # 如果 ui.py 把颜色禁了(非 TTY/NO_COLOR),用硬编码值
    if not RESET:
        RESET = "\033[0m"
        BOLD = "\033[1m"
        DIM = "\033[2m"
        RED = "\033[31m"
        GREEN = "\033[32m"
        YELLOW = "\033[33m"
        BLUE = "\033[34m"
        MAGENTA = "\033[35m"
        CYAN = "\033[36m"
        WHITE = "\033[37m"
except ImportError:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"


def _color(text: str, color: str, use_color: bool = True) -> str:
    if not use_color:
        return text
    return f"{color}{text}{RESET}"


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
            return _color(sep, DIM, self.use_color) + "\n" + _color(f"  📦 {lang_label}", CYAN + BOLD, self.use_color)

        # 标题
        m = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            colors = [
                CYAN + BOLD, BLUE + BOLD, GREEN + BOLD, YELLOW + BOLD,
                MAGENTA + BOLD, RED + BOLD,
            ]
            color = colors[min(level - 1, len(colors) - 1)]
            self.block_count += 1
            prefix = "#" * level
            return _color(f"\n{prefix} {title}", color, self.use_color)

        # 水平线
        if re.match(r"^[-*_]{3,}\s*$", stripped):
            return _color("\n" + "─" * 60 + "\n", DIM, self.use_color)

        # 列表
        list_match = re.match(r"^(\s*)([-*+]|\d+\.)\s+(.+)$", stripped)
        if list_match:
            indent = len(list_match.group(1))
            marker = list_match.group(2)
            content = list_match.group(3)
            bullet = "•" if marker in "-*+" else marker
            indent_str = "  " * (indent // 2)
            return indent_str + _color(bullet, CYAN + BOLD, self.use_color) + " " + self._render_inline(content)

        # 引用
        if stripped.startswith(">"):
            text = stripped[1:].strip()
            return _color("│ ", DIM, self.use_color) + _color(text, DIM, self.use_color)

        # 表格行(简单:检测 |---|)
        if stripped.startswith("|") and stripped.endswith("|") and "-" in stripped and "|" in stripped[1:]:
            self.in_table = True
            return _color(stripped, DIM, self.use_color)

        if self.in_table and stripped.startswith("|"):
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
            rendered = "\n" + _color(sep, DIM, self.use_color)
            self.code_buffer = []
            self.code_lang = ""
            return rendered
        # 代码内容
        self.code_buffer.append(line)
        return _color(line, DIM, self.use_color)

    def _render_inline(self, text: str) -> str:
        """行内格式渲染(粗体 / 斜体 / 代码 / 链接)"""
        result = text
        # 行内代码
        result = re.sub(
            r"`([^`]+)`",
            lambda m: _color(f"`{m.group(1)}`", YELLOW, self.use_color),
            result,
        )
        # 粗体
        result = re.sub(
            r"\*\*([^*]+)\*\*",
            lambda m: _color(m.group(1), BOLD, self.use_color),
            result,
        )
        # 斜体
        result = re.sub(
            r"(?<!\*)\*([^*]+)\*(?!\*)",
            lambda m: _color(m.group(1), DIM, self.use_color),
            result,
        )
        # 链接 [text](url)
        result = re.sub(
            r"\[([^\]]+)\]\(([^)]+)\)",
            lambda m: _color(m.group(1), CYAN, self.use_color) +
                     (_color(f" ({m.group(2)})", DIM, self.use_color) if self.use_color else f" ({m.group(2)})"),
            result,
        )
        return result

    def _render_table_row(self, line: str) -> str:
        """渲染表格行"""
        cells = [c.strip() for c in line.strip("|").split("|")]
        rendered_cells = []
        for cell in cells:
            rendered_cells.append(_color(cell, WHITE, self.use_color))
        return _color("│ ", DIM, self.use_color) + _color(" │ ", DIM, self.use_color).join(rendered_cells)

    def flush(self) -> str:
        """flush 剩余 buffer"""
        if not self.buffer.strip():
            return ""
        if self.state == "IN_CODE":
            # 代码块未结束
            self.state = "NORMAL"
            self.code_buffer.append(self.buffer)
            return "\n" + _color(self.buffer, DIM, self.use_color)
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


def is_streaming_md_enabled() -> bool:
    """是否启用 streaming MD(可通过环境变量关闭)"""
    import os
    return os.environ.get("FR_CLI_STREAMING_MD", "1") != "0"
