"""
plan_mode.py —— 计划模式主流程

generate_plan → 用户确认 → execute_plan → summarize → 存档

参考:fr_cli/core/plan.py 提供 generate_plan / render_plan / execute_plan /
summarize_execution / save_plan
"""
from __future__ import annotations

import copy
from pathlib import Path

from fr_cli.lang.i18n import T
from fr_cli.ui.ui import DIM, RED, RESET, YELLOW
from fr_cli.memory.context import build_context_summary, extract_recent_turns, save_context
from fr_cli.memory.session import create_session, update_session


def handle_plan_mode(state, u):
    """计划模式主流程:生成计划 → 确认 → 执行 → 汇总"""
    from fr_cli.core.plan import (
        execute_plan,
        generate_plan,
        render_plan,
        save_plan,
        summarize_execution,
    )
    from fr_cli.ui.prompt import create_prompt

    lang = state.lang
    prompt = create_prompt(state)

    # 1. 生成计划
    plan = generate_plan(state, u, lang)
    if not plan:
        print(
            f"{RED}{'❌ 计划生成失败' if lang == 'zh' else '❌ Failed to generate plan'}{RESET}"
        )
        return

    state.active_plan = plan
    state.plan_step_idx = 0

    # 2. 展示计划
    print()
    print(render_plan(plan, lang))
    print()

    # 3. 用户确认
    confirm_msg = "是否执行该计划?" if lang == "zh" else "Execute this plan?"
    if not prompt.confirm(confirm_msg, default=True):
        print(f"{YELLOW}{'🛑 已取消执行' if lang == 'zh' else '🛑 Cancelled'}{RESET}")
        state.active_plan = None
        return

    # 4. 执行计划
    step_results = execute_plan(state, plan, lang)

    # 5. 持久化
    save_plan(state, plan, step_results)

    # 6. 汇总结果
    summary, usage = summarize_execution(state, u, plan, step_results, lang)

    # 7. 更新消息历史与上下文
    plan_text = render_plan(plan, lang)
    result_summary = "\n".join(
        f"步骤 {i}: {'成功' if ok else '失败'}\n{txt[:500]}"
        for i, (ok, txt) in enumerate(step_results, 1)
    )

    updated_messages = copy.deepcopy(state.messages)
    user_prompt = u
    if state.vfs.cwd:
        user_prompt += T("ctx_dir", lang, state.vfs.cwd)

    updated_messages.append({"role": "user", "content": f"[计划模式] {user_prompt}"})
    updated_messages.append(
        {
            "role": "assistant",
            "content": f"**执行计划**\n{plan_text}\n\n**执行结果**\n{result_summary}\n\n**总结**\n{summary}",
        }
    )

    # 更新记忆上下文
    recent = extract_recent_turns(updated_messages, 5)
    state.context_summary = build_context_summary(recent, lang)
    save_context(state.sn, state.context_summary)

    state.messages = updated_messages

    # 自动按日期存档会话
    if not state.auto_session_path:
        path = create_session(state.messages, session_id=getattr(state, "session_id", None))
        if path:
            state.auto_session_path = path
            print(f"{DIM}💾 {Path(path).name}{RESET}")
    else:
        update_session(state.auto_session_path, state.messages)

    # 返回统计信息
    return {
        "response_time": 0.0,
        "input_tokens": usage.get("prompt_tokens", 0) if usage else 0,
        "output_tokens": usage.get("completion_tokens", 0) if usage else 0,
        "total_tokens": usage.get("total_tokens", 0) if usage else 0,
    }
