"""
pipeline 阶段 5:收尾处理

从 fr_cli.core.chat.pipeline 拆出(原文件 488 行)。
_post_process: 统计行 / 功能推荐 / 产物检测 / 记忆更新 / 自动存档,
返回统计信息供底部状态栏使用。
"""
from __future__ import annotations

from pathlib import Path

from fr_cli.core.headless import is_headless
from fr_cli.ui.ui import CYAN, DIM, GREEN, RESET, print_styled
from fr_cli.core.sysmon import get_sys_stats
from fr_cli.memory.context import build_context_summary, extract_recent_turns, save_context
from fr_cli.memory.session import create_session, update_session


def _post_process(state, updated_messages, txt, usage, response_time, u, lang):
    """统计 / 推荐 / 产物检测 / 记忆 / 存档"""
    # v2.8.7+:无头模式(bot / 服务端进程)不向 stdout 输出
    headless = is_headless(state)

    # 回复正文回传 —— bot / 服务端场景从这里取答案。
    # 放在最前面,保证即使后续步骤抛异常,调用方也能拿到内容。
    try:
        state.last_reply = txt or ""
    except Exception:
        pass

    # 显示模型信息和 token 使用情况
    if not headless:
        sys_stats = get_sys_stats(lang)
        stats_extra = f" | {sys_stats}" if sys_stats else ""
        if usage:
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", 0)
            # 口径与状态栏一致（core/usage.py::format_token_usage 是唯一真相源）
            from fr_cli.core.usage import format_token_usage
            usage_text = format_token_usage(input_tokens, output_tokens,
                                            total_tokens, state.limit,
                                            with_pct=bool(state.limit))
            print_styled(
                f"{DIM}{response_time:.1f}s · {state.display_model} · "
                f"{usage_text}{stats_extra}{RESET}"
            )
        else:
            print_styled(f"{DIM}{response_time:.1f}s · {state.display_model}{stats_extra}{RESET}")

    # 智能功能推荐
    if not headless:
        from fr_cli.core.recommender import recommend_features
        recommendations = recommend_features(u)
        if recommendations:
            print_styled(f"{GREEN}推荐功能:{RESET}")
            for i, rec in enumerate(recommendations[:5], 1):
                print_styled(f"  {DIM}[{i}]{RESET} {CYAN}{rec['cmd']}{RESET} - {rec['desc']}")

    # 智能插件进化检测 & Agent 分身检测(统一入口)
    # 无头模式下由 detect_*_artifact 内部自行短路(会 input() 索要名称)
    from fr_cli.agent.artifact_detector import detect_plugin_artifact, detect_agent_artifact
    detect_plugin_artifact(txt, lang, state)
    detect_agent_artifact(txt, lang, state)

    # 更新记忆上下文
    recent = extract_recent_turns(updated_messages, 5)
    state.context_summary = build_context_summary(recent, lang)
    # v2.8.7+:无头模式不写全局 config.json 的 context.summaries ——
    # 那个命名空间以全局 session_name 为 key,多用户 bot 场景必然串台。
    # bot 由自己的 SessionStore 按 session_key 隔离管理。
    if not headless:
        save_context(state.sn, state.context_summary)

    # 更新主消息列表
    state.set_messages(updated_messages)

    # 自动按日期存档会话
    if not state.auto_session_path:
        path = create_session(state.get_messages(), session_id=getattr(state, "session_id", None))
        if path:
            state.auto_session_path = path
            # v3.0+:广播 session.created(此前该事件只有 metrics 钩子、没有生产派发点)
            try:
                from fr_cli.core.events import V2Events, dispatch_event
                dispatch_event(
                    V2Events.SESSION_CREATED,
                    data={"path": path},
                    source="chat",
                )
            except Exception:
                pass
            if not headless:
                print_styled(f"{DIM}{Path(path).name}{RESET}")
    else:
        update_session(state.auto_session_path, state.get_messages())
        # v3.0+:广播 session.saved(此前该事件只有 metrics 钩子、没有生产派发点)
        try:
            from fr_cli.core.events import V2Events, dispatch_event
            dispatch_event(
                V2Events.SESSION_SAVED,
                data={"path": state.auto_session_path},
                source="chat",
            )
        except Exception:
            pass

    # 返回统计信息供底部状态栏使用
    return {
        "response_time": response_time,
        "input_tokens": usage.get("prompt_tokens", 0) if usage else 0,
        "output_tokens": usage.get("completion_tokens", 0) if usage else 0,
        "total_tokens": usage.get("total_tokens", 0) if usage else 0,
    }
