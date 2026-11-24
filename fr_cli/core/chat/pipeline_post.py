"""
pipeline 阶段 5:收尾处理

从 fr_cli.core.chat.pipeline 拆出(原文件 488 行)。
_post_process: 统计行 / 功能推荐 / 产物检测 / 记忆更新 / 自动存档,
返回统计信息供底部状态栏使用。
"""
from __future__ import annotations

import sys
from pathlib import Path

from fr_cli.lang.i18n import T
from fr_cli.ui.ui import CYAN, DIM, GREEN, RESET, print_styled
from fr_cli.core.sysmon import get_sys_stats
from fr_cli.memory.context import build_context_summary, extract_recent_turns, save_context
from fr_cli.memory.session import create_session, update_session


def _post_process(state, updated_messages, txt, usage, response_time, u, lang):
    """统计 / 推荐 / 产物检测 / 记忆 / 存档"""
    # 显示模型信息和 token 使用情况
    sys_stats = get_sys_stats(lang)
    stats_extra = f" | {sys_stats}" if sys_stats else ""
    if usage:
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)
        usage_pct = f" ({total_tokens / state.limit * 100:.0f}%)" if state.limit else ""
        print_styled(
            f"{DIM}{response_time:.1f}s · {state.display_model} · "
            f"↓{input_tokens} ↑{output_tokens} Σ{total_tokens}{usage_pct}"
            f"{stats_extra}{RESET}"
        )
    else:
        print_styled(f"{DIM}{response_time:.1f}s · {state.display_model}{stats_extra}{RESET}")

    # 智能功能推荐
    from fr_cli.core.recommender import recommend_features
    recommendations = recommend_features(u)
    if recommendations:
        print_styled(f"{GREEN}推荐功能:{RESET}")
        for i, rec in enumerate(recommendations[:5], 1):
            print_styled(f"  {DIM}[{i}]{RESET} {CYAN}{rec['cmd']}{RESET} - {rec['desc']}")

    # 智能插件进化检测 & Agent 分身检测(统一入口)
    from fr_cli.agent.artifact_detector import detect_plugin_artifact, detect_agent_artifact
    detect_plugin_artifact(txt, lang, state)
    detect_agent_artifact(txt, lang, state)

    # 更新记忆上下文
    recent = extract_recent_turns(updated_messages, 5)
    state.context_summary = build_context_summary(recent, lang)
    save_context(state.sn, state.context_summary)

    # 更新主消息列表
    state.messages = updated_messages

    # 自动按日期存档会话
    if not state.auto_session_path:
        path = create_session(state.messages, session_id=getattr(state, "session_id", None))
        if path:
            state.auto_session_path = path
            print_styled(f"{DIM}{Path(path).name}{RESET}")
    else:
        update_session(state.auto_session_path, state.messages)

    # 返回统计信息供底部状态栏使用
    return {
        "response_time": response_time,
        "input_tokens": usage.get("prompt_tokens", 0) if usage else 0,
        "output_tokens": usage.get("completion_tokens", 0) if usage else 0,
        "total_tokens": usage.get("total_tokens", 0) if usage else 0,
    }
