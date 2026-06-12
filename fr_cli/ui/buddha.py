"""
ASCII 佛像 —— fr-cli 修仙项目的启动画面

设计:坐佛像(禅定印)
- 100% ASCII + Unicode 几何符号,**完全不用 CJK 字符**,
  避免终端列宽计算偏移(中文字符显示 2 列宽但 Python len() 算 1)。
- 100% 兼容所有终端(无需 24-bit 颜色、无需图像协议)
- 居中显示,自适应终端宽度
- 共 25 行,纯字符构图
"""
from __future__ import annotations

import re
import shutil
import sys

# ===================== 颜色常量 =====================

RESET = "\x1b[0m"

# ANSI 256 色
CYAN = "\x1b[38;5;117m"          # 青(光晕外圈)
GOLD = "\x1b[38;5;178m"          # 金色(实心光晕/法身)
GOLD_BRIGHT = "\x1b[38;5;220m"   # 亮金(轮廓高光)
GOLD_DEEP = "\x1b[38;5;130m"     # 深金(轮廓阴影/底座)
ORANGE = "\x1b[38;5;209m"        # 橙(法衣)
MAGENTA = "\x1b[38;5;141m"       # 紫(白毫/眼)
YELLOW = "\x1b[38;5;227m"        # 黄(手印/光点)
RED = "\x1b[38;5;160m"           # 暗红(底部文字)

# 全局 NO_COLOR / prompt_toolkit 兼容：关闭颜色
from fr_cli.ui.ui import _NO_COLOR
if _NO_COLOR:
    RESET = CYAN = GOLD = GOLD_BRIGHT = GOLD_DEEP = ORANGE = MAGENTA = YELLOW = RED = ""


# ===================== 佛像 ASCII =====================
# 严格规范:
#   - 每行字符数 = 65(光晕外圈最宽),从中心向左右对称
#   - 不用 CJK 字符(佛/头/禅等),全部用 box-drawing + 几何符号
#   - 每个字符位置 = 1 个终端列宽
#
# 结构(从上到下):
#   1) 顶部光晕:  . * 放射
#   2) 头光圆:    o 虚线 + ░▒▓ 渐变实心
#   3) 佛头:      ┌─┐ │  框 + . 白毫 + o o 眼 + ~ 嘴
#   4) 脖颈:      缩小为 1 行
#   5) 法衣:      ╱╲╳ 梯形
#   6) 双手:      /_/\_\ 禅定印 + + 拇指
#   7) 莲台:      5 个 [▓▓] 莲瓣
#   8) 底部文字:  fr-cli v2.3.3 | Fanren Typewriter(纯 ASCII)
#   9) 基座:      ===== 暗红粗线

BUDDHA_ART = r"""


                              .          .
                       .          *          .
                  .          *     o     *          .
             .          *     o   ░▒▓██▓▒░   o     *          .
                  *     o   ░▒▓████████▓▒░   o     *
                       o  ░▒▓██┌──────────┐██▓▒░  o
                         ░▒▓██│     .     │██▓▒░
                         ░▒▓██│   o   o   │██▓▒░
                         ░▒▓██│    ~~     │██▓▒░
                         ░▒▓██└──────────┘██▓▒░
                      ░▒▓██████████████████████▓▒░
                   ░▒▓███╱  ╲   ╱     ╲   ╱  ╲███▓▒░
                 ░▒▓███╱    ╲ ╱   ╳   ╳ ╲ ╱    ╲███▓▒░
               ░▒▓███╱      ╳     ___     ╳      ╲███▓▒░
              ░▒▓███╱      ╱     ╱ + ╲     ╲      ╲███▓▒░
            ░▒▓███╱       ╱     ╱     ╲     ╲       ╲███▓▒░
          ░▒▓████████████████████████████████████████████▓▒░
        ░▒▓███  ┌──┐    ┌──┐    ┌──┐    ┌──┐    ┌──┐  ███▓▒░
       ░▒▓███   │▓▓│    │▓▓│    │▓▓│    │▓▓│    │▓▓│   ███▓▒░
       ░▒▓███   │▓▓│    │▓▓│    │▓▓│    │▓▓│    │▓▓│   ███▓▒░
       ░▒▓███   └──┘    └──┘    └──┘    └──┘    └──┘   ███▓▒░
         ░▒▓███████████████████████████████████████████▓▒░
            ░▒▓███▓▒░                              ░▒▓███▓▒░
                ░▒▓██▓▒░                      ░▒▓██▓▒░
                    ░▒▓██▓▒░            ░▒▓██▓▒░
"""


