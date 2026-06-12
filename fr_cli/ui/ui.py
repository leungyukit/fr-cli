"""
终端UI、颜色定义与动画引擎
"""
import sys, time, platform, os

# 原始 ANSI 颜色代码表（供 set_no_color 恢复使用）
_COLOR_CODES = {
    'RESET': '\033[0m',
    'BOLD': '\033[1m',
    'DIM': '\033[2m',
    'RED': '\033[91m',
    'GREEN': '\033[92m',
    'YELLOW': '\033[93m',
    'BLUE': '\033[94m',
    'MAGENTA': '\033[95m',
    'CYAN': '\033[96m',
    'WHITE': '\033[97m',
    'MAROON': '\033[38;5;88m',  # 酒红色 / Burgundy
    'GRAY': '\033[90m',           # 亮黑 / 灰色
    'CODE_BG': '\033[48;5;236m',
    'CODE_FG': '\033[38;5;255m',
}

# ── NO_COLOR 支持 ──
# 若环境变量 NO_COLOR 设置（非空），则禁用所有 ANSI 颜色
# 同时检测非 TTY 环境（管道/重定向）自动禁用
_NO_COLOR = bool(os.environ.get("NO_COLOR") or not sys.stdout.isatty())


def set_no_color(value: bool = True) -> None:
    """
    运行时启用/禁用 ANSI 颜色。
    当 prompt_toolkit.patch_stdout 接管 stdout 时，原始 ANSI 转义序列会被当作
    纯文本显示为 ?[92m 等乱码；调用本函数可全局关闭颜色输出。
    """
    global _NO_COLOR, RESET, BOLD, DIM, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE, MAROON, GRAY, CODE_BG, CODE_FG
    _NO_COLOR = bool(value)
    if _NO_COLOR:
        RESET = BOLD = DIM = ""
        RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = ""
        MAROON = GRAY = ""
        CODE_BG = CODE_FG = ""
    else:
        RESET = _COLOR_CODES['RESET']
        BOLD = _COLOR_CODES['BOLD']
        DIM = _COLOR_CODES['DIM']
        RED = _COLOR_CODES['RED']
        GREEN = _COLOR_CODES['GREEN']
        YELLOW = _COLOR_CODES['YELLOW']
        BLUE = _COLOR_CODES['BLUE']
        MAGENTA = _COLOR_CODES['MAGENTA']
        CYAN = _COLOR_CODES['CYAN']
        WHITE = _COLOR_CODES['WHITE']
        MAROON = _COLOR_CODES['MAROON']
        GRAY = _COLOR_CODES['GRAY']
        CODE_BG = _COLOR_CODES['CODE_BG']
        CODE_FG = _COLOR_CODES['CODE_FG']


def reset_color() -> None:
    """根据当前环境变量重新初始化颜色状态"""
    set_no_color(bool(os.environ.get("NO_COLOR") or not sys.stdout.isatty()))


# 根据初始化时的环境状态设置颜色常量
set_no_color(_NO_COLOR)

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
    """判断字符是否为全角字符（用于显示宽度计算）"""
    import unicodedata
    return unicodedata.east_asian_width(c) in ('F', 'W')

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

def print_bye():
    """打印退出动画"""
    print(f"\n{DIM}欢 迎 下 次 继 续 修 仙{RESET}\n")
