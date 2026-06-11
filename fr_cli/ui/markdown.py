"""
轻量级 Markdown 到 ANSI 终端渲染器

支持：
- 标题 (# ## ###)
- 粗体 (**text**)
- 斜体 (*text*)
- 行内代码 (`code`)
- 无序列表 (- * +)
- 有序列表 (1. 2.)
- 引用 (> )
- 分隔线 (--- *** ___)
- 链接 ([text](url))

限制：
- 不处理嵌套结构
- 不处理表格
- 代码块内部不做渲染（stream.py 已处理代码块高亮）
"""
import re
from fr_cli.ui.ui import RESET, BOLD, DIM, CYAN, GREEN, YELLOW, MAGENTA, BLUE, _NO_COLOR


def _render_inline(text: str) -> str:
    """渲染行内格式：粗体、斜体、代码、链接"""
    # 粗体 **text**
    text = re.sub(r'\*\*(.+?)\*\*', f'{BOLD}\\1{RESET}', text)
    # 斜体 *text*（排除 ** 的情况）
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', f'{DIM}\\1{RESET}', text)
    # 行内代码 `code`
    text = re.sub(r'`([^`]+?)`', f'{GREEN}\\1{RESET}', text)
    # 链接 [text](url) → 只显示 text
    text = re.sub(r'\[([^\]]+?)\]\([^)]+?\)', f'{CYAN}\\1{RESET}', text)
    return text


def _is_prompt_toolkit_stdout() -> bool:
    """检测当前 stdout 是否被 prompt_toolkit.patch_stdout 接管"""
    import sys
    return "prompt_toolkit" in type(sys.stdout).__module__


def render_markdown(text: str) -> str:
    """将 Markdown 文本渲染为带 ANSI 颜色的终端输出

    Args:
        text: Markdown 格式文本
    Returns:
        带 ANSI 颜色的文本（NO_COLOR / patch_stdout 环境下返回原文）
    """
    if _NO_COLOR or not text or _is_prompt_toolkit_stdout():
        return text

    lines = text.split('\n')
    result = []
    in_code = False

    for line in lines:
        # 代码块边界检测
        stripped = line.strip()
        if stripped.startswith('```'):
            in_code = not in_code
            result.append(line)
            continue

        if in_code:
            result.append(line)
            continue

        original = line

        # 分隔线（至少 3 个 - * _）
        if re.match(r'^\s*([-*_])\s*\1\s*\1+\s*$', stripped):
            width = 50
            result.append(f"{DIM}{'─' * width}{RESET}")
            continue

        # 标题
        heading_match = re.match(r'^(#{1,6})\s+(.*)$', line)
        if heading_match:
            level = len(heading_match.group(1))
            content = heading_match.group(2)
            # 标题颜色随级别递减
            colors = [MAGENTA, CYAN, GREEN, YELLOW, BLUE, DIM]
            color = colors[min(level - 1, 5)]
            result.append(f"{color}{BOLD}{content}{RESET}")
            continue

        # 引用
        if line.startswith('> '):
            result.append(f"{DIM}│ {line[2:]}{RESET}")
            continue

        # 无序列表
        list_match = re.match(r'^(\s*)[-*+]\s+(.*)$', line)
        if list_match:
            indent = list_match.group(1)
            content = list_match.group(2)
            result.append(f"{indent}{CYAN}•{RESET} {_render_inline(content)}")
            continue

        # 有序列表
        ordered_match = re.match(r'^(\s*)(\d+)\.\s+(.*)$', line)
        if ordered_match:
            indent = ordered_match.group(1)
            num = ordered_match.group(2)
            content = ordered_match.group(3)
            result.append(f"{indent}{CYAN}{num}.{RESET} {_render_inline(content)}")
            continue

        # 普通行：渲染行内格式
        result.append(_render_inline(original))

    return '\n'.join(result)