# ===================== 颜色化 =====================

def _colorize_line(line: str) -> str:
    """给一行字符加颜色(单字符 → 单颜色,无 CJK 字符)。"""
    out = []
    for ch in line:
        if ch == "." or ch == "*":
            out.append(f"{CYAN}{ch}{RESET}")
        elif ch in "░▒":
            out.append(f"{CYAN}{ch}{RESET}")
        elif ch == "▓":
            out.append(f"{GOLD}{ch}{RESET}")
        elif ch == "█":
            out.append(f"{GOLD_DEEP}{ch}{RESET}")
        elif ch in "┌┐└┘├┤┬┴┼─━│╪":
            out.append(f"{GOLD_BRIGHT}{ch}{RESET}")
        elif ch in "╭╮╰╯":
            out.append(f"{GOLD_BRIGHT}{ch}{RESET}")
        elif ch == "o":
            out.append(f"{MAGENTA}{ch}{RESET}")
        elif ch == "+":
            out.append(f"{MAGENTA}{ch}{RESET}")
        elif ch == "~":
            out.append(f"{MAGENTA}{ch}{RESET}")
        elif ch in "▽△▲▼":
            out.append(f"{YELLOW}{ch}{RESET}")
        elif ch in "╱╲╳":
            out.append(f"{ORANGE}{ch}{RESET}")
        elif ch == "_":
            out.append(f"{GOLD_BRIGHT}{ch}{RESET}")
        elif ch == " ":
            out.append(" ")
        else:
            # 兜底:ASCII 字符用 ORANGE
            out.append(f"{ORANGE}{ch}{RESET}")
    return "".join(out)


# ===================== 底部文字 =====================

def _make_footer(version: str = "2.3.3") -> str:
    """底部文字:纯 ASCII 软件名 + 版本号,居中。"""
    text = f"fr-cli v{version}  |  Fanren Typewriter  |  凡 人 打 字 机"
    return text


# ===================== 对外接口 =====================

def render_buddha(version: str = "2.3.3") -> str:
    """返回彩色化后的完整佛像文本(无 CJK 字符)。"""
    raw = BUDDHA_ART
    lines = [l for l in raw.split("\n")]
    # 颜色化
    out_lines = [_colorize_line(l) for l in lines]
    # 底部接一行版本号(用 ASCII,避免 CJK 偏移)
    out_lines.append("")  # 空行
    footer = _make_footer(version=version)
    out_lines.append(f"{GOLD_BRIGHT}{footer}{RESET}")
    return "\n".join(out_lines)


def print_buddha(version: str = "2.3.3") -> int:
    """打印佛像,返回有效行数(供调试)。"""
    try:
        term_w = shutil.get_terminal_size().columns
    except Exception:
        term_w = 80

    art = render_buddha(version=version)
    lines = art.split("\n")

    # 佛像宽 ~70 字符,居中
    buddha_w = 70
    left_pad = " " * max((term_w - buddha_w) // 2, 0)

    out = sys.stdout
    printed = 0
    for line in lines:
        # 用可见宽度(去 ANSI 码)判断是否空行
        plain = re.sub(r"\x1b\[[0-9;]*m", "", line)
        if plain.strip():
            out.write(left_pad + line + "\n")
            printed += 1
        else:
            out.write("\n")
    out.flush()
    return printed
