"""
对话上下文压缩

在长会话中，对较早的用户/助手轮次进行 LLM 摘要，减少 prompt token 消耗。
完整历史仍保留在 state.messages 中，仅发送给 LLM 的消息列表被压缩。
"""
from typing import Dict, List, Optional

from fr_cli.core.stream import stream_cnt


SUMMARY_PROMPT_ZH = """请将以下历史对话压缩成一段摘要，保留关键事实、用户意图和已完成的动作；忽略寒暄与重复内容。不超过 300 字。

历史对话：
{history}

请直接输出摘要，不要加标题。"""


SUMMARY_PROMPT_EN = """Please compress the following conversation history into a concise summary. Keep key facts, user intent, and completed actions; omit greetings and repetition. Limit to 300 words.

History:
{history}

Output the summary directly, without a title."""


def _message_content_str(msg: Dict) -> str:
    """将消息内容转为字符串（支持多模态列表的简单表示）。"""
    content = msg.get("content", "")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                t = item.get("type", "")
                if t == "text":
                    parts.append(item.get("text", ""))
                elif t == "image_url":
                    parts.append("[图片]")
                else:
                    parts.append(str(item))
            else:
                parts.append(str(item))
        return " ".join(parts)
    return str(content)


def estimate_tokens(messages: List[Dict], overhead: int = 4) -> int:
    """启发式估算消息列表的 token 数（字符数/4 + 每条开销）。"""
    total = 0
    for msg in messages:
        text = _message_content_str(msg)
        total += max(1, len(text) // 4) + overhead
    return total


def _format_history(messages: List[Dict]) -> str:
    """将用户/助手轮次格式化为用于摘要的文本。"""
    lines = []
    for msg in messages:
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        label = "用户" if role == "user" else "AI"
        text = _message_content_str(msg)
        if text:
            lines.append(f"{label}: {text[:800]}")
    return "\n".join(lines)


def compress_messages(
    messages: List[Dict],
    client,
    model_name: str,
    lang: str = "zh",
    keep_recent: int = 5,
    max_summary_tokens: int = 512,
) -> List[Dict]:
    """
    对消息列表进行摘要压缩。

    - 保留 system 提示词（第一条 system 消息）。
    - 保留最近 keep_recent 轮（每轮 = user + assistant）对话。
    - 将更早的 user/assistant 轮次合并为一条 [历史摘要] system 消息。

    返回新的消息列表（不修改原列表）。
    """
    if len(messages) <= 1:
        return list(messages)

    system_msgs = [m for m in messages if m.get("role") == "system"]
    chat_msgs = [m for m in messages if m.get("role") in ("user", "assistant")]

    keep_chat = keep_recent * 2
    if len(chat_msgs) <= keep_chat:
        return list(messages)

    old = chat_msgs[:-keep_chat]
    recent = chat_msgs[-keep_chat:]

    history_text = _format_history(old)
    if not history_text.strip():
        return list(messages)

    prompt_template = SUMMARY_PROMPT_ZH if lang == "zh" else SUMMARY_PROMPT_EN
    prompt = prompt_template.format(history=history_text)

    try:
        summary, _, _, _ = stream_cnt(
            client, model_name,
            [{"role": "user", "content": prompt}],
            lang,
            custom_prefix="",
            max_tokens=max_summary_tokens,
            silent=True,
        )
        summary = summary.strip()
    except Exception:
        summary = ""

    if not summary:
        # 摘要失败时退化为简单截断（保留最近轮次）
        return system_msgs + recent

    result = []
    if system_msgs:
        # 保留第一条系统提示，避免摘要冲淡核心人设
        result.append(system_msgs[0])
    result.append({"role": "system", "content": f"[历史摘要]\n{summary}"})
    # 保留其余系统消息（如近期记忆、失败提示等）
    result.extend(system_msgs[1:])
    result.extend(recent)
    return result


def maybe_compress(
    messages: List[Dict],
    client,
    model_name: Optional[str],
    lang: str = "zh",
    threshold: int = 8000,
    keep_recent: int = 5,
) -> tuple[List[Dict], bool, int, int]:
    """
    如果估算 token 超过阈值，则压缩早期对话。

    返回：(messages_or_compressed, did_compress, before_tokens, after_tokens)
    """
    before = estimate_tokens(messages)
    if threshold <= 0 or before <= threshold:
        return list(messages), False, before, before

    if not model_name:
        return list(messages), False, before, before

    compressed = compress_messages(
        messages, client, model_name, lang=lang, keep_recent=keep_recent
    )
    after = estimate_tokens(compressed)
    return compressed, True, before, after
