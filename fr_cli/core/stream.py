"""
流式输出与高亮状态机引擎

性能优化：
- 缓冲 50ms flush 一次（避免逐 token 终端 IO 卡顿）
- 流式 Markdown 实时渲染（标题/列表/代码块/表格边输出边排版）
- 代码块高亮状态机（markdown=False 时的降级路径）
- 中断检测（用户按 Esc）
"""
import sys
import time
import re
from fr_cli.ui.ui import RESET, DIM, CYAN, RED, GREEN, MAGENTA, CODE_BG, CODE_FG, _NO_COLOR
from fr_cli.lang.i18n import T


_FLUSH_INTERVAL_MS = 50  # 每 50ms 刷新一次（实测流畅且不卡）
_MAX_BUFFER_CHARS = 4096  # 累积超过这个数强制 flush


def _is_prompt_toolkit_stdout() -> bool:
    """检测当前 stdout 是否被 prompt_toolkit.patch_stdout 接管

    判定逻辑收口在 ui.stdout_is_prompt_toolkit_proxy()(单一判定源),
    这里保留薄封装: cron.py 等历史 import 与本文件的 monkeypatch 测试不变。
    """
    from fr_cli.ui import ui as _ui
    return _ui.stdout_is_prompt_toolkit_proxy()


def _markdown_use_color() -> bool:
    """流式 Markdown 渲染器的颜色开关(实时判定, 不用 import 时快照)

    颜色要开需同时满足:
    ① ui 未被 set_no_color(True) 显式关掉(运行时可覆盖态)
    ② 环境判定 color_enabled() 为真(双 TTY 且无 NO_COLOR / FR_CLI_NO_COLOR)
    ③ stdout 没被 prompt_toolkit.patch_stdout 代理 —— StdoutProxy 非 raw
       模式走 Vt100_Output.write(), 会把 ANSI 的 ESC 字节替换成字面 '?',
       打色就显示 ?[96m 乱码(与 _ColorDisable / cron 的 _ProxyColorDisable
       同款策略; 真实 TTY 下 isatty 仍为 True, 只有这项能拦住)
    任一不满足 → False, 渲染器原样吐文本, 不会泄漏转义序列。
    """
    from fr_cli.ui import ui as _ui
    return (
        not _ui._NO_COLOR
        and _ui.color_enabled()
        and not _is_prompt_toolkit_stdout()
    )


class _ColorDisable:
    """临时禁用 stream.py 内部颜色常量的上下文管理器

    prompt_toolkit.patch_stdout 会把原始 ANSI 转义序列当作纯文本显示，
    导致用户看到 [92m / ?[92m 这类字符。在此环境下强制禁用颜色输出。
    """

    def __enter__(self):
        global RESET, DIM, CYAN, RED, GREEN, MAGENTA, CODE_BG, CODE_FG
        self._orig = {
            "RESET": RESET, "DIM": DIM, "CYAN": CYAN, "RED": RED,
            "GREEN": GREEN, "MAGENTA": MAGENTA, "CODE_BG": CODE_BG, "CODE_FG": CODE_FG,
        }
        if _NO_COLOR or _is_prompt_toolkit_stdout():
            RESET = DIM = CYAN = RED = GREEN = MAGENTA = CODE_BG = CODE_FG = ""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        global RESET, DIM, CYAN, RED, GREEN, MAGENTA, CODE_BG, CODE_FG
        RESET = self._orig["RESET"]
        DIM = self._orig["DIM"]
        CYAN = self._orig["CYAN"]
        RED = self._orig["RED"]
        GREEN = self._orig["GREEN"]
        MAGENTA = self._orig["MAGENTA"]
        CODE_BG = self._orig["CODE_BG"]
        CODE_FG = self._orig["CODE_FG"]


class _InterruptSignal:
    """流式输出中断信号（Esc 键）"""
    def __init__(self):
        self._flag = False
    def set(self):
        self._flag = True
    def is_set(self):
        return self._flag
    def reset(self):
        self._flag = False


_current_interrupt = _InterruptSignal()


def request_interrupt():
    """外部调用此函数请求中断当前流式输出（按 Esc 时调用）"""
    _current_interrupt.set()


