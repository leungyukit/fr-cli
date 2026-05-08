"""
流式输出与高亮状态机引擎
"""
import sys
import time
from fr_cli.ui.ui import RESET, DIM, CYAN, RED, CODE_BG, CODE_FG
from fr_cli.lang.i18n import T


def stream_cnt(client, model, messages, lang, custom_prefix=None, max_tokens=None, silent=False):
    """
    流式调用 LLM 并实时打印，带有简易代码块高亮状态机
    :param client: LLM 客户端实例 (BaseLLMClient 子类)
    :param silent: 如果为True，则不输出到终端，仅返回文本
    :return: tuple (完整回复文本 str, 使用情况 dict, 响应时间 float)
    """
    if not silent:
        p = custom_prefix or f"{CYAN}{T('prompt_ai', lang)}{RESET} "
        sys.stdout.write(p); sys.stdout.flush()

    start_time = time.time()
    full_text = ""
    in_code = False
    usage = {}

    try:
        # 验证API密钥
        if not client.api_key or len(client.api_key) < 10:
            print(f"{RED}[错误] API密钥未配置或格式不正确{RESET}")
            return "[错误] 请先配置有效的API密钥", {}, 0.0

        response = client.stream_chat(
            model=model,
            messages=messages,
            max_tokens=max_tokens if max_tokens else 4096
        )

        for chunk in response:
            txt = chunk.get("content", "")
            if txt:
                full_text += txt
                # 简易状态机：检测 ``` 切换代码背景
                if "```" in txt:
                    parts = txt.split("```")
                    for i, part in enumerate(parts):
                        if i > 0:  # 遇到了一个 ```
                            in_code = not in_code
                            if not silent:
                                if in_code:
                                    sys.stdout.write(f"{CODE_BG}{CODE_FG}")
                                else:
                                    sys.stdout.write(f"{RESET}")
                        if not silent:
                            sys.stdout.write(part)
                        sys.stdout.flush()
                else:
                    if not silent:
                        if in_code:
                            sys.stdout.write(f"{CODE_BG}{CODE_FG}{txt}{CODE_FG}")
                        else:
                            sys.stdout.write(txt)
                    sys.stdout.flush()

            if chunk.get("usage"):
                usage = chunk["usage"]

    except Exception as e:
        sys.stdout.write(f"\n{DIM}{str(e)[:50]}{RESET}")
        sys.stdout.flush()

    if not silent:
        sys.stdout.write(RESET)
        sys.stdout.write("\n")
        sys.stdout.flush()

    end_time = time.time()
    response_time = end_time - start_time

    # 如果没有收到任何内容，返回提示信息
    if not full_text:
        return "[错误] 无法获取AI回复，请检查API密钥配置", usage, response_time

    return full_text, usage, response_time
