"""
启动引导
- 加载系统提示词
- 历史会话后台加载
- 上下文懒加载
- 同步 MANUAL.md 到工作空间
- 打印启动画面
"""
import os
import sys
import shutil
import threading
from pathlib import Path

# 先触发路径迁移（必须在导入任何用 paths 的模块之前）
from fr_cli.conf.paths import migrate as _paths_migrate
_paths_migrate()

from fr_cli.conf.config import init_config, ConfigError
from fr_cli.lang.i18n import T
from fr_cli import __version__
from fr_cli.memory.history import load_sess
from fr_cli.memory.context import load_context
from fr_cli.core.core import AppState


def sync_manual_to_workspace(vfs):
    """将项目根目录的 MANUAL.md 复制到工作空间，使 AI 可通过 read_file 读取"""
    if not vfs.cwd:
        return
    try:
        manual_src = Path(__file__).parent.parent / "MANUAL.md"
        if not manual_src.exists():
            return
        manual_dst = Path(vfs.cwd) / "MANUAL.md"
        if not manual_dst.exists():
            shutil.copy2(manual_src, manual_dst)
    except Exception:
        pass


def _ensure_manual_exists():
    """如果项目根目录没有 MANUAL.md，则创建一个默认版本"""
    manual_path = Path(__file__).parent.parent / "MANUAL.md"
    if manual_path.exists():
        return
    default_content = """# 凡人打字机 (fr-cli) 使用手册

## 快速开始

- 输入 `/help` 查看所有命令
- 输入 `/tutorial` 开始交互式教程
- 直接输入问题即可与 AI 对话

## 常用命令

- `/model <模型名>` — 切换大模型
- `/key <api_key>` — 设置 API Key
- `/dir <目录>` — 设置工作目录
- `/save <名称>` — 保存当前会话
- `/load <名称>` — 加载历史会话

## 内置 Agent

- `@local <需求>` — 本地系统操作
- `@remote <别名> <需求>` — 远程 SSH 操作
- `@db <别名> <查询>` — 数据库查询
- `@RAG <问题>` — 知识库问答
"""
    try:
        manual_path.write_text(default_content, encoding="utf-8")
    except Exception:
        pass


def load_system_prompt(state, lang: str):
    """初始化或恢复 system prompt"""
    sp = T("sys_prompt", lang)
    if not state.messages:
        state.messages = [{"role": "system", "content": sp}]
    return sp


def start_history_loader(state, sp: str):
    """后台线程加载历史会话"""
    if not state.sn:
        return
    def _load_history():
        try:
            ok, m, _ = load_sess(0, sp)
            if ok and m and (not state.messages or state.messages[0].get("role") != "system" or len(state.messages) == 1):
                state.messages = m
        except Exception:
            pass
    threading.Thread(target=_load_history, daemon=True, name="history-loader").start()


def start_context_loader(state):
    """后台线程加载上下文摘要"""
    if not state.sn:
        return
    state._context_pending = True

    def _load_context():
        try:
            state.context_summary = load_context(state.sn)
            state._context_pending = False
        except Exception:
            state._context_pending = False
    threading.Thread(target=_load_context, daemon=True, name="context-loader").start()


def print_simple_banner(state, version: str):
    """圆角框线启动画面 —— Kimi Code CLI 风格"""
    from fr_cli.ui.ui import CYAN, BOLD, DIM, RESET, MAROON, get_display_width

    inner_width = 110  # 内容区宽度（不含左右框线）

    def _pad(text: str, width: int) -> str:
        w = get_display_width(text)
        return text + " " * max(width - w, 0)

    # 信息准备
    model = f"{state.display_provider}/{state.display_model}" if state.cfg.get("provider") else "未配置"
    allowed_dirs = state.cfg.get("allowed_dirs", [])
    directory = allowed_dirs[0] if allowed_dirs else "未配置"
    cwd = getattr(state.vfs, "cwd", None) or directory
    session_id = getattr(state, "session_id", None) or "全新"

    # 框线
    top = "╭" + "─" * inner_width + "╮"
    bot = "╰" + "─" * inner_width + "╯"
    empty = "│" + " " * inner_width + "│"

    # Logo + 标题
    title = f"   {MAROON}▐▀▀▀▀▀▀▌{RESET}  {CYAN}{BOLD}凡人打字机{RESET}  {DIM}fr-cli v{version}{RESET}"
    subtitle = f"   {MAROON}▐██████▌{RESET}  {DIM}Send /help for help information{RESET}"

    # 信息行
    dir_line = f"  Directory: {cwd}"
    sess_line = f"  Session:   {session_id}"
    model_line = f"  Model:     {model}"

    print()
    print(top)
    print(empty)
    print("│" + _pad(title, inner_width) + "│")
    print("│" + _pad(subtitle, inner_width) + "│")
    print(empty)
    print("│" + _pad(dir_line, inner_width) + "│")
    print("│" + _pad(sess_line, inner_width) + "│")
    print("│" + _pad(model_line, inner_width) + "│")
    print(empty)
    print(bot)
    print()


def print_startup_banner(state, cfg, show_logo: bool = False):
    """打印启动画面

    Args:
        show_logo: True 时显示佛像 ASCII art（-logo 参数），
                   False 时显示简洁线条框（默认）
    """
    from fr_cli import __version__

    if show_logo:
        # -logo 参数：显示佛像 ASCII art
        try:
            from fr_cli.ui.buddha import print_buddha
            n_lines = print_buddha(version=__version__)
            print()
            return
        except Exception as e:
            # 出错则降级到简洁 banner
            try:
                from fr_cli.conf.paths import FR_CLI_DIR
                log_path = FR_CLI_DIR / "splash.log"
                with open(log_path, "a", encoding="utf-8") as f:
                    import traceback
                    f.write(f"[buddha skipped] {type(e).__name__}: {e}\n")
            except Exception:
                pass
            print_simple_banner(state, __version__)
            return

    # 默认：简洁线条框
    print_simple_banner(state, __version__)


def bootstrap(show_logo: bool = False):
    """启动引导主入口：返回 (cfg, state)"""
    try:
        cfg = init_config()
    except ConfigError:
        from fr_cli.ui.ui import RED, RESET
        print(f"{RED}配置初始化失败，退出。{RESET}")
        return None, None
    state = AppState(cfg)
    sync_manual_to_workspace(state.vfs)
    sp = load_system_prompt(state, cfg.get("lang", "zh"))
    start_history_loader(state, sp)
    start_context_loader(state)
    print_startup_banner(state, cfg, show_logo=show_logo)
    return cfg, state