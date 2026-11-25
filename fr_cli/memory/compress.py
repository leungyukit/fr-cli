"""
对话上下文压缩

在长会话中，对较早的用户/助手轮次进行 LLM 摘要，减少 prompt token 消耗。
完整历史仍保留在 state.messages 中，仅发送给 LLM 的消息列表被压缩。
"""
import re
from typing import Dict, List, Optional

from fr_cli.core.stream import stream_cnt


# ------------------------------------------------------------------
# Token 估算（混合感知：CJK 与西文分别计权）
# ------------------------------------------------------------------
#
# 旧实现用 `len(text) // 4` 估算，这是**英文**的经验值（约 4 字符/token）。
# 中文实际约 1.5 字/token（1 字 ≈ 0.67 token），沿用 //4 会低估 2.7~4 倍，
# 导致上下文压缩触发点远晚于模型真实上限 → 413 / context 超限。
#
# 现改为混合感知估算：
#   - CJK 字符：CJK_TOKEN_RATIO（≈0.65 token/字）
#   - 其余字符：OTHER_TOKEN_RATIO（≈0.25 token/字符，即 4 字符/token）
#   - 整体再乘安全系数 TOKEN_SAFETY_FACTOR（宁可高估不可低估）

# CJK 字符正则：一次扫描完成统计，避免逐字符遍历（性能）
#   U+4E00–U+9FFF  中日韩统一表意文字
#   U+3400–U+4DBF  中日韩统一表意文字扩展 A
#   U+3000–U+303F  中日韩符号和标点
#   U+FF00–U+FFEF  全角字符
#   U+3040–U+30FF  假名
#   U+AC00–U+D7AF  韩文音节
_CJK_RE = re.compile(
    "["
    "\u4e00-\u9fff"
    "\u3400-\u4dbf"
    "\u3000-\u303f"
    "\uff00-\uffef"
    "\u3040-\u30ff"
    "\uac00-\ud7af"
    "]"
)

# 单个 CJK 字约 0.6~0.7 token
CJK_TOKEN_RATIO = 0.65
# 西文 / 数字 / 符号约 0.25 token/字符（英文约 4 字符/token）
OTHER_TOKEN_RATIO = 0.25
# 安全边际：宁可略微高估也不要低估 —— 提前触发压缩好过撞上模型上下文上限
TOKEN_SAFETY_FACTOR = 1.08


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


def _estimate_text_tokens(text: str) -> int:
    """估算单段文本的 token 数（混合感知 + 安全系数）。

    CJK 字符按 CJK_TOKEN_RATIO 计，其余字符按 OTHER_TOKEN_RATIO 计，
    合计后再乘 TOKEN_SAFETY_FACTOR 取整（向下取整与旧实现语义一致）。
    """
    if not text:
        return 0
    cjk_count = len(_CJK_RE.findall(text))
    other_count = len(text) - cjk_count
    raw = cjk_count * CJK_TOKEN_RATIO + other_count * OTHER_TOKEN_RATIO
    return int(raw * TOKEN_SAFETY_FACTOR)


def estimate_tokens(messages: List[Dict], overhead: int = 4) -> int:
    """启发式估算消息列表的 token 数（混合感知 + 每条消息固定开销）。

    Args:
        messages: 消息列表（content 支持 str 或多模态 list）
        overhead: 每条消息的固定开销（角色/分隔符），语义与旧实现一致

    Returns:
        估算的 token 总数（int）。中文场景不再像旧实现那样低估 2.7~4 倍。
    """
    total = 0
    for msg in messages:
        text = _message_content_str(msg)
        total += max(1, _estimate_text_tokens(text)) + overhead
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