def _looks_like_tools_rejection(exc: BaseException) -> bool:
    """判断异常是否由"provider 不接受 tools 参数"引起。

    v2.8.7(P0-3)：个别 OpenAI 兼容端点只支持部分模型的原生 tools，
    传入后会直接 400。命中时自动去掉 tools 重试一次，退回文本标记路径。
    """
    msg = (str(exc) or "").lower()
    if "tool" not in msg and "function" not in msg:
        return False
    return any(k in msg for k in (
        "not support", "unsupported", "invalid", "unknown", "unrecognized",
        "not allowed", "unexpected", "does not support", "extra inputs",
        "not permitted", "not allowed",
    ))


def _dispatch_llm_event(event_attr: str, data: dict) -> None:
    """派发 LLM 生命周期事件（永不抛异常）。

    v2.8.7（P1-2）：把 ``llm.requested`` / ``llm.responded`` / ``llm.failed``
    的派发**下沉到 stream_cnt** —— 它是全仓所有 LLM 调用的唯一漏斗
    （20+ 个调用点，含 MasterAgent 的 ReAct 循环）。

    此前事件只在 ``core/chat/pipeline_respond.py`` 里派发，而 MasterAgent
    默认接管普通对话后那条路径根本不会走 → ``llm.*`` 指标恒为 0（假零）。
    下沉后所有调用方自动被覆盖，且不会重复计数。

    Args:
        event_attr: ``V2Events`` 的属性名（如 "LLM_REQUESTED"）
        data: 事件负载
    """
    try:
        from fr_cli.core.events import V2Events, dispatch_event
        name = getattr(V2Events, event_attr, None)
        if not name:
            return
        dispatch_event(name, data=data, source="stream")
    except Exception:
        pass


