"""
韩立字符画 —— 《凡人修仙传》主角形象

启动画面展示用。素材由官方动画版韩立参考图经
半块字符(▀) + 真彩色转换生成,存放于 assets/:

- hanli_bust.ansi  半身像(默认启动, 56 列)
- hanli_bust.txt   半身像纯文本降级版(NO_COLOR / 非 Unicode 终端)
- hanli_full.ansi  全身细节版(-logo, 72 列)
- hanli_full.txt   全身纯文本降级版

转换管线: alpha 抠图 → LANCZOS 缩放 → 自动对比度 + USM 锐化
→ 每字符格采样上下两像素颜色(fg/bg) → 半块字符输出,
垂直分辨率翻倍;暗部颜色提亮保护,保证黑发/墨袍在深色终端可见。
"""
import shutil
import sys
from pathlib import Path

_ASSETS_DIR = Path(__file__).parent.parent / "assets"

# 每种素材的字符宽度(列),用于居中计算
ART_WIDTH = {"bust": 56, "full": 72}


def _no_color() -> bool:
    """是否禁用彩色输出"""
    import os
    if os.environ.get("FORCE_COLOR") or os.environ.get("CLICOLOR_FORCE"):
        return False
    if os.environ.get("NO_COLOR"):
        return True
    try:
        from fr_cli.ui.ui import _NO_COLOR
        if _NO_COLOR:
            return True
    except Exception:
        pass
    return not sys.stdout.isatty()


def _load_art(variant: str, color: bool) -> str:
    """读取字符画素材;color=True 读 .ansi,否则读 .txt 纯文本版"""
    ext = "ansi" if color else "txt"
    path = _ASSETS_DIR / f"hanli_{variant}.{ext}"
    return path.read_text(encoding="utf-8")


def art_row_count(variant: str = "bust", color: bool = False) -> int:
    """字符画行数(用于终端高度判断)

    :param variant: "bust" | "full"
    :param color: True 按 .ansi 彩色版计算 —— 半块字符垂直分辨率翻倍,
                  行数 ≈ 2 × 纯文本版;高度保护必须按实际要打印的版本算
    """
    try:
        return len(_load_art(variant, color).rstrip("\n").split("\n"))
    except OSError:
        return 0


def _center(text: str, width: int) -> str:
    """按终端宽度居中(每行前加空格;彩色行以 ANSI 开头也安全)"""
    try:
        term_w = shutil.get_terminal_size().columns
    except Exception:
        term_w = 80
    pad = " " * max((term_w - width) // 2, 0)
    return "\n".join(pad + line if line.strip() else line for line in text.split("\n"))


def print_hanli(variant: str = "bust", min_free_rows: int = 12) -> bool:
    """打印韩立字符画(居中)。

    Args:
        variant: "bust"(半身像, 默认) | "full"(全身细节)
        min_free_rows: 预留行数(给信息框/提示), 终端不够高时跳过
    Returns:
        True=已打印, False=跳过(终端过小 / 素材缺失 / 非交互)
    """
    if variant not in ART_WIDTH:
        variant = "bust"

    color = not _no_color()
    try:
        art = _load_art(variant, color)
    except OSError:
        return False

    # 终端高度保护: 小终端不刷屏, 留 min_free_rows 给后续内容
    # 必须按实际要打印的版本(彩色/纯文本)计算行数 —— 彩色版是纯文本版的约 2 倍
    try:
        term_h = shutil.get_terminal_size().lines
        if term_h and term_h < art_row_count(variant, color=color) + min_free_rows:
            return False
    except Exception:
        pass

    print()
    print(_center(art.rstrip("\n"), ART_WIDTH[variant]))
    return True
