"""
一次性（非流式）LLM 调用 —— 供蜂群汇总 / Agent Team 聚合等"要一整段结果"的场景使用

为什么需要它
------------
全仓 LLM 客户端的**公开接口**是 ``stream_chat(model, messages, ...)``
（``BaseLLMClient`` 的抽象方法）。但 ``fr_cli/agent/swarm.py::_summarize_with_llm``
直接调了 ``client.chat.completions.create(...)`` —— 那是 OpenAI SDK **内部**对象
（``openai_compat.py`` 里是 ``self._client.chat.completions``），并不是 fr_cli
客户端的公开属性。

后果：所有 OpenAI 兼容厂商（DeepSeek / Kimi / Qwen / StepFun / MiniMax /
讯飞星火 / 小米 MiMo）的**议会（council）汇总一直失败**，最终只会吐一句
``[汇总失败: 'OpenAICompatibleClient' object has no attribute 'chat']``。

本模块把"要一整段结果"的调用统一收口到公开接口上。

为什么不复用 ``core/stream.py::stream_cnt``
--------------------------------------------
``stream_cnt`` 是**终端流式渲染**的漏斗：失败时它把错误**渲染成一段文本**
返回（``"[错误] ..."``），而不是抛异常或返回 ``None``。调用方若要区分
"模型回答"与"错误提示"，只能去嗅探文本前缀 —— 脆弱且会漏。

``complete_text`` 因此自己走 ``stream_chat``：成功返回正文，失败返回
``(None, 真实原因)``，调用方不必猜。同时保留 v2.8.7 的三项能力：

* **重试**：瞬时错误（网络抖动 / 超时 / 限流 / 5xx）指数退避重试
* **降级**：主模型彻底失败时切到备用 provider 再试一次
* **思考-答案分离**：``reasoning`` 分片不进正文；正文为空时回退到思考内容
  （与 ``core/stream.py`` 同一口径，避免"答非所问"）
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

#: 默认单次生成上限（token）
DEFAULT_MAX_TOKENS = 4096

#: **强**思考特征：谈论"该怎么回答"的元指令 —— 正常答案里几乎不会出现。
#: 命中即判定该句是思考残留。
_STRONG_THINKING_MARKERS = (
    "need not mention", "don't mention", "do not mention",
    "the user asks", "the user wants", "the user is asking",
    "need output", "need to output", "need cover", "need to cover",
    "need include", "need to include", "need thorough", "need be thorough",
    "final answer in", "answer in chinese", "answer in english",
    "we need answer", "need to answer the", "must answer",
)

#: **弱**思考特征：单个出现不足以判定，需命中 ≥2 个。
_WEAK_THINKING_MARKERS = (
    "we need", "we should", "we must", "we have to",
    "need to", "need for", "let's", "let me",
    "i need to", "i should", "i will",
    "now, ", "okay,", "first,", "second,", "third,",
    "to answer", "to respond", "to provide", "to complete",
    "the task is", "the request is", "here is", "here's",
    "my plan",
)

#: 开头思考残留段落的最小长度（太短不剥离，避免误伤）
_MIN_LEAK_LEN = 40

#: 中文字符判定（用于划定"开头纯 ASCII 段"）
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

#: 句子切分（保留句末标点与换行；英文句点后跟空白也算断句）
_SENT_SPLIT_RE = re.compile(
    r"[^。！？!?\n]+?(?:[。！？!?\n]|\.(?=\s))|[^。！？!?\n]+$"
)

#: 中文回答场景的中文字符数下限 —— 低于此值视为"纯英文场景"，不做剥离
_MIN_CJK_CHARS = 20


def _is_strong_thinking(sentence: str) -> bool:
    """是否命中强思考特征（谈论"该怎么回答"的元指令）。"""
    low = sentence.lower()
    return any(m in low for m in _STRONG_THINKING_MARKERS)


def strip_thinking_leak(text: str) -> str:
    """剥离混入正文的模型思考段落（provider 偶发把 thinking 写进 content）。

    背景：推理模型（stepfun step-5 等）在思考较长时会把思考过程下发到
    ``delta.content``。``core/llm/base.py`` 按"同包时以 content 为准"的规则
    取 content —— 于是这段思考被当成正文，进入最终答案（实测：聚合答案
    开头出现 ``We need answer user. They gave previous member outputs? ...
    Need not mention agents/team/summary.``，之后才是真正的中文正文）。

    这里做一个**保守**的启发式修复（逐句删除 + 思考模式）：

    * 只在**中文回答**场景启用（全文中文字符数 ≥ ``_MIN_CJK_CHARS``），
      纯英文回答完全不动（英文里 "We need to ..." 是正常表达）；
    * 逐句扫描：某句命中强特征（元指令）即**进入思考模式**并删除该句；
    * 思考模式内：不含中文的句子一并删除（都是思考碎片）；含中文但仍命中
      强特征的也删除（``Need cover task: 分别为智能手机…``）；
      遇到 markdown 标题或普通中文句子则退出思考模式；
    * 删除后若正文被清空，则**整段退回原文** —— 宁可残留也不给空答案。

    诚实边界：这是**启发式**，不是协议层分离 —— provider 把 thinking 塞进
    content 时没有任何标记可依。只有**开头**连续的思考会被剥离；夹在答案
    中间的思考残留抓不到。宁可偶尔残留，也不误伤正常答案。
    """
    if not text:
        return text
    # 纯英文场景不做剥离
    if len(_CJK_RE.findall(text)) < _MIN_CJK_CHARS:
        return text

    spans = [
        m.span() for m in _SENT_SPLIT_RE.finditer(text) if m.group().strip()
    ]
    if not spans:
        return text

    kill: List[Tuple[int, int]] = []
    in_thinking = False
    finished = False          # 第一段思考结束后，后面一律不动
    is_first = True           # 思考模式只允许由**第一句**触发
    for start, end in spans:
        sentence = text[start:end]
        strong = _is_strong_thinking(sentence)
        if finished:
            continue
        if not in_thinking:
            # 只有**强特征**能触发思考模式（弱特征太容易误伤正常英文），
            # 且只能由第一句触发 —— 正文中间出现的 "Need include ..." 是
            # 正常内容，不能删
            if is_first and strong:
                in_thinking = True
                kill.append((start, end))
            is_first = False
            continue
        # 已在思考模式
        if sentence.lstrip().startswith("#"):
            in_thinking = False          # markdown 标题 → 答案开始
            finished = True
        elif strong or not _CJK_RE.search(sentence):
            kill.append((start, end))    # 元指令句 / 英文碎片 → 都是思考
        else:
            in_thinking = False          # 普通中文句子 → 答案开始
            finished = True
    if not kill:
        return text

    pieces: List[str] = []
    prev = 0
    for start, end in kill:
        if start > prev:
            pieces.append(text[prev:start])
        prev = end
    pieces.append(text[prev:])
    result = re.sub(r"\n{3,}", "\n\n", "".join(pieces)).strip()
    return result if result else text


def _key_ok(client: Any) -> bool:
    """API Key 是否可用（Mock 客户端允许空 key）。"""
    from fr_cli.core.llm import MockLLMClient

    if isinstance(client, MockLLMClient):
        return True
    key = getattr(client, "api_key", "") or ""
    return len(key) >= 10


def _run_once(client: Any, model: str, messages: List[Dict[str, Any]],
              max_tokens: int, timeout: Optional[int]) -> Tuple[str, Dict[str, Any]]:
    """跑一次流式调用，把正文攒成一整段返回，同时带回 usage。"""
    text = ""
    reasoning_text = ""
    usage: Dict[str, Any] = {}
    response = client.stream_chat(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        timeout=timeout,
    )
    for chunk in response:
        ctext = chunk.get("content", "")
        if ctext:
            # 推理模型的思考内容单独收集，不混进正文
            if chunk.get("reasoning"):
                reasoning_text += ctext
            else:
                text += ctext
        if chunk.get("usage"):
            usage = chunk["usage"]
    if not text and reasoning_text:
        # 兜底：部分 provider（火山方舟 coding endpoint 等）只把答案放在
        # reasoning_content 里 —— 此时把思考内容当作答案，避免「答非所问」
        text = reasoning_text
    return text, usage


def complete_text_ex(
    client: Any,
    model: Optional[str],
    messages: List[Dict[str, Any]],
    lang: str = "zh",
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout: Optional[int] = None,
    fallback: Any = None,
    provider: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
    """同 :func:`complete_text`，但**额外返回 usage**（token 统计）。

    Agent Team 一轮要调多次模型（拆解 + N 个成员 + 聚合），需要把用量加总，
    因此这里保留 usage 而不是丢掉。

    Returns:
        ``(text, error, usage)`` —— 成功时 error 为 None；失败时 text 为 None。
    """
    if not client or not model:
        return None, "模型未配置", {}
    if not _key_ok(client):
        return None, "API 密钥未配置或格式不正确", {}

    from fr_cli.core.llm.resilience import (
        DEFAULT_BACKOFF,
        DEFAULT_RETRY,
        call_with_retry,
        describe_error,
        is_transient,
        resolve_fallback,
    )

    attempts = max(1, int(DEFAULT_RETRY) + 1)

    def _attempt(c, m):
        return _run_once(c, m, messages, max_tokens, timeout)

    text = ""
    usage: Dict[str, Any] = {}
    try:
        text, usage = call_with_retry(
            lambda _n: _attempt(client, model),
            attempts=attempts,
            backoff=DEFAULT_BACKOFF,
            should_retry=is_transient,
        )
    except Exception as e:
        # 降级：主模型彻底失败 → 换备用 provider 再试一次
        fb = resolve_fallback(fallback)
        if fb is None:
            return None, describe_error(e), usage
        fb_client, fb_model = fb
        try:
            text, usage = call_with_retry(
                lambda _n: _attempt(fb_client, fb_model),
                attempts=attempts,
                backoff=DEFAULT_BACKOFF,
                should_retry=is_transient,
            )
        except Exception as e2:
            return None, describe_error(e2), usage

    if not text or not text.strip():
        return None, "模型返回空内容", usage
    # 剥离开头偶发混入的思考段落（provider 把 thinking 写进 content 时的兜底）
    return strip_thinking_leak(text), None, usage


def complete_text(
    client: Any,
    model: Optional[str],
    messages: List[Dict[str, Any]],
    lang: str = "zh",
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout: Optional[int] = None,
    fallback: Any = None,
    provider: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """静默完成一次 LLM 调用。

    与 :func:`fr_cli.core.stream.stream_cnt` 的区别：**不流式、不打印**，
    且**失败返回 ``(None, 原因)``** 而不是把错误渲染成文本。

    Args:
        client: LLM 客户端实例（``BaseLLMClient`` 子类）
        model: 模型名
        messages: 消息列表
        lang: 语言（仅用于事件标注，当前无副作用）
        max_tokens: 单次生成上限
        timeout: 单次请求超时秒数；None → 用客户端默认
        fallback: 降级来源 —— (client, model) 元组或返回它的可调用对象
        provider: 提供商名（仅用于事件上报）

    Returns:
        ``(text, error)`` —— 成功时 error 为 None；失败时 text 为 None。
    """
    text, err, _usage = complete_text_ex(
        client, model, messages,
        lang=lang, max_tokens=max_tokens, timeout=timeout,
        fallback=fallback, provider=provider,
    )
    return text, err
