"""
终端UI、颜色定义与动画引擎
"""
import sys, time, random, platform, os

# ANSI 颜色与样式常量
RESET = '\033[0m'; BOLD = '\033[1m'; DIM = '\033[2m'
RED = '\033[91m'; GREEN = '\033[92m'; YELLOW = '\033[93m'
BLUE = '\033[94m'; MAGENTA = '\033[95m'; CYAN = '\033[96m'; WHITE = '\033[97m'
CODE_BG = '\033[48;5;236m'; CODE_FG = '\033[38;5=255m'

# 动画用的字符集
C_HALF = r"!@#$%^&*()_+-=[]{}|;:<>?/~0123456789ABCDEFabcdef"

def enable_win_ansi():
    """在 Windows 上启用 ANSI 转义序列支持 (VT100)"""
    if platform.system() == "Windows":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        except Exception:
            os.system("")

def safe_clear():
    """安全地清除当前行"""
    sys.stdout.write("\r\033[K")
    sys.stdout.flush()

def is_wide(c):
    """判断字符是否为全角字符（用于动画对齐）"""
    return len(c.encode('utf-8')) > 1

def get_display_width(text):
    """计算字符串的实际显示宽度，考虑ANSI颜色代码和全角字符"""
    import re
    # 移除ANSI颜色代码
    clean_text = re.sub(r'\033\[[0-9;]*m', '', text)
    # 计算显示宽度
    width = 0
    for char in clean_text:
        if is_wide(char):
            width += 2
        else:
            width += 1
    return width

def print_banner(mn, tl, ad, sn, l):
    """打印启动时的小乌龟从左向右爬行动画"""

    # 乌龟身体（6行）
    turtle_body = [
        '      _____',
        "   .-' o o '-.",
        '  /           \\',
        ' |     ___     |',
        '  \\   /   \\   /',
        "   `-._____.-'",
    ]

    # 三帧腿部姿态（每帧2行腿部）
    turtle_frames = [
        turtle_body + ['    /  \\   /  \\ ', '   /    \\ /    \\'],
        turtle_body + ['    |  |   |  |  ', '   /    \\ /    \\'],
        turtle_body + ['    \\  /   \\  / ', '   /    \\ /    \\'],
    ]

    total_lines = len(turtle_frames[0])  # 8 行

    # 爬行路径：从左到右，共 8 个位置，每步 3 格
    positions = [0, 3, 6, 9, 12, 15, 18, 21]

    # 打印初始空白占位
    print("\n" * total_lines)

    # 爬行动画：每个位置循环三帧腿部
    for pos in positions:
        for frame in turtle_frames:
            sys.stdout.write(f"\033[{total_lines}A")
            for line in frame:
                # 整体右移 pos 格，加绿色
                padded = " " * pos + line
                sys.stdout.write(f"\033[K{GREEN}{padded}{RESET}\n")
            sys.stdout.flush()
            time.sleep(0.15)

    # 最终定格：再显示一帧（停顿一下）
    sys.stdout.write(f"\033[{total_lines}A")
    for line in turtle_frames[0]:
        padded = " " * positions[-1] + line
        sys.stdout.write(f"\033[K{GREEN}{padded}{RESET}\n")
    sys.stdout.flush()
    time.sleep(0.3)

    # 显示标题
    if l == "zh":
        print(f"\n{CYAN}{BOLD}  凡 人 打 字 机 {RESET}")
        print(f"  【 修 仙 者 的 编 码 引 擎 】\n")
    else:
        print(f"\n{CYAN}{BOLD}  F A N R E N  C L I  T O O L{RESET}")
        print(f"  [ Advanced Code Engine v1.0 ]\n")

    uf = (l == "zh")
    ds = f"{GREEN}{ad}{RESET}" if ad else f"{RED}{('未开放洞府' if uf else 'No dir')}{RESET}"
    ss = f"{MAGENTA}{sn}{RESET}" if sn else f"{DIM}{'全新轮回' if uf else 'New'}{RESET}"
    i1 = f"  {'🔮 模型' if uf else 'Model'}: {GREEN}{BOLD}{mn}{RESET}  |  {'🛡️ 上限' if uf else 'Limit'}: {YELLOW}{tl}{RESET}"
    i2 = f"  {'📂 洞府' if uf else 'Dir'}: {ds}  |  {'⏳ 轮回' if uf else 'Sess'}: {ss}"
    bl = max(get_display_width(i1), get_display_width(i2)) + 4
    print(f"{MAGENTA}┌{'─'*bl}┐{RESET}\n{MAGENTA}│{RESET}{i1}{' '*(bl-get_display_width(i1)-2)}{MAGENTA}│{RESET}\n{MAGENTA}│{RESET}{i2}{' '*(bl-get_display_width(i2)-2)}{MAGENTA}│{RESET}\n{MAGENTA}└{'─'*bl}┘{RESET}\n")

def print_bye():
    """打印退出动画"""
    print(f"\n{DIM}欢 迎 下 次 继 续 修 仙{RESET}\n")
