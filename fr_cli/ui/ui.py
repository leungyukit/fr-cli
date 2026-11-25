"""
终端UI、颜色定义与动画引擎
"""
import sys, platform, os
from typing import Dict, Tuple, Union

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

# 当前生效的颜色码 —— 活引用的唯一真值来源。
# 运行时被 set_no_color() 改写，所有持有 _LiveColor 的模块立刻跟着变。
_COLOR_STATE: Dict[str, str] = {}


# ── 颜色常量的"活引用" ──────────────────────────────────────────────
#
# 历史漏洞：模块用 ``from fr_cli.ui.ui import RED`` 取色时拿到的是**字符串
# 副本** —— import 期就把转义序列烤进了局部变量。于是运行时
# ``set_no_color(True)`` 只能改 ui.ui 自己的全局，那 90+ 个副本纹丝不动：
# "全局关色"对它们无效，非 TTY / prompt_toolkit.patch_stdout 代理期仍会
# 漏出 ?[91m 这类乱码。（markdown_stream.py 早先用 PEP 562 代理修过自己，
# 但那是逐个模块打补丁 —— 这里从根上解决。）
#
# 现在常量本身是 str 子类实例：它记住自己的**名字**（或名字元组），取值时
# 实时回读 _COLOR_STATE。于是：
#   * ``from fr_cli.ui.ui import RED`` 拿到的仍是活引用；
#   * ``CYAN + BOLD`` 返回的也是活引用（组合在**取用时**才求值，
#     所以 import 期就写下的 ``COLOR_HUNK = CYAN + BOLD`` 同样是活的）；
#   * ``f"{RED}"`` / ``format(RED)`` / ``print(RED)`` 都拿到当前值。
#
# 底层字符串值保留导入期的颜色码，仅用于让 isinstance(x, str) 成立、
# 以及在少数不需要实时性的场景（如当字典键）下不炸。
_ColorSpec = Union[str, Tuple[str, ...]]


def _resolve_color(spec: _ColorSpec) -> str:
    """解析颜色规格 → 当前生效的转义序列（实时）"""
    if isinstance(spec, str):
        return _COLOR_STATE.get(spec, "")
    return "".join(_COLOR_STATE.get(name, "") for name in spec)


def _join_spec(a: _ColorSpec, b: _ColorSpec) -> Tuple[str, ...]:
    """拼接两个颜色规格，保持"活"的组合"""
    a_t = (a,) if isinstance(a, str) else tuple(a)
    b_t = (b,) if isinstance(b, str) else tuple(b)
    return a_t + b_t


class _LiveColor(str):
    """颜色常量的活引用（见上方说明）"""

    def __new__(cls, spec: _ColorSpec, fallback: str = ""):
        obj = super().__new__(cls, fallback)
        obj._spec = spec
        return obj

    def __str__(self) -> str:
        return _resolve_color(self._spec)

    def __format__(self, format_spec: str) -> str:
        return format(str(self), format_spec)

    def __bool__(self) -> bool:
        # 真值也跟随实时状态：关色后 RED 等价于空串，
        # 于是 `if not color:` 这类判断（markdown_stream._color）在
        # 关色时会正确地跳过着色。
        return bool(_resolve_color(self._spec))

    def __eq__(self, other) -> bool:
        if isinstance(other, str):
            return _resolve_color(self._spec) == str(other)
        return NotImplemented

    def __hash__(self) -> int:
        return hash(_resolve_color(self._spec))

    def __add__(self, other):
        if isinstance(other, _LiveColor):
            return _LiveColor(_join_spec(self._spec, other._spec))
        return str(self) + other

    def __radd__(self, other):
        return other + str(self)


# ── NO_COLOR 支持 ──
# 单一判定源: 所有 UI 模块(ui / output / markdown_stream / stream)都走这里,
# 避免历史上"ui.py 只认 NO_COLOR、output.py 还认 FR_CLI_NO_COLOR"的两套漂移
# (曾导致 FR_CLI_NO_COLOR=1 关不掉 markdown 流式输出的颜色)。
#
# 优先级(从高到低):
#   0. stdout 被 prompt_toolkit.patch_stdout 代理 → 强制关色(绝对否决)
#   1. FORCE_COLOR / CLICOLOR_FORCE  → 强制开色(忽略 TTY 检测)
#   2. NO_COLOR / FR_CLI_NO_COLOR    → 强制关色(标准约定)
#   3. stdin 与 stdout 均为 TTY      → 开色; 否则关色(管道/重定向/日志)
#
# 第 0 级为什么压过 FORCE_COLOR: REPL 的 AI 对话跑在 prompt_toolkit 的
# patch_stdout 上下文里(queue.py), StdoutProxy 非 raw 模式走
# Vt100_Output.write(), 该方法会把文本里的 ESC 字节替换成字面 '?'
# (prompt_toolkit/output/vt100.py: "Removes vt100 escape codes -- used
# for safely writing text")。此时打任何色都只会得到 ?[96m 乱码, 且代理下
# isatty() 仍为 True, 只有这项检测能拦住。真实冒烟踩过两次: markdown 流式
# 输出满屏 ?[96m?[1m•?[0m; master_loop 的"自动会话已创建"提示 ?[2m...?[0m。
def stdout_is_prompt_toolkit_proxy() -> bool:
    """当前 stdout 是否被 prompt_toolkit.patch_stdout 代理(StdoutProxy 实例)"""
    return "prompt_toolkit" in type(sys.stdout).__module__


