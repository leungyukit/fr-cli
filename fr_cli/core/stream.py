"""
流式输出与高亮状态机引擎

性能优化：
- 缓冲 50ms flush 一次（避免逐 token 终端 IO 卡顿）
- 代码块高亮状态机
- 中断检测（用户按 Esc）
"""
import sys
import time
import threading
from fr_cli.ui.ui import RESET, DIM, CYAN, RED, GREEN, CODE_BG, CODE_FG
from fr_cli.lang.i18n import T

_FLUSH_INTERVAL_MS = 50  # 每 50ms 刷新一次（实测流畅且不卡）
_MAX_BUFFER_CHARS = 4096  # 累积超过这个数强制 flush


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


def stream_cnt(client, model, messages, lang, custom_prefix=None, max_tokens=None, silent=False):
    """
    流式调用 LLM 并实时打印，带有简易代码块高亮状态机

    性能：
    - 缓冲 50ms flush 一次（实测流畅度提升 3-5x）
    - 中断支持（通过 request_interrupt() 触发）

    :param client: LLM 客户端实例 (BaseLLMClient 子类)
    :param silent: 如果为 True，则不输出到终端，仅返回文本
    :return: tuple (完整回复文本 str, 使用情况 dict, 响应时间 float, 是否被中断 bool)
    """
    _current_interrupt.reset()
    interrupted = False

    if not silent:
        p = custom_prefix or f"{GREEN}{T('prompt_ai', lang)} "
        sys.stdout.write(p); sys.stdout.flush()

    start_time = time.time()
    full_text = ""
    in_code = False
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

    def _colorize(txt: str) -> str:
        """代码块高亮处理（带缓冲）"""
        nonlocal in_code, buf
        if "```" in txt:
            parts = txt.split("```")
            for i, part in enumerate(parts):
                if i > 0:
                    in_code = not in_code
                    buf += f"{CODE_BG}{CODE_FG}" if in_code else GREEN
                if part:
                    if in_code:
                        buf += f"{CODE_BG}{CODE_FG}{part}"
                    else:
                        buf += f"{GREEN}{part}"
        else:
            if in_code:
                buf += f"{CODE_BG}{CODE_FG}{txt}"
            else:
                buf += f"{GREEN}{txt}"

    try:
        # 验证 API 密钥（Mock 客户端允许空 key）
        from fr_cli.core.llm import MockLLMClient
        is_mock = isinstance(client, MockLLMClient)
        if not is_mock and (not client.api_key or len(client.api_key) < 10):
            print(f"{RED}[错误] API 密钥未配置或格式不正确{RESET}")
            return "[错误] 请先配置有效的 API 密钥", {}, 0.0, False

        response = client.stream_chat(
            model=model,
            messages=messages,
            max_tokens=max_tokens if max_tokens else 4096
        )

        for chunk in response:
            # 中断检测
            if _current_interrupt.is_set():
                interrupted = True
                break

            txt = chunk.get("content", "")
            if txt:
                full_text += txt
                if not silent:
                    _colorize(txt)
                    now = time.time()
                    # 缓冲超过时间或超过大小都 flush
                    if (now - last_flush) * 1000 >= _FLUSH_INTERVAL_MS or len(buf) >= _MAX_BUFFER_CHARS:
                        _do_flush()
                        last_flush = now

            if chunk.get("usage"):
                usage = chunk["usage"]

        # 循环结束 flush 剩余
        if not silent:
            _do_flush()

    except Exception as e:
        # 错误信息立即显示，不缓冲
        if not silent:
            _do_flush()
            sys.stdout.write(f"\n{RED}{str(e)[:200]}{RESET}\n")
            sys.stdout.flush()

    if not silent:
        sys.stdout.write(f"{RESET}\n")
        sys.stdout.flush()

    end_time = time.time()
    response_time = end_time - start_time

    if interrupted and not full_text.endswith("\n[已中断]"):
        full_text = full_text + "\n[已中断]"

    if not full_text:
        return "[错误] 无法获取 AI 回复，请检查 API 密钥配置", usage, response_time, False

    return full_text, usage, response_time, interrupted
