"""
Diff 可视化 —— 彩色 diff 渲染

相比普通 unified diff:
- 颜色:绿(+)/红(-)/黄(上下文)/青(行号)/灰(hunk header)
- 折叠:默认 3 行上下文,只显示修改块附近
- 双栏并排 / 单栏 unified 切换
- 行号对齐(旧文件 / 新文件)
- 统计:增加 / 删除 / 修改行数

格式:
```
diff --git a/file.py b/file.py
@@ -10,7 +10,8 @@
- 10  |    old line 1           |     10 | new line 1           +
- 11  | -  old line 2           |     11 | + new line 2         +
- 12  |    old line 3           |     12 | new line 3           +
- 13  | -                       |     13 | + new line 4 added   +
```
"""
import re
from typing import List, Tuple, Dict, Any, Optional

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


# 颜色规则
COLOR_ADD = GREEN
COLOR_DEL = RED
COLOR_CONTEXT = DIM
COLOR_HUNK = CYAN + BOLD
COLOR_LINE_NUM = DIM
COLOR_META = YELLOW


def _color(text: str, color: str, use_color: bool = True) -> str:
    if not use_color:
        return text
    return f"{color}{text}{RESET}"


def _parse_unified_diff(diff_text: str) -> List[Dict[str, Any]]:
    """解析 unified diff 为 hunk 列表

    Returns:
        [{"old_start", "new_start", "lines": [(kind, content), ...]}, ...]
    """
    hunks = []
    current_hunk = None

    for line in diff_text.splitlines():
        if line.startswith("@@"):
            # @@ -10,7 +10,8 @@
            m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            if m:
                if current_hunk is not None:
                    hunks.append(current_hunk)
                current_hunk = {
                    "old_start": int(m.group(1)),
                    "old_count": int(m.group(2) or 1),
                    "new_start": int(m.group(3)),
                    "new_count": int(m.group(4) or 1),
                    "lines": [],
                }
        elif current_hunk is not None:
            if line.startswith("+"):
                current_hunk["lines"].append(("add", line[1:]))
            elif line.startswith("-"):
                current_hunk["lines"].append(("del", line[1:]))
            elif line.startswith(" "):
                current_hunk["lines"].append(("ctx", line[1:]))
            # else: "\ No newline at end of file" etc — skip

    if current_hunk is not None:
        hunks.append(current_hunk)
    return hunks


def _line_num_width(hunks: List[Dict[str, Any]]) -> int:
    """计算行号显示宽度"""
    max_n = 1
    for h in hunks:
        max_n = max(max_n, h["old_start"] + h["old_count"], h["new_start"] + h["new_count"])
    return max(4, len(str(max_n)))


def render_diff_unified(diff_text: str, use_color: bool = True,
                        context: int = 3) -> str:
    """渲染 unified diff(单栏彩色)

    Args:
        diff_text: 原始 unified diff 文本
        use_color: 是否使用 ANSI 颜色
        context: 显示上下几行
    """
    if not diff_text.strip():
        return _color("(no diff)", DIM, use_color)

    hunks = _parse_unified_diff(diff_text)
    if not hunks:
        return _color(diff_text, WHITE, use_color)

    width = _line_num_width(hunks)
    lines = []

    for h in hunks:
        header = f"@@ -{h['old_start']},{h['old_count']} +{h['new_start']},{h['new_count']} @@"
        lines.append(_color(header, COLOR_HUNK, use_color))

        old_lineno = h["old_start"]
        new_lineno = h["new_start"]
        hunk_lines = h["lines"]

        # 应用上下文过滤(默认上下文 = 3,显示修改块附近)
        if context >= 0:
            indices_to_show = set()
            for i, (kind, _) in enumerate(hunk_lines):
                if kind != "ctx":
                    for j in range(max(0, i - context), min(len(hunk_lines), i + context + 1)):
                        indices_to_show.add(j)
            hunk_lines_filtered = [
                (kind, content, i in indices_to_show)
                for i, (kind, content) in enumerate(hunk_lines)
            ]
        else:
            hunk_lines_filtered = [(k, c, True) for k, c in hunk_lines]

        # 渲染
        last_shown = -1
        for idx, (kind, content, show) in enumerate(hunk_lines_filtered):
            if not show:
                # 跳过 ctx 行(也要更新行号)
                if kind == "ctx":
                    old_lineno += 1
                    new_lineno += 1
                elif kind == "del":
                    old_lineno += 1
                elif kind == "add":
                    new_lineno += 1
                continue

            # 检测折叠(连续 3+ 个隐藏行)
            if last_shown >= 0 and idx - last_shown > 1:
                lines.append(_color(f"  ... ({idx - last_shown - 1} 行折叠) ...", DIM, use_color))
            last_shown = idx

            old_str = f"{old_lineno:>{width}}" if kind in ("ctx", "del") else " " * width
            new_str = f"{new_lineno:>{width}}" if kind in ("ctx", "add") else " " * width
            line_num = _color(f"{old_str} │ {new_str} │ ", COLOR_LINE_NUM, use_color)

            if kind == "add":
                lines.append(line_num + _color(f"+ {content}", COLOR_ADD, use_color))
                new_lineno += 1
            elif kind == "del":
                lines.append(line_num + _color(f"- {content}", COLOR_DEL, use_color))
                old_lineno += 1
            else:  # ctx
                lines.append(line_num + _color(f"  {content}", COLOR_CONTEXT, use_color))
                old_lineno += 1
                new_lineno += 1
        lines.append("")

    return "\n".join(lines).rstrip()