def stream_cnt(client, model, messages, lang, custom_prefix=None, max_tokens=None,
               silent=False, markdown=True, timeout=None, retry=None, fallback=None,
               provider=None, tools=None, tool_choice=None, tool_accumulator=None):
    """
    流式调用 LLM 并实时打印，带有简易代码块高亮状态机

    性能：
    - 缓冲 50ms flush 一次（实测流畅度提升 3-5x）
    - 中断支持（通过 request_interrupt() 触发）
    - markdown=True（默认）时用 StreamingMarkdownRenderer 实时渲染
      Markdown（标题/列表/代码块/表格），不再等结束后整篇重渲染

    v2.8.7（P0-2）新增韧性能力：
    - **重试**：瞬时错误（网络抖动 / 超时 / 限流 / 5xx）自动指数退避重试；
      已产出内容后不再重试（避免重复输出）
    - **降级**：主模型彻底失败时，可切到备用 provider 再试一次
    - **timeout 可配**：默认取 client.DEFAULT_TIMEOUT（60s），不再写死
    - **错误不再被吞**：失败时返回真实原因，而不是笼统的"请检查 API 密钥配置"

    :param client: LLM 客户端实例 (BaseLLMClient 子类)
    :param silent: 如果为 True，则不输出到终端，仅返回文本
    :param markdown: 是否对流式输出做实时 Markdown 渲染（silent 时无效）
    :param timeout: 单次请求超时秒数；None → client.DEFAULT_TIMEOUT
    :param retry: 重试次数（不含首次）；None → resilience.DEFAULT_RETRY
    :param fallback: 降级来源 —— (client, model) 元组或返回它的可调用对象
    :param provider: 提供商名（仅用于事件上报，可选）
    :param tools: OpenAI 格式的 function schema 数组（原生 function calling）
    :param tool_choice: "auto" / "none" / "required"
    :param tool_accumulator: 可选的 :class:`ToolCallAccumulator` —— 收到
        原生 tool_call 分片时累积进去（上层据此执行工具并回填结果）
    :return: tuple (完整回复文本 str, 使用情况 dict, 响应时间 float, 是否被中断 bool)
    """
    from fr_cli.core.llm.resilience import (
        DEFAULT_BACKOFF,
        DEFAULT_RETRY,
        call_with_retry,
        describe_error,
        is_transient,
        resolve_fallback,
    )

    if timeout is None:
        timeout = getattr(client, "DEFAULT_TIMEOUT", 60)
    if retry is None:
        retry = DEFAULT_RETRY
    attempts = max(1, int(retry) + 1)

    with _ColorDisable():
        _current_interrupt.reset()
        interrupted = False

        # 流式 Markdown 渲染器(实时读取全局颜色状态, 不用 import 时快照):
        # 组合判定见 _markdown_use_color(); 非 TTY / NO_COLOR / FR_CLI_NO_COLOR
        # 任一命中即 use_color=False, 不向非 TTY 泄漏 ANSI 转义序列。
        renderer = None
        if markdown and not silent:
            from fr_cli.ui.markdown_stream import StreamingMarkdownRenderer
            renderer = StreamingMarkdownRenderer(use_color=_markdown_use_color())

        if not silent:
            p = custom_prefix or f"{GREEN}{T('prompt_ai', lang)} "
            sys.stdout.write(p)
            sys.stdout.flush()

        start_time = time.time()
        full_text = ""
        in_code = False
        awaiting_lang = False   # 进入代码块后是否在等语言标识行
        current_lang = ""       # 当前代码块的语言标识
        lang_detect_buf = ""    # 跨 chunk 语言标识检测缓冲
        pending_ticks = ""      # 结尾挂起的 1~2 个反引号(可能是被截断的 ``` 围栏)
        usage = {}
        buf = ""  # 输出缓冲
        last_flush = time.time()

        def _do_flush():
            """实际写入 + flush"""
            nonlocal buf
            if buf:
                sys.stdout.write(buf)
                sys.stdout.flush()
                buf = ""

        def _flush_renderer():
            """收尾:把渲染器里未换行的残行 + 挂起的反引角吐出到 buf"""
            nonlocal buf, pending_ticks
            if renderer is not None:
                buf += renderer.flush()
            if pending_ticks:
                # 流结束了,挂起的反引角不再是围栏的一部分,按当前上下文补输出
                buf += (f"{CODE_BG}{CODE_FG}{pending_ticks}" if in_code else f"{GREEN}{pending_ticks}")
                pending_ticks = ""

        def _emit(txt: str, mode: str = "answer"):
            """输出一段新内容：优先走 Markdown 渲染器，降级走代码块高亮

            Args:
                mode: 语义色 —— ``answer``（最终答案，绿色）/ ``reasoning``
                      （思考过程，暗色）。两者在终端上可区分。
            """
            nonlocal buf
            if renderer is not None:
                # 模式切换时先把没换行的残余按旧模式吐出 ——
                # 否则思考与答案挤在同一行，颜色就分不开
                buf += renderer.set_mode(mode)
                buf += renderer.feed(txt)
            else:
                _colorize(txt, mode)

        def _colorize(txt: str, mode: str = "answer"):
            """代码块高亮处理（带缓冲），支持跨 chunk 的语言标识检测

            状态: in_code(代码块内) + awaiting_lang(等待语言标识行的换行符)
            修复: 旧版靠 lang_detect_buf 真值判断"是否在等语言标识",
            ``` 与语言标签被分到不同 chunk 且标签恰为空串时会丢状态;
            另修复 ``` 围栏本身被 chunk 边界截断时完全失效的问题
            (结尾 1~2 个反引号挂起到下一 chunk 再判定)。
            """
            nonlocal in_code, buf, current_lang, lang_detect_buf, awaiting_lang, pending_ticks

            # 正文基色（v2.8.7 第四阶段）：答案=绿，思考=暗色（视觉上退到背景）
            text_color = GREEN if mode != "reasoning" else DIM

            def _emit_lang_or_content(s: str):
                """等待语言标识期间的内容:攒到第一行完整再决定 标签/原样输出"""
                nonlocal buf, current_lang, lang_detect_buf, awaiting_lang
                lang_detect_buf += s
                if '\n' not in lang_detect_buf:
                    return  # 语言标识跨 chunk，继续等
                first_line = lang_detect_buf.split('\n', 1)[0]
                lang_match = re.match(r'^(\w+)$', first_line.strip())
                if lang_match:
                    current_lang = lang_match.group(1)
                    if not _NO_COLOR:
                        # 在代码块开头显示语言标签
                        buf += f"{CODE_BG}{CODE_FG}{MAGENTA}[{current_lang}]{RESET}{CODE_BG}{CODE_FG}"
                    else:
                        buf += f"[{current_lang}]"
                    # 去掉语言标识行，保留剩余内容
                    remaining = lang_detect_buf[len(first_line):]
                    if remaining:
                        buf += f"{CODE_BG}{CODE_FG}{remaining}"
                else:
                    current_lang = ""
                    buf += f"{CODE_BG}{CODE_FG}{lang_detect_buf}"
                lang_detect_buf = ""
                awaiting_lang = False

            # 拼接上一 chunk 挂起的反引号
            if pending_ticks:
                txt = pending_ticks + txt
                pending_ticks = ""
            # 结尾 1~2 个反引号先挂起:下一 chunk 若以 ``` 补齐就是围栏,
            # 否则按普通文本(行内代码收尾)补跑。
            # 护栏:txt 以完整 ``` 结尾时不能挂起,否则会把围栏切碎。
            tick_m = re.search(r'`{1,2}\Z', txt)
            if tick_m and not re.search(r'```\Z', txt):
                pending_ticks = tick_m.group(0)
                txt = txt[:tick_m.start()]

            # 按 ``` 切分，奇数段落在代码块内
            parts = txt.split("```")
            for i, part in enumerate(parts):
                if i > 0:
                    in_code = not in_code
                    if in_code:
                        # 进入代码块：后面紧跟的可能是语言标识行（如 ```python\n）
                        awaiting_lang = True
                        lang_detect_buf = ""
                        _emit_lang_or_content(part)
                    else:
                        # 退出代码块：先 RESET 关闭代码块颜色，再切回正文色
                        current_lang = ""
                        lang_detect_buf = ""
                        awaiting_lang = False
                        buf += f"{RESET}{text_color}"
                    continue
                if not part:
                    continue
                if awaiting_lang:
                    _emit_lang_or_content(part)
                elif in_code:
                    buf += f"{CODE_BG}{CODE_FG}{part}"
                else:
                    buf += f"{text_color}{part}"

        def _run_once(c=None, m=None):
            """跑一次流式调用，返回 (文本, usage)。

            异常直接向上抛 —— 由外层的重试/降级逻辑处理。
            已产出的部分内容保存在 ``partial``，避免异常时丢失。

            v2.8.7(P0-3)：若 provider 不接受 tools 参数，去掉 tools 再试一次，
            自动退回文本标记路径。注意 provider 客户端多是**生成器函数** ——
            拒绝异常发生在**迭代期**而非调用期，所以兜底必须包住整个迭代。
            """
            nonlocal interrupted, last_flush, partial
            text = ""
            reasoning_text = ""   # 思考过程（与答案分离，不进历史/记忆）
            usg = {}
            attempt_tools = tools
            while True:
                try:
                    extra = ({"tools": attempt_tools, "tool_choice": tool_choice or "auto"}
                             if attempt_tools else {})
                    response = (c or client).stream_chat(
                        model=(m or model),
                        messages=messages,
                        max_tokens=max_tokens if max_tokens else 4096,
                        timeout=timeout,
                        **extra,
                    )
                    for chunk in response:
                        # 中断检测
                        if _current_interrupt.is_set():
                            interrupted = True
                            break

                        ctext = chunk.get("content", "")
                        if ctext:
                            # v2.8.7(第四阶段):推理模型的思考内容单独收集，
                            # 不混入返回的答案正文（答案要进历史/记忆，思考不进）
                            is_reasoning = bool(chunk.get("reasoning"))
                            if is_reasoning:
                                reasoning_text += ctext
                            else:
                                text += ctext
                            if not silent:
                                # 思考照样可见，但用**暗色**与答案区分开
                                _emit(ctext, "reasoning" if is_reasoning else "answer")
                                now = time.time()
                                # 缓冲超过时间或超过大小都 flush
                                if (now - last_flush) * 1000 >= _FLUSH_INTERVAL_MS or len(buf) >= _MAX_BUFFER_CHARS:
                                    _do_flush()
                                    last_flush = now

                        if chunk.get("usage"):
                            usg = chunk["usage"]

                        # 原生 function calling 的分片
                        if tool_accumulator is not None and chunk.get("tool_calls"):
                            tool_accumulator.add_delta(chunk["tool_calls"])

                    if not text and reasoning_text:
                        # 兜底：部分 provider（火山方舟 coding endpoint 等）
                        # 只把答案放在 reasoning_content 里 —— 此时把思考内容
                        # 当作答案返回，避免「答非所问」。
                        text = reasoning_text
                    return text, usg
                except Exception as e:
                    # provider 不接受 tools —— 去掉 tools 再试一次（只试一次）
                    if attempt_tools and not text and _looks_like_tools_rejection(e):
                        attempt_tools = None
                        continue
                    partial = text
                    raise

        def _on_retry(attempt_no, total, exc, delay):
            """重试提示（仅瞬时错误才走到这里）"""
            if not silent:
                from fr_cli.ui.ui import YELLOW
                sys.stdout.write(
                    f"\n{YELLOW}[!] 调用失败（第 {attempt_no}/{total} 次）："
                    f"{describe_error(exc)} —— {delay:.1f}s 后重试{RESET}\n"
                )
                sys.stdout.flush()

        last_exc = None
        partial = ""      # 异常时已产出的部分内容
        try:
            # 验证 API 密钥（Mock 客户端允许空 key）
            from fr_cli.core.llm import MockLLMClient
            is_mock = isinstance(client, MockLLMClient)
            if not is_mock and (not client.api_key or len(client.api_key) < 10):
                from fr_cli.core.errors import APIKeyError
                err = APIKeyError("API 密钥未配置或格式不正确")
                if not silent:
                    print(f"\n{err.format()}\n")
                return "[错误] 请先配置有效的 API 密钥", {}, 0.0, False

            # ---- 重试（仅在尚未产出任何内容时）----
            _dispatch_llm_event("LLM_REQUESTED", {
                "provider": provider,
                "model": model,
                "messages_count": len(messages or []),
            })
            try:
                full_text, usage = call_with_retry(
                    lambda _n: _run_once(),
                    attempts=attempts,
                    backoff=DEFAULT_BACKOFF,
                    on_retry=_on_retry,
                    should_retry=lambda e: (not partial) and is_transient(e),
                )
            except Exception:
                full_text = partial
                raise

            # 循环结束 flush 剩余（含渲染器里未换行的残行）
            if not silent:
                _flush_renderer()
                _do_flush()

            _dispatch_llm_event("LLM_RESPONDED", {
                "provider": provider,
                "model": model,
                "usage": usage,
                "response_time": time.time() - start_time,
                "output_len": len(full_text) if full_text else 0,
            })

        except Exception as e:
            last_exc = e
            if partial and not full_text:
                full_text = partial

            # ---- 降级：主模型彻底失败且没产出任何内容 → 换备用 provider 再试 ----
            fb = resolve_fallback(fallback) if not full_text else None
            if fb is not None:
                fb_client, fb_model = fb
                if not silent:
                    from fr_cli.ui.ui import YELLOW
                    sys.stdout.write(
                        f"\n{YELLOW}[!] 主模型不可用（{describe_error(e)}），"
                        f"降级到 {fb_model}{RESET}\n"
                    )
                    sys.stdout.flush()
                try:
                    fb_text, fb_usage = call_with_retry(
                        lambda _n: _run_once(fb_client, fb_model),
                        attempts=attempts,
                        backoff=DEFAULT_BACKOFF,
                        on_retry=_on_retry,
                    )
                    full_text += fb_text
                    if fb_usage:
                        usage = fb_usage
                    model = fb_model
                    last_exc = None
                    if not silent:
                        _flush_renderer()
                        _do_flush()
                except Exception as e2:
                    last_exc = e2

            if last_exc is not None:
                # 错误信息立即显示，不缓冲，走统一友好错误处理
                if not silent:
                    _flush_renderer()
                    _do_flush()
                    from fr_cli.core.errors import friendly_print
                    err_msg = friendly_print(last_exc)
                    sys.stdout.write(f"\n{err_msg}\n")
                    sys.stdout.flush()
                _dispatch_llm_event("LLM_FAILED", {
                    "provider": provider,
                    "model": model,
                    "error": str(last_exc),
                })

        if not silent:
            # 渲染器残行已在循环结束/异常两处 flush 过(幂等),这里只需冲终端缓冲
            _do_flush()
            if interrupted:
                # 中断时给用户一个明确的停止标记（Claude Code 风格）
                sys.stdout.write(f"{DIM}[已中断]{RESET}\n")
            else:
                sys.stdout.write(f"{RESET}\n")
            sys.stdout.flush()

    end_time = time.time()
    response_time = end_time - start_time

    if interrupted and not full_text.endswith("\n[已中断]"):
        full_text = full_text + "\n[已中断]"

    if not full_text:
        # v2.8.7(P0-2):失败原因如实带回,不再笼统报"请检查 API 密钥配置"
        if last_exc is not None:
            from fr_cli.core.errors import friendly_print
            return f"[错误] {friendly_print(last_exc)}", usage, response_time, False
        return "[错误] 无法获取 AI 回复，请检查 API 密钥配置", usage, response_time, False

    return full_text, usage, response_time, interrupted
