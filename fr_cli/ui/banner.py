"""
启动画面 —— Kimi Code CLI 风格（v2.4.0+）

- 单个圆角框包住整个标题区
- 框内：项目名 + 欢迎语 + 关键信息（目录/Session/Model/Tokens/Mode）
- 框外：── input ──... 分隔线（让用户视觉上看到"输入区"开始）
- TUI prompt_toolkit 接管 input 区
"""
import shutil
import re
from fr_cli.ui.ui import (
    CYAN, YELLOW, BOLD, DIM, RESET, GRAY,
    get_display_width, _NO_COLOR,
)
from fr_cli import __version__


def _get_box_width() -> int:
    """自适应框宽：终端宽 - 4（左右各 2 边距），最大 100"""
    try:
        cols = shutil.get_terminal_size().columns
    except Exception:
        cols = 100
    return min(max(cols - 4, 60), 100)


def _strip_ansi(s: str) -> str:
    """去除 ANSI 颜色码，返回纯文本（用于计算显示宽度）"""
    return re.sub(r'\033\[[0-9;]*m', '', s)


def _box_line(content: str, width: int) -> str:
    """拼一行框内容：│ + 左缩进 2 + 内容（按 ANSI 透明宽度） + 右填充 + │
    返回格式：'│  {content}  {padding}│'，宽度严格 = width（含两边 │）
    """
    inner = width - 2  # 去掉左右 │ 的空间
    # 计算 ANSI 透明的宽度
    plain = _strip_ansi(content)
    cw = get_display_width(plain)
    # 固定 2 字符左缩进
    left_pad = "  "
    if cw >= inner - 2:
        # 内容太长，截断（简化：直接展示，不严格截断避免 ANSI 撕裂）
        right_pad = ""
    else:
        right_pad = " " * (inner - 2 - cw)
    return f"{GRAY}│{RESET}{left_pad}{content}{right_pad}{GRAY}│{RESET}"


def print_banner(model_name: str, limit: int, allowed_dirs: list, session_name: str,
                 lang: str, provider: str, version: str, token_used: int = 0, mode: str = "direct",
                 is_mock: bool = False):
    """单框启动画面（Kimi Code 风格）"""
    # 检查是否禁用启动画面
    try:
        from fr_cli.conf.config import load_config
        cfg = load_config()
        if cfg.get("banner_enabled") is False:
            return
    except Exception:
        pass

    width = _get_box_width()
    horizontal = "─" * (width - 2)

    print()
    print(f"{GRAY}╭{horizontal}╮{RESET}")

    # 准备内容
    if allowed_dirs:
        ds = allowed_dirs[0]
    else:
        ds = "(未设置)"

    if session_name:
        sess_display = session_name
    else:
        sess_display = "全新"

    if is_mock:
        model_display = f"🧪 mock/{model_name}"
    else:
        model_display = f"{provider}/{model_name}"

    # 每行独立（_box_line 自动加 2 字符缩进）
    title_line = f"{CYAN}{BOLD}凡人打字机{RESET}  {DIM}v{version}{RESET}  {DIM}· 修仙者的编码引擎{RESET}"
    help_line = f"{DIM}输入{RESET} {CYAN}/{RESET}{DIM} 看命令，{RESET}{CYAN}@{RESET}{DIM} 调 Agent，{RESET}{CYAN}!{RESET}{DIM} 跑 shell，{RESET}{CYAN}?{RESET}{DIM} 看帮助{RESET}"
    info_line = (
        f"{DIM}Directory:{RESET} {ds}"
    )
    sess_line = (
        f"{DIM}Session:  {RESET} {sess_display}"
    )
    model_line = (
        f"{DIM}Model:    {RESET} {model_display}"
        f"  {DIM}·{RESET} {YELLOW}{limit}{RESET}{DIM} tokens{RESET}"
        f"  {DIM}·{RESET} {YELLOW}{mode}{RESET}{DIM} mode{RESET}"
    )
    footer_line = f"{DIM}✨ fr-cli {__version__} — 9 提供商 · Agent 分身 · RAG · MasterAgent 自我进化{RESET}"

    all_lines = [
        title_line,
        help_line,
        "",  # 空行
        info_line,
        sess_line,
        model_line,
        "",  # 空行
        footer_line,
    ]

    for line in all_lines:
        print(_box_line(line, width))

    # 底部框线
    print(f"{GRAY}╰{horizontal}╯{RESET}")
    print()


def print_input_separator(width: int = None):
    """在 TUI 输入区上方打印分隔线：── input ──────...

    直接使用当前终端窗口宽度，不受 banner 框宽上限限制，
    确保分隔线始终铺满终端整行。
    """
    if width is None:
        try:
            width = shutil.get_terminal_size().columns
        except Exception:
            width = 100
    label = "── input "
    # 总长度 = 终端宽度
    dash_count = max(width - len(label), 10)
    sep_color = "" if _NO_COLOR else "\033[90m"
    print(f"{sep_color}{label}{'─' * dash_count}{RESET}")
