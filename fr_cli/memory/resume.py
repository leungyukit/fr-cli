"""
会话恢复 —— 启动时提示用户继续上次会话

策略:
- 检查 ~/.fr_cli/sessions/auto/ 下的最新会话
- 如果最后一条消息距离现在 < 24 小时,提示用户是否继续
- 用户选择:
  - y / 回车:加载最后 N 条消息到 messages
  - n:跳过,开始新会话
  - s:完整列出最近会话选一条
"""
import time
from typing import Optional, List, Dict, Any

from fr_cli.conf.paths import SESSIONS_AUTO_DIR


RESUME_WINDOW_SECONDS = 24 * 3600  # 24h 内提示
DEFAULT_LOAD_TURNS = 5  # 默认加载最近 5 轮(10 条)


def find_latest_auto_session() -> Optional[Dict[str, Any]]:
    """找最新的自动存档会话

    Returns:
        None 或 {path, filename, updated_at, msg_count}
    """
    if not SESSIONS_AUTO_DIR.exists():
        return None

    files = sorted(SESSIONS_AUTO_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None

    latest = files[0]
    try:
        mtime = latest.stat().st_mtime
        from fr_cli.core.store import JsonStore
        data = JsonStore(str(latest), default=dict).read()
        msgs = data.get("messages", [])
        return {
            "path": str(latest),
            "filename": latest.name,
            "updated_at": mtime,
            "msg_count": len(msgs),
            "messages": msgs,
        }
    except Exception:
        return None


def is_resumable(session_info: Dict[str, Any]) -> bool:
    """判断会话是否在恢复时间窗内"""
    if not session_info:
        return False
    now = time.time()
    age = now - session_info.get("updated_at", 0)
    return 0 <= age <= RESUME_WINDOW_SECONDS


def format_resume_prompt(session_info: Dict[str, Any], lang: str = "zh") -> str:
    """格式化恢复提示"""
    age_min = (time.time() - session_info["updated_at"]) / 60
    if age_min < 60:
        age_text = f"{int(age_min)} 分钟前"
    elif age_min < 24 * 60:
        age_text = f"{int(age_min / 60)} 小时前"
    else:
        age_text = f"{int(age_min / 60 / 24)} 天前"

    msg_count = session_info.get("msg_count", 0)
    filename = session_info.get("filename", "?")

    if lang == "zh":
        return (
            f"\n{CYAN_BOLD}📂 检测到上次会话{RESET}\n"
            f"  文件: {filename}\n"
            f"  时间: {age_text}\n"
            f"  消息: {msg_count} 条\n"
            f"\n{GREEN}y{WHITE}/回车{RESET} = 继续上次会话(加载最近 {DEFAULT_LOAD_TURNS} 轮)\n"
            f"{YELLOW}n{WHITE}     = 开始新会话\n"
            f"{BLUE}s{WHITE}     = 选择其他会话"
        )
    return (
        f"\n{CYAN_BOLD}📂 Previous session detected{RESET}\n"
        f"  File: {filename}\n"
        f"  Time: {age_text}\n"
        f"  Messages: {msg_count}\n"
        f"\n{GREEN}y{WHITE}/Enter{RESET} = resume (load last {DEFAULT_LOAD_TURNS} turns)\n"
        f"{YELLOW}n{WHITE}      = new session\n"
        f"{BLUE}s{WHITE}      = select other session"
    )


def load_last_n_turns(messages: List[Dict[str, Any]], n_turns: int = DEFAULT_LOAD_TURNS) -> List[Dict[str, Any]]:
    """从 messages 中加载最近 N 轮(user+assistant 配对)

    排除 system 消息,只取 user/assistant
    """
    # 过滤掉 system,只保留 user/assistant
    conv_msgs = [m for m in messages if m.get("role") in ("user", "assistant")]
    # 每轮 = user + assistant
    turns = len(conv_msgs) // 2
    n = min(n_turns, turns)
    start = -(n * 2)  # 取最后 n*2 条
    return conv_msgs[start:]


def ask_resume_choice(prompt_input=None) -> Optional[str]:
    """询问用户选择

    Args:
        prompt_input: 可注入的 input 函数(测试用)

    Returns:
        'y' / 'n' / 's' / None(EOF)
    """
    prompt_fn = prompt_input or input
    try:
        choice = prompt_fn("  选择 [y/n/s] > ").strip().lower()
        return choice or "y"  # 回车 = y
    except (EOFError, KeyboardInterrupt):
        return None


# ANSI color shortcuts(避免循环 import)
try:
    from fr_cli.ui.ui import RESET, BOLD, GREEN, YELLOW, BLUE, CYAN, WHITE
    CYAN_BOLD = f"{CYAN}{BOLD}"
except ImportError:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    CYAN_BOLD = f"{CYAN}{BOLD}"
