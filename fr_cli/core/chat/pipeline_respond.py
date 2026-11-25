"""
pipeline 阶段 3+4:插件前置拦截 + 流式调用 + 多源汇总

从 fr_cli.core.chat.pipeline 拆出(原文件 488 行)。
- _maybe_run_local_plugin: /plugin_name 开头直接执行本地插件(无 LLM 调用)
- _stream_and_respond:     流式调用 + 事件广播 + 命令自动执行([*] 风格展示)
- _multi_source_blend:     初步回答 + 工具结果 → 第二轮汇总调用
"""
from __future__ import annotations

import sys

from fr_cli.core.headless import is_headless
from fr_cli.lang.i18n import T
from fr_cli.ui.ui import BOLD, CYAN, DIM, GREEN, RED, RESET, print_styled
from fr_cli.core.stream import stream_cnt
from fr_cli.core.intent import has_save_intent

from fr_cli.core.chat.helpers import (
    auto_compress_messages,
    record_usage,
    fold_result,
)

# v2.8.7(UX)：单轮内最多注入几轮转向指令 —— 防止用户连续按 Ctrl+S 造成无限循环
MAX_STEER_ROUNDS = 3


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
    # v2.8.7+:无头模式(bot / 服务端进程)不向 stdout 输出,只取回文本
    headless = is_headless(state)

    # v2.8.7(P0-2):LLM 调用韧性 —— timeout 可配 + 瞬时错误重试 + 主模型挂了降级
    timeout = None
    try:
        timeout = (getattr(state, "cfg", None) or {}).get("llm_timeout") or None
    except Exception:
        timeout = None
    fallback = None
    try:
        getter = getattr(state, "get_fallback_client", None)
        if callable(getter):
            fallback = getter
    except Exception:
        fallback = None

    # v2.8.7(P1-2)：llm.requested / llm.responded / llm.failed 的派发已
    # **下沉到 core/stream.py::stream_cnt** —— 它是全仓 LLM 调用的唯一漏斗，
    # 覆盖 MasterAgent 的 ReAct 循环等此前绕过派发的路径。
    # 这里再派发一次会双计数，故移除。

    # v2.8.7(P0-3)：原生 function calling
    # 工具 schema 由注册表导出（command/schema.py::export_schemas 已是 OpenAI 格式），
    # 客户端不支持（SUPPORTS_TOOLS=False）或用户关闭时自动退回文本标记路径。
    tools_payload = None
    tool_acc = None
    try:
        cfg = getattr(state, "cfg", None) or {}
        if cfg.get("function_calling", True):
            from fr_cli.core.llm.function_calling import (
                ToolCallAccumulator,
                build_tools_payload,
                client_supports_tools,
            )
            if client_supports_tools(state.client):
                tools_payload = build_tools_payload()
                if tools_payload:
                    tool_acc = ToolCallAccumulator()
    except Exception:
        tools_payload = None
        tool_acc = None

    try:
        txt, usage, response_time, _ = stream_cnt(
            state.client, state.model_name, updated_messages, lang,
            max_tokens=state.limit,
            silent=headless,
            timeout=timeout,
            fallback=fallback,
            provider=getattr(state, "provider", None),
            tools=tools_payload,
            tool_accumulator=tool_acc,
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
        if not headless:
            print_styled(f"{RED}{friendly_print(e)}{RESET}")
        return None, None, 0.0

    if usage:
        record_usage(state, usage)
    updated_messages.append({"role": "assistant", "content": txt})

    # v2.8.7(P1-2)：llm.responded 已由 stream_cnt 派发 —— 移除此处重复派发
    # （重复派发会让 metrics 计数翻倍）

    # ---- 原生 function calling：执行模型请求的工具并回填结果 ----
    native_calls = tool_acc.finish() if tool_acc is not None else []
    if native_calls:
        txt, usage, response_time = _handle_native_tool_calls(
            state, updated_messages, native_calls, txt, usage, response_time,
            lang, headless, tools_payload, timeout, fallback,
        )

    # ---- 转向指令注入（v2.8.7 UX）----
    # 用户在 AI 生成途中按 Ctrl+S 追加的指令，不是"下一轮"，而是**当前轮的追加输入**：
    # 这里把它作为 user 消息塞回本轮历史，再跑一次 LLM，让模型带着新指令重新回答。
    txt, usage, response_time = _run_steer_rounds(
        state, updated_messages, lang, headless, tools_payload, timeout, fallback,
        txt, usage, response_time,
    )

    # 自动执行 AI 响应中的命令
    try:
        clean_txt, cmd_results = state.executor.process_ai_commands(txt, updated_messages)
    except Exception as e:
        from fr_cli.core.errors import friendly_print
        if not headless:
            print_styled(f"{RED}{friendly_print(e)}{RESET}")
        clean_txt, cmd_results = txt, []

    # AI 响应已在 stream_cnt 中实时渲染（流式 Markdown），此处不再整篇重渲染，
    # 仅展示命令自动执行的结果（[*] 头 + dim 体，Claude Code 风格），避免重复输出
    if cmd_results and not headless:
        print()
        for result in cmd_results:
            folded = fold_result(result)
            head, _, body = folded.partition("\n")
            print_styled(f"{CYAN}[*]{RESET} {BOLD}{head.strip()}{RESET}")
            body = body.strip("\n")
            if body.strip():
                print_styled(f"{DIM}{body}{RESET}")

    # 多源汇总第二轮
    if cmd_results:
        usage, response_time = _multi_source_blend(
            state, updated_messages, clean_txt, cmd_results, u, lang, usage, response_time,
        )

    return txt, usage, response_time


def _run_steer_rounds(
    state, updated_messages, lang, headless, tools_payload, timeout, fallback,
    txt, usage, response_time,
):
    """把"转向指令"注入**当前这一轮**并重跑 LLM。

    v2.8.7(UX)：与对话队列(repl/queue.py)的区别 ——
    队列排成**下一轮**独立对话，steering 注入**当前轮**，
    模型在原有上下文上看到新指令后重新回答，本轮整体时长相应变长。

    最多跑 ``MAX_STEER_ROUNDS`` 轮，防止用户连续按 Ctrl+S 导致无限循环。
    """
    from fr_cli.core.steering import drain_steer, format_steer_notice

    for _ in range(MAX_STEER_ROUNDS):
        steer_msgs = drain_steer(state)
        if not steer_msgs:
            break
        if not headless:
            print_styled(
                f"{CYAN}[↯]{RESET} {DIM}{format_steer_notice(len(steer_msgs))}{RESET}"
            )
        new_txt, new_usage, new_rt = _apply_steer(
            state, updated_messages, steer_msgs, lang, headless,
            tools_payload, timeout, fallback,
        )
        if new_txt is None:
            break
        txt = new_txt
        if new_usage:
            usage = new_usage
        if new_rt:
            response_time += new_rt

    return txt, usage, response_time


def _apply_steer(
    state, updated_messages, steer_msgs, lang, headless,
    tools_payload, timeout, fallback,
):
    """把转向指令作为 user 消息追加进本轮历史，再跑一次 LLM。

    Returns:
        ``(新文本, usage, response_time)``；失败时新文本为 ``None``（保留原文本）。
    """
    for msg in steer_msgs:
        updated_messages.append({"role": "user", "content": msg})

    # 转向消息也会占上下文，压缩阈值照常生效
    auto_compress_messages(state, updated_messages)

    # 转向轮同样允许原生 function calling —— 模型可能"改主意"要调工具
    tool_acc = None
    if tools_payload:
        try:
            from fr_cli.core.llm.function_calling import ToolCallAccumulator
            tool_acc = ToolCallAccumulator()
        except Exception:
            tool_acc = None

    try:
        txt, usage, response_time, _ = stream_cnt(
            state.client, state.model_name, updated_messages, lang,
            max_tokens=state.limit,
            silent=headless,
            timeout=timeout,
            fallback=fallback,
            provider=getattr(state, "provider", None),
            tools=tools_payload,
            tool_accumulator=tool_acc,
        )
    except Exception as e:
        from fr_cli.core.errors import friendly_print
        if not headless:
            print_styled(f"{RED}{friendly_print(e)}{RESET}")
        return None, None, 0.0

    if usage:
        record_usage(state, usage)
    updated_messages.append({"role": "assistant", "content": txt})

    native_calls = tool_acc.finish() if tool_acc is not None else []
    if native_calls:
        txt, usage, response_time = _handle_native_tool_calls(
            state, updated_messages, native_calls, txt, usage, response_time,
            lang, headless, tools_payload, timeout, fallback,
        )

    return txt, usage, response_time


def _tool_result_text(name: str, result, print_lines: list, exc=None) -> str:
    """把一次工具执行的结果转成「回给模型的文本」+「给用户看的一行」。

    Args:
        name: 工具名
        result: Result 对象；None 表示执行过程抛了异常
        print_lines: 打印行收集器（并发执行时先收集、最后按顺序输出）
        exc: 执行异常（result 为 None 时给出）

    Returns:
        回给模型的文本
    """
    if exc is not None:
        print_lines.append(f"{RED}[*] {name}: {exc}{RESET}")
        return f"[x] {name} 执行异常: {exc}"
    try:
        if result.is_ok():
            payload = result.unwrap()
            print_lines.append(f"{CYAN}[*]{RESET} {BOLD}{name}{RESET}")
            return str(payload) if payload is not None else "(无返回)"
        err = result.error
        print_lines.append(f"{RED}[*] {name}: {err}{RESET}")
        return f"[x] {name} 执行失败: {err}"
    except Exception as e:
        print_lines.append(f"{RED}[*] {name}: {e}{RESET}")
        return f"[x] {name} 执行异常: {e}"


def _handle_native_tool_calls(
    state, updated_messages, native_calls, first_txt, usage, response_time,
    lang, headless, tools_payload, timeout, fallback,
):
    """执行模型通过**原生 function calling** 请求的工具，把结果回填后跑第二轮。

    v2.8.7（P0-3）：这是原生 function calling 的闭环 ——
    模型请求工具 → 本地执行 → 以 ``role="tool"`` 回填 → 模型基于真实结果继续推理。

    与既有的文本标记路径（``【调用：tool({...})】`` + ``process_ai_commands``）
    是**两条并存**的路径：这里只处理 provider 原生返回的 tool_calls。

    Returns:
        ``(最终文本, usage, response_time)``
    """
    from fr_cli.core.llm.function_calling import tool_calls_to_messages

    results: list[str] = []
    # 打印行先收集、最后按顺序输出 —— 并发执行时直接 print 会交错
    print_lines: list[str] = []

    # v2.8.7（长线-3）：原生 function calling 一次可以返回**多个** tool_calls
    # （"读这三个文件"）。此前这里是无条件串行，等于把模型的一次决策拆成 N 次等待。
    # ≥2 个时并发执行，结果仍按调用顺序回填 —— ``role="tool"`` 消息必须与
    # 请求顺序一一对应。
    runnable = [(i, c) for i, c in enumerate(native_calls) if not c.error]
    outcome: dict[int, str] = {}

    if len(runnable) >= 2:
        from fr_cli.command.parallel import ParallelExecutor
        par = ParallelExecutor(state.executor)
        res_list = par.execute_parsed([(c.name, c.arguments) for _, c in runnable])
        for (idx, call), res in zip(runnable, res_list):
            outcome[idx] = _tool_result_text(call.name, res, print_lines)
    else:
        for idx, call in runnable:
            exc = None
            try:
                res = state.executor.invoke_tool(call.name, call.arguments)
            except Exception as e:
                res = None
                exc = e
            outcome[idx] = _tool_result_text(call.name, res, print_lines, exc=exc)

    for idx, call in enumerate(native_calls):
        if call.error:
            # 参数解析失败 —— 把错误回给模型，让它自己纠正（这正是原生协议的价值）
            results.append(f"[x] 工具参数无效: {call.error}")
        else:
            results.append(outcome.get(idx, "(无返回)"))

    # 回填：assistant(tool_calls) + 逐条 role="tool"
    updated_messages.extend(tool_calls_to_messages(native_calls, results))

    if not headless:
        for text in print_lines:
            print_styled(text)

    # 第二轮 —— 模型基于真实工具结果给出最终回答
    auto_compress_messages(state, updated_messages)
    try:
        final_txt, final_usage, final_rt, _ = stream_cnt(
            state.client, state.model_name, updated_messages, lang,
            max_tokens=state.limit,
            silent=headless,
            timeout=timeout,
            fallback=fallback,
            provider=getattr(state, "provider", None),
            tools=tools_payload,
        )
    except Exception as e:
        from fr_cli.core.errors import friendly_print
        if not headless:
            print_styled(f"{RED}{friendly_print(e)}{RESET}")
        final_txt, final_usage, final_rt = first_txt, usage, response_time

    if final_usage:
        record_usage(state, final_usage)
    updated_messages.append({"role": "assistant", "content": final_txt})
    return final_txt, final_usage or usage, final_rt or response_time


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

    if not is_headless(state):
        sys.stdout.write(f"{GREEN}{T('prompt_ai', lang)} ")
        sys.stdout.flush()
    final_txt, final_usage, final_response_time, _ = stream_cnt(
        state.client, state.model_name, updated_messages, lang,
        custom_prefix="", max_tokens=state.limit,
        silent=is_headless(state),
    )
    updated_messages.append({"role": "assistant", "content": final_txt})

    if final_usage:
        record_usage(state, final_usage)
        usage = final_usage
    response_time += final_response_time

    return usage, response_time
