"""
pipeline 阶段 3+4:插件前置拦截 + 流式调用 + 多源汇总

从 fr_cli.core.chat.pipeline 拆出(原文件 488 行)。
- _maybe_run_local_plugin: /plugin_name 开头直接执行本地插件(无 LLM 调用)
- _stream_and_respond:     流式调用 + 事件广播 + 命令自动执行([*] 风格展示)
- _multi_source_blend:     初步回答 + 工具结果 → 第二轮汇总调用
"""
from __future__ import annotations

import sys

from fr_cli.lang.i18n import T
from fr_cli.ui.ui import BOLD, CYAN, DIM, GREEN, RED, RESET
from fr_cli.core.stream import stream_cnt
from fr_cli.core.intent import has_save_intent

from fr_cli.core.chat.helpers import (
    auto_compress_messages,
    record_usage,
    fold_result,
)


def _maybe_run_local_plugin(state, prompt, lang, updated_messages):
    """如果 prompt 以 /plugin_name 开头,直接执行本地插件(无 LLM 调用)"""
    for pk in state.plugins:
        if prompt.startswith(f"/{pk} "):
            p_args = prompt[len(f"/{pk} "):].strip()
            if state.security.check("sec_exec", f"/{pk}"):
                from fr_cli.addon.plugin import exec_plugin
                exec_plugin(pk, state.plugins[pk], p_args, lang)
            updated_messages.append({"role": "assistant", "content": f"[Executed /{pk}]"})
            state.messages = updated_messages
            return True
    return False


def _stream_and_respond(state, updated_messages, u, lang):
    """流式调用 AI,自动执行命令,必要时进入第二轮多源汇总"""
    # v3.0+:广播 llm.requested
    try:
        from fr_cli.core.events import V2Events, dispatch_event
        dispatch_event(
            V2Events.LLM_REQUESTED,
            data={
                "provider": getattr(state, "provider", None),
                "model": state.model_name,
                "messages_count": len(updated_messages),
                "prompt_preview": u[:200],
            },
            source="chat",
        )
    except Exception:
        pass

    try:
        txt, usage, response_time, _ = stream_cnt(
            state.client, state.model_name, updated_messages, lang,
            max_tokens=state.limit,
        )
    except Exception as e:
        try:
            from fr_cli.core.events import V2Events, dispatch_event
            dispatch_event(
                V2Events.LLM_FAILED,
                data={"model": state.model_name, "error": str(e)},
                source="chat",
            )
        except Exception:
            pass
        from fr_cli.core.errors import friendly_print
        print(f"{RED}{friendly_print(e)}{RESET}")
        return None, None, 0.0

    if usage:
        record_usage(state, usage)
    updated_messages.append({"role": "assistant", "content": txt})

    # v3.0+:广播 llm.responded
    try:
        from fr_cli.core.events import V2Events, dispatch_event
        dispatch_event(
            V2Events.LLM_RESPONDED,
            data={
                "model": state.model_name,
                "usage": usage,
                "response_time": response_time,
                "output_len": len(txt) if txt else 0,
            },
            source="chat",
        )
    except Exception:
        pass

    # 自动执行 AI 响应中的命令
    try:
        clean_txt, cmd_results = state.executor.process_ai_commands(txt, updated_messages)
    except Exception as e:
        from fr_cli.core.errors import friendly_print
        print(f"{RED}{friendly_print(e)}{RESET}")
        clean_txt, cmd_results = txt, []

    # AI 响应已在 stream_cnt 中实时渲染（流式 Markdown），此处不再整篇重渲染，
    # 仅展示命令自动执行的结果（[*] 头 + dim 体，Claude Code 风格），避免重复输出
    if cmd_results:
        print()
        for result in cmd_results:
            folded = fold_result(result)
            head, _, body = folded.partition("\n")
            print(f"{CYAN}[*]{RESET} {BOLD}{head.strip()}{RESET}")
            body = body.strip("\n")
            if body.strip():
                print(f"{DIM}{body}{RESET}")

        # 多源汇总第二轮
        usage, response_time = _multi_source_blend(
            state, updated_messages, clean_txt, cmd_results, u, lang, usage, response_time,
        )

    return txt, usage, response_time


def _multi_source_blend(
    state, updated_messages, clean_txt, cmd_results, u, lang, usage, response_time,
):
    """将大模型初步回答与所有工具结果结构化合并,触发第二轮 AI 调用"""
    sources = []
    if clean_txt.strip():
        sources.append(f"【来源一:大模型初步回答】\n{clean_txt.strip()}")
    for idx, result in enumerate(cmd_results, start=2):
        sources.append(f"【来源{idx}:工具执行结果】\n{result}")

    blend_system_content = "=== 多源信息汇总 ===\n\n"
    blend_system_content += "\n\n---\n\n".join(sources)
    blend_system_content += (
        "\n\n=== 整理要求 ===\n"
        "请基于以上所有信息来源,整理成一份完整、准确、结构清晰的最终答案。\n"
        "- 不同来源的信息若存在冲突,请以最新/最权威来源为准,或明确标注不确定性。\n"
        "- 若大模型初步回答已较完整,但工具结果提供了更新/更详细的数据,请在初步回答基础上补充修正。\n"
        "- 若工具结果与初步回答完全一致,可精简输出,避免冗余。\n"
        "- 最终答案应自成一体,用户无需知道这是多源汇总的结果。"
    )

    updated_messages[-1]["content"] = clean_txt if clean_txt.strip() else "[已执行命令]"
    updated_messages.append({"role": "system", "content": blend_system_content})

    # 第二轮前再次压缩(工具结果可能很长)
    auto_compress_messages(state, updated_messages)

    # 检测保存意图,追加提示强制第二轮 AI 调用 write_file
    if has_save_intent(u):
        save_hint = (
            "\n[系统提示:用户原始请求中包含'保存到本地'的意图。"
            "请在给出最终整理后的回答后,使用 write_file 工具将完整内容保存到文件。"
            "如果用户未指定文件名,请使用一个能反映内容主题的简洁文件名(如 a2a_introduction.md)。]"
        )
        updated_messages.append({"role": "system", "content": save_hint})

    sys.stdout.write(f"{GREEN}{T('prompt_ai', lang)} ")
    sys.stdout.flush()
    final_txt, final_usage, final_response_time, _ = stream_cnt(
        state.client, state.model_name, updated_messages, lang,
        custom_prefix="", max_tokens=state.limit,
    )
    updated_messages.append({"role": "assistant", "content": final_txt})

    if final_usage:
        record_usage(state, final_usage)
        usage = final_usage
    response_time += final_response_time

    return usage, response_time