def render_diff_side_by_side(diff_text: str, use_color: bool = True,
                              context: int = 3) -> str:
    """双栏并排 diff(左侧旧,右侧新)

    Args:
        diff_text: 原始 unified diff
        use_color: ANSI 颜色
        context: 上下文行数
    """
    if not diff_text.strip():
        return _color("(no diff)", DIM, use_color)

    hunks = _parse_unified_diff(diff_text)
    if not hunks:
        return _color(diff_text, WHITE, use_color)

    width = _line_num_width(hunks)
    # 终端宽度估算:每栏约 (width + content + 8)
    left_w = 70  # 每栏 70 字符
    lines = []

    for h in hunks:
        header = f"@@ -{h['old_start']},{h['old_count']} +{h['new_start']},{h['new_count']} @@"
        lines.append(_color(header, COLOR_HUNK, use_color))
        # 表头
        sep = "═" * (left_w * 2 + 5)
        lines.append(_color(sep, DIM, use_color))
        lines.append(
            _color(f"{'OLD':>{width}} │ ", COLOR_LINE_NUM, use_color) +
            _color("content".ljust(left_w - width - 3), DIM, use_color) +
            _color(" │ ", DIM, use_color) +
            _color(f"{'NEW':>{width}} │ ", COLOR_LINE_NUM, use_color) +
            _color("content".ljust(left_w - width - 3), DIM, use_color)
        )
        lines.append(_color(sep, DIM, use_color))

        old_lineno = h["old_start"]
        new_lineno = h["new_start"]

        # 把 (kind, content) 序列按配对规则变成行
        paired_lines = _pair_diff_lines(h["lines"])

        for pair_kind, old_line, new_line in paired_lines:
            old_str = f"{old_lineno:>{width}}" if old_line is not None else " " * width
            new_str = f"{new_lineno:>{width}}" if new_line is not None else " " * width

            old_content = (old_line or "")[:left_w - width - 3].ljust(left_w - width - 3)
            new_content = (new_line or "")[:left_w - width - 3].ljust(left_w - width - 3)

            old_color = COLOR_DEL if pair_kind == "del" else (COLOR_CONTEXT if pair_kind == "ctx" else DIM)
            new_color = COLOR_ADD if pair_kind == "add" else (COLOR_CONTEXT if pair_kind == "ctx" else DIM)

            old_full = _color(f"{old_str} │ ", COLOR_LINE_NUM, use_color) + _color(old_content, old_color, use_color)
            new_full = _color(f"{new_str} │ ", COLOR_LINE_NUM, use_color) + _color(new_content, new_color, use_color)

            lines.append(f"{old_full} {_color('│', DIM, use_color)} {new_full}")

            if old_line is not None:
                old_lineno += 1
            if new_line is not None:
                new_lineno += 1
        lines.append("")

    return "\n".join(lines).rstrip()


def _pair_diff_lines(lines: List[Tuple[str, str]]) -> List[Tuple[str, Optional[str], Optional[str]]]:
    """把 (kind, content) 序列变成配对(用于双栏显示)

    Returns:
        [(kind, old_line, new_line), ...]
        kind = "ctx" / "add" / "del" / "mod"
    """
    result = []
    i = 0
    while i < len(lines):
        kind, content = lines[i]
        if kind == "ctx":
            result.append(("ctx", content, content))
            i += 1
        elif kind == "add":
            # 连续的 add 视为一组
            adds = []
            while i < len(lines) and lines[i][0] == "add":
                adds.append(lines[i][1])
                i += 1
            for a in adds:
                result.append(("add", None, a))
        elif kind == "del":
            # 连续的 del 视为一组
            dels = []
            while i < len(lines) and lines[i][0] == "del":
                dels.append(lines[i][1])
                i += 1
            # 如果紧接着是 add = 修改(mod),配对
            adds = []
            if i < len(lines) and lines[i][0] == "add":
                while i < len(lines) and lines[i][0] == "add":
                    adds.append(lines[i][1])
                    i += 1
            # 配对:数量多的为主
            n = max(len(dels), len(adds))
            for j in range(n):
                old_line = dels[j] if j < len(dels) else None
                new_line = adds[j] if j < len(adds) else None
                if old_line is not None and new_line is not None:
                    result.append(("mod", old_line, new_line))
                elif old_line is not None:
                    result.append(("del", old_line, None))
                else:
                    result.append(("add", None, new_line))
        else:
            i += 1
    return result


def diff_stats(diff_text: str) -> Dict[str, int]:
    """统计 diff 增删改行数

    Returns:
        {"added": int, "deleted": int, "hunks": int, "files": int}
    """
    stats = {"added": 0, "deleted": 0, "hunks": 0, "files": 0}
    if not diff_text:
        return stats

    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            stats["files"] += 1
        elif line.startswith("@@"):
            stats["hunks"] += 1
        elif line.startswith("+") and not line.startswith("+++"):
            stats["added"] += 1
        elif line.startswith("-") and not line.startswith("---"):
            stats["deleted"] += 1
    return stats


def render_diff_stats(diff_text: str, lang: str = "zh") -> str:
    """格式化 diff 统计"""
    stats = diff_stats(diff_text)
    if lang == "zh":
        return (
            f"📊 Diff 统计: "
            f"+{stats['added']} -{stats['deleted']} "
            f"修改块 {stats['hunks']} "
            f"文件 {stats['files']}"
        )
    return (
        f"📊 Diff stats: "
        f"+{stats['added']} -{stats['deleted']} "
        f"hunks {stats['hunks']} "
        f"files {stats['files']}"
    )
