"""
VFS 变更展示 —— diff / 预览渲染(纯函数)

从 fr_cli.weapon.fs 拆出(原文件 415 行)。
只负责把文件变更渲染成终端输出,不做任何 IO:
- _is_binary_content: 空字节 / utf-8 解码失败 → 二进制
- _format_diff:       统一格式 diff + 颜色 + 截断
- _preview_content:   新文件 / 追加内容的绿色预览
"""
from __future__ import annotations

import difflib
from pathlib import Path

from fr_cli.lang.i18n import T
from fr_cli.ui.ui import GREEN, RED, CYAN, YELLOW, RESET


def _is_binary_content(data: bytes) -> bool:
    """简单启发式判断内容是否为二进制"""
    if not data:
        return False
    # 若包含空字节，则认为是二进制
    if b"\x00" in data:
        return True
    # 尝试用 utf-8 解码，失败则视为二进制
    try:
        data.decode("utf-8")
        return False
    except UnicodeDecodeError:
        return True


def _format_diff(old_lines: list, new_lines: list, path: str, l: str = "zh", max_lines: int = 80) -> str:
    """生成带颜色的统一格式 diff 文本"""
    # path 可能是绝对路径，使用文件名作为 diff 标签更简洁
    label = Path(path).name
    diff = list(difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{label}",
        tofile=f"b/{label}",
        lineterm="",
    ))
    if not diff:
        return ""

    truncated = False
    if len(diff) > max_lines:
        diff = diff[:max_lines]
        truncated = True

    lines = []
    for line in diff:
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            lines.append(f"{CYAN}{line}{RESET}")
        elif line.startswith("+"):
            lines.append(f"{GREEN}{line}{RESET}")
        elif line.startswith("-"):
            lines.append(f"{RED}{line}{RESET}")
        else:
            lines.append(line)

    if truncated:
        lines.append(f"{YELLOW}{T('diff_truncated', l)}{RESET}")

    return "\n".join(lines)


def _preview_content(content: str, l: str = "zh", max_lines: int = 20) -> str:
    """生成新文件/追加内容的颜色预览"""
    lines = content.splitlines()
    if not lines:
        return ""
    truncated = len(lines) > max_lines
    preview = lines[:max_lines]
    result = "\n".join(f"{GREEN}+{line}{RESET}" for line in preview)
    if truncated:
        result += f"\n{YELLOW}{T('diff_preview_truncated', l, len(preview))}{RESET}"
    return result
