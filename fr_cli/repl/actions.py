"""
TUI 快捷键动作处理（e/r/u）

- e = edit：编辑上一条 AI 回答，重新生成
- r = retry：重试上一条 user prompt
- u = undo：撤销最后 N 轮对话
"""
from fr_cli.ui.ui import CYAN, RESET, YELLOW, DIM


def action_edit_last_ai(state, prompt):
    """e = 编辑上一条 AI 回答，然后重新生成"""
    if not state.messages or len(state.messages) < 2:
        print(f"{YELLOW}⚠️ 没有可编辑的 AI 回答{RESET}")
        return
    last_ai_idx = None
    for i in range(len(state.messages) - 1, 0, -1):
        if state.messages[i].get("role") == "assistant":
            last_ai_idx = i
            break
    if last_ai_idx is None:
        print(f"{YELLOW}⚠️ 没找到 AI 回答{RESET}")
        return
    state.messages = state.messages[:last_ai_idx]
    print(f"{CYAN}✏️  准备重新生成最后一条 AI 回答...{RESET}")
    last_user = None
    for m in reversed(state.messages):
        if m.get("role") == "user":
            last_user = m.get("content", "")
            break
    if last_user:
        prompt.set_busy(True)
        try:
            from fr_cli.core.chat import handle_ai_chat
            stats = handle_ai_chat(state, last_user)
            if stats:
                prompt.update_last_stats(**stats)
        finally:
            prompt.set_busy(False)


def action_retry_last_user(state, prompt):
    """r = 重试上一条 user prompt（不改 user 内容，再调一次）"""
    if not state.messages:
        print(f"{YELLOW}⚠️ 没有可重试的对话{RESET}")
        return
    last_user = None
    for m in reversed(state.messages):
        if m.get("role") == "user":
            last_user = m.get("content", "")
            break
    if not last_user:
        print(f"{YELLOW}⚠️ 没找到 user prompt{RESET}")
        return
    for i in range(len(state.messages) - 1, -1, -1):
        if state.messages[i].get("role") == "user" and state.messages[i].get("content") == last_user:
            state.messages = state.messages[:i + 1]
            break
    print(f"{CYAN}🔄 重试上一条 user prompt...{RESET}")
    prompt.set_busy(True)
    try:
        from fr_cli.core.chat import handle_ai_chat
        stats = handle_ai_chat(state, last_user)
        if stats:
            prompt.update_last_stats(**stats)
    finally:
        prompt.set_busy(False)


def action_undo_last(state, n: int = 1):
    """u = 撤销最后 N 轮对话（每轮 = 1 user + 1 assistant）"""
    if not state.messages:
        print(f"{YELLOW}⚠️ 没有可撤销的对话{RESET}")
        return
    if n < 1:
        n = 1
    end = len(state.messages)
    for i in range(len(state.messages) - 1, -1, -1):
        if state.messages[i].get("role") == "system":
            end = i + 1
            break
    if end >= len(state.messages):
        print(f"{YELLOW}⚠️ 已经没有对话了{RESET}")
        return
    deleted = 0
    cursor = len(state.messages) - 1
    while cursor >= end and deleted < n:
        if state.messages[cursor].get("role") == "assistant":
            state.messages.pop(cursor)
            cursor -= 1
            if cursor >= end and state.messages[cursor].get("role") == "user":
                state.messages.pop(cursor)
                cursor -= 1
                deleted += 1
            else:
                break
        else:
            cursor -= 1
    if deleted:
        suffix = f"{DIM}（再按 u 继续撤销）{RESET}" if deleted == n else ""
        print(f"{CYAN}↩️  撤销了 {deleted} 轮对话{suffix}")
    else:
        print(f"{DIM}已撤销{RESET}")
