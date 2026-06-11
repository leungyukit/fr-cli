"""
流式输出与高亮状态机引擎

性能优化：
- 缓冲 50ms flush 一次（避免逐 token 终端 IO 卡顿）
- 代码块高亮状态机（支持语言标识显示）
- 中断检测（用户按 Esc）
"""
import sys
import time
import threading
import re
from fr_cli.ui.ui import RESET, DIM, CYAN, RED, GREEN, MAGENTA, CODE_BG, CODE_FG, _NO_COLOR
from fr_cli.lang.i18n import T


_FLUSH_INTERVAL_MS = 50  # 每 50ms 刷新一次（实测流畅且不卡）
_MAX_BUFFER_CHARS = 4096  # 累积超过这个数强制 flush


def _is_prompt_toolkit_stdout() -> bool:
    """检测当前 stdout 是否被 prompt_toolkit.patch_stdout 接管"""
    return "prompt_toolkit" in type(sys.stdout).__module__


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
    with _ColorDisable():
        _current_interrupt.reset()
        interrupted = False

        if not silent:
            p = custom_prefix or f"{GREEN}{T('prompt_ai', lang)} "
            sys.stdout.write(p)
            sys.stdout.flush()

        start_time = time.time()
        full_text = ""
        in_code = False
        current_lang = ""       # 当前代码块的语言标识
        lang_detect_buf = ""    # 跨 chunk 语言标识检测缓冲
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
            """代码块高亮处理（带缓冲），支持语言标识检测"""
            nonlocal in_code, buf, current_lang, lang_detect_buf
            if "```" in txt:
                parts = txt.split("```")
                for i, part in enumerate(parts):
                    if i > 0:
                        in_code = not in_code
                        if in_code:
                            # 进入代码块：尝试检测语言标识
                            # 语言标识通常在 ``` 后直接跟随，如 ```python\n
                            lang_detect_buf += part
                            # 等待完整的第一行来确定语言
                            if '\n' in lang_detect_buf:
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
                            else:
                                # 语言标识跨 chunk，暂不输出
                                continue
                        else:
                            # 退出代码块：先 RESET 关闭代码块颜色，再切回普通文本绿色
                            current_lang = ""
                            lang_detect_buf = ""
                            buf += f"{RESET}{GREEN}"
                    elif in_code and lang_detect_buf:
                        # 正在等待语言标识的换行符
                        lang_detect_buf += part
                        if '\n' in lang_detect_buf:
                            first_line = lang_detect_buf.split('\n', 1)[0]
                            lang_match = re.match(r'^(\w+)$', first_line.strip())
                            if lang_match:
                                current_lang = lang_match.group(1)
                                if not _NO_COLOR:
                                    buf += f"{CODE_BG}{CODE_FG}{MAGENTA}[{current_lang}]{RESET}{CODE_BG}{CODE_FG}"
                                else:
                                    buf += f"[{current_lang}]"
                                remaining = lang_detect_buf[len(first_line):]
                                if remaining:
                                    buf += f"{CODE_BG}{CODE_FG}{remaining}"
                            else:
                                current_lang = ""
                                buf += f"{CODE_BG}{CODE_FG}{lang_detect_buf}"
                            lang_detect_buf = ""
                        else:
                            continue
                    elif part:
                        if in_code:
                            buf += f"{CODE_BG}{CODE_FG}{part}"
                        else:
                            buf += f"{GREEN}{part}"
            else:
                if in_code and lang_detect_buf:
                    # 仍在等待语言标识
                    lang_detect_buf += txt
                    if '\n' in lang_detect_buf:
                        first_line = lang_detect_buf.split('\n', 1)[0]
                        lang_match = re.match(r'^(\w+)$', first_line.strip())
                        if lang_match:
                            current_lang = lang_match.group(1)
                            if not _NO_COLOR:
                                buf += f"{CODE_BG}{CODE_FG}{MAGENTA}[{current_lang}]{RESET}{CODE_BG}{CODE_FG}"
                            else:
                                buf += f"[{current_lang}]"
                            remaining = lang_detect_buf[len(first_line):]
                            if remaining:
                                buf += f"{CODE_BG}{CODE_FG}{remaining}"
                        else:
                            current_lang = ""
                            buf += f"{CODE_BG}{CODE_FG}{lang_detect_buf}"
                        lang_detect_buf = ""
                elif in_code:
                    buf += f"{CODE_BG}{CODE_FG}{txt}"
                else:
                    buf += f"{GREEN}{txt}"

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

            response = client.stream_chat(
                model=model,
                messages=messages,
                max_tokens=max_tokens if max_tokens else 4096,
                timeout=60,
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
            # 错误信息立即显示，不缓冲，走统一友好错误处理
            if not silent:
                _do_flush()
                from fr_cli.core.errors import friendly_print
                err_msg = friendly_print(e)
                sys.stdout.write(f"\n{err_msg}\n")
                sys.stdout.flush()

        if not silent:
            _do_flush()
            sys.stdout.write(f"{RESET}\n")
            sys.stdout.flush()

    end_time = time.time()
    response_time = end_time - start_time

    if interrupted and not full_text.endswith("\n[已中断]"):
        full_text = full_text + "\n[已中断]"

    if not full_text:
        return "[错误] 无法获取 AI 回复，请检查 API 密钥配置", usage, response_time, False

    return full_text, usage, response_time, interrupted