def color_enabled() -> bool:
    """当前环境是否应输出 ANSI 颜色(每次调用实时判定, 不用 import 时快照)"""
    if stdout_is_prompt_toolkit_proxy():
        return False
    if os.environ.get("FORCE_COLOR") or os.environ.get("CLICOLOR_FORCE"):
        return True
    if os.environ.get("NO_COLOR") or os.environ.get("FR_CLI_NO_COLOR"):
        return False
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except Exception:
        return False


_NO_COLOR = not color_enabled()


def set_no_color(value: bool = True) -> None:
    """
    运行时启用/禁用 ANSI 颜色(显式覆盖, 优先于环境判定)。
    当 prompt_toolkit.patch_stdout 接管 stdout 时,原始 ANSI 转义序列会被当作
    纯文本显示为 ?[92m 等乱码；调用本函数可全局关闭颜色输出。

    实现要点：改的是 _COLOR_STATE（活引用的真值来源），**不是**重新绑定
    模块全局 —— 因为 ``from fr_cli.ui.ui import RED`` 这种按值导入早就把
    旧字符串复制走了，重新绑定模块全局对它们无效。
    """
    global _NO_COLOR
    _NO_COLOR = bool(value)
    for name, code in _COLOR_CODES.items():
        _COLOR_STATE[name] = "" if _NO_COLOR else code


def no_color() -> bool:
    """当前是否处于显式关色状态（实时判定，不用 import 时快照）"""
    return _NO_COLOR


# ── 对外导出的颜色常量（活引用）────────────────────────────────────
#
# 每个常量都是一个 _LiveColor 实例：按值导入到别的模块后仍然是"活的"。
# 组合写法（CYAN + BOLD）返回的也是活引用。
RESET = _LiveColor("RESET", _COLOR_CODES['RESET'])
BOLD = _LiveColor("BOLD", _COLOR_CODES['BOLD'])
DIM = _LiveColor("DIM", _COLOR_CODES['DIM'])
RED = _LiveColor("RED", _COLOR_CODES['RED'])
GREEN = _LiveColor("GREEN", _COLOR_CODES['GREEN'])
YELLOW = _LiveColor("YELLOW", _COLOR_CODES['YELLOW'])
BLUE = _LiveColor("BLUE", _COLOR_CODES['BLUE'])
MAGENTA = _LiveColor("MAGENTA", _COLOR_CODES['MAGENTA'])
CYAN = _LiveColor("CYAN", _COLOR_CODES['CYAN'])
WHITE = _LiveColor("WHITE", _COLOR_CODES['WHITE'])
MAROON = _LiveColor("MAROON", _COLOR_CODES['MAROON'])
GRAY = _LiveColor("GRAY", _COLOR_CODES['GRAY'])
CODE_BG = _LiveColor("CODE_BG", _COLOR_CODES['CODE_BG'])
CODE_FG = _LiveColor("CODE_FG", _COLOR_CODES['CODE_FG'])


def reset_color() -> None:
    """根据当前环境变量重新初始化颜色状态"""
    set_no_color(not color_enabled())


def use_color() -> bool:
    """当前是否应输出 ANSI 颜色: 显式关色(set_no_color(True)) 或环境判定为假则为 False。

    print_styled 与彩色 input() 提示共用的单一判定(每次调用实时判定,
    不用 import 时快照)。判定组合与 stream._markdown_use_color 保持一致。
    """
    return not _NO_COLOR and color_enabled()


def print_styled(text: str) -> None:
    """打印一行(可能带 ANSI 颜色的)文本; 颜色不可用时剥掉转义序列输出纯文本。

    颜色不可用 = 显式 set_no_color(True) 或 color_enabled() 为假, 覆盖场景:
    - 非 TTY(管道/重定向/日志)
    - stdout 被 prompt_toolkit.patch_stdout 代理(REPL 的 AI 对话期):
      StdoutProxy 非 raw 模式走 Vt100_Output.write(), 会把文本里的 ESC
      字节替换成字面 '?', 裸打色只会让用户看到 ?[2m 乱码。
    - 运行时显式关色(set_no_color(True), cron 等内部路径在用)

    与 "if color_enabled(): print(彩色版) else: print(纯文版)" 等价, 但
    消息只有一份(按需剥序列, 不抄两遍), 两分支不会漂移。chat 路径的带色
    print 统一走这里, 替代各文件 from ui import 颜色常量后裸 print 的写法
    (那种写法在代理期必泄漏 ?[ 乱码)。判定组合与 stream._markdown_use_color
    保持一致: 显式关色 与 环境判定 缺一不可。
    """
    if use_color():
        print(text)
    else:
        from fr_cli.ui.ansi import strip_ansi  # 延迟导入: ui 被最早导入, 不拖累启动
        print(strip_ansi(text))


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


def center_display(text: str, width: int) -> str:
    """按显示宽度居中并补齐到 width 列。

    str.center 按代码点补齐,emoji/中文占 2 列会导致行宽超出、框线错位。
    """
    w = get_display_width(text)
    if w >= width:
        return text
    lpad = (width - w) // 2
    return " " * lpad + text + " " * (width - w - lpad)

def print_bye():
    """打印退出动画"""
    print(f"\n{DIM}欢 迎 下 次 继 续 修 仙{RESET}\n")