def _split_tiers(old: List[Dict], tiers: int) -> List[List[Dict]]:
    """把待压缩的早期轮次切成若干**连续**分段（分层压缩）。

    v2.8.7(P1-5)：旧实现把所有早期对话一次性合并成一段 300 字摘要 ——
    信息损失不可逆，且模型分不清"早期定了什么"和"中期改了什么"。

    分段规则：按时间顺序等分，每段至少 2 条消息；段数不超过 ``tiers``。
    段数不足（早期消息太少）时返回单段 —— 退化成旧行为。
    """
    if tiers <= 1 or len(old) < 4:
        return [old]

    count = min(tiers, len(old) // 2)
    if count <= 1:
        return [old]

    size = len(old) // count
    segments = []
    start = 0
    for i in range(count):
        end = len(old) if i == count - 1 else start + size
        segments.append(old[start:end])
        start = end
    return [seg for seg in segments if seg]


def _build_summary_prompt(template: str, history_text: str, label: str) -> str:
    """拼摘要 prompt —— 分层时带上「这是第几段」的提示。"""
    if label:
        return template.format(history=f"（{label}）\n{history_text}")
    return template.format(history=history_text)


def _summarize_segment(
    client, model_name: str, prompt_template: str, segment: List[Dict],
    label: str, lang: str, max_summary_tokens: int,
) -> str:
    """对一段历史做 LLM 摘要；失败返回空串。"""
    history_text = _format_history(segment)
    if not history_text.strip():
        return ""
    prompt = _build_summary_prompt(prompt_template, history_text, label)
    try:
        summary, _, _, _ = stream_cnt(
            client, model_name,
            [{"role": "user", "content": prompt}],
            lang,
            custom_prefix="",
            max_tokens=max_summary_tokens,
            silent=True,
        )
        return summary.strip()
    except Exception:
        return ""


def compress_messages(
    messages: List[Dict],
    client,
    model_name: str,
    lang: str = "zh",
    keep_recent: int = 5,
    max_summary_tokens: int = 512,
    tiers: int = 3,
) -> List[Dict]:
    """
    对消息列表进行摘要压缩。

    - 保留 system 提示词（第一条 system 消息）。
    - 保留最近 keep_recent 轮（每轮 = user + assistant）对话。
    - 将更早的 user/assistant 轮次切成最多 ``tiers`` 段**分层**摘要，
      每段一条 ``[历史摘要 i/N]`` system 消息，按时间顺序排列；
      每段标注它覆盖的对话序号区间，模型据此知道"这是哪一阶段的事"。

    v2.8.7(P1-5)：旧实现把早期对话一次性合并成一条摘要，信息不可逆丢失。
    分层后每个阶段保留自己的摘要，且段与段之间的边界仍然可见。

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

    if not _format_history(old).strip():
        return list(messages)

    prompt_template = SUMMARY_PROMPT_ZH if lang == "zh" else SUMMARY_PROMPT_EN
    segments = _split_tiers(old, tiers)

    # 先把每段的摘要结果收齐，再决定整体策略
    raw: List[tuple] = []
    offset = 0
    for idx, segment in enumerate(segments, start=1):
        start_msg = offset
        offset += len(segment)
        if len(segments) > 1:
            # 标注覆盖区间（消息序号从 1 开始）—— 模型据此知道"这是哪一阶段的事"
            label = (
                f"第 {idx}/{len(segments)} 段早期对话"
                f"（第 {start_msg + 1}~{offset} 条消息）"
            )
        else:
            label = ""
        summary = _summarize_segment(
            client, model_name, prompt_template, segment, label, lang, max_summary_tokens,
        )
        raw.append((idx, summary, segment))

    if not any(summary for _, summary, _ in raw):
        # 全部摘要失败（LLM 不可用）→ 退化为简单截断。
        # 不能改成"保留原文片段"—— 那比不压缩还大，压缩就白做了。
        return system_msgs + recent

    summaries: List[str] = []
    for idx, summary, segment in raw:
        if summary:
            summaries.append(
                f"[历史摘要 {idx}/{len(segments)}]\n{summary}"
                if len(segments) > 1 else f"[历史摘要]\n{summary}"
            )
        else:
            # 只有部分段失败 → 该段保留原文片段（比整段丢弃强）
            excerpt = _format_history(segment)[:600]
            if excerpt.strip():
                summaries.append(
                    f"[历史摘要 {idx}/{len(segments)} · 摘要失败，保留原文片段]\n{excerpt}"
                )

    result = []
    if system_msgs:
        # 保留第一条系统提示，避免摘要冲淡核心人设
        result.append(system_msgs[0])
    for item in summaries:
        result.append({"role": "system", "content": item})
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
    tiers: int = 3,
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
        messages, client, model_name, lang=lang, keep_recent=keep_recent, tiers=tiers
    )
    after = estimate_tokens(compressed)
    return compressed, True, before, after
