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

from typing import Any, Dict, List, Optional, Tuple

#: 默认单次生成上限（token）
DEFAULT_MAX_TOKENS = 4096


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
    return text, None, usage


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
