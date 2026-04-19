"""
记忆上下文引擎
保存并注入最近 N 轮对话的总结，作为 system prompt 的上下文
让每个会话拥有独立的短期记忆
"""
import json
import re
from pathlib import Path
from datetime import datetime

CONTEXT_FILE = Path.home() / ".zhipu_cli_context.json"


def extract_recent_turns(messages, n=5):
    """
    从消息列表中提取最近 n 轮 user/assistant 对话
    :param messages: 完整消息历史
    :param n: 轮数（每轮包含 user + assistant）
    :return: list of dict, 最多 n*2 条消息
    """
    chat_msgs = [m for m in messages if m.get("role") in ("user", "assistant")]
    return chat_msgs[-n * 2:]


def build_context_summary(turns, lang="zh"):
    """
    将对话轮次格式化为上下文摘要文本
    :param turns: extract_recent_turns 返回的消息列表
    :param lang: 语言
    :return: str 摘要文本（空字符串表示无内容）
    """
    if not turns:
        return ""

    header = "\n\n[当前会话上下文摘要]\n" if lang == "zh" else "\n\n[Session Context Summary]\n"
    lines = []

    for m in turns:
        role = "用户" if m.get("role") == "user" else "AI"
        content = m.get("content", "")

        # 处理多模态消息（图片等）
        if isinstance(content, list):
            content = "[图片/多模态消息]"
        elif isinstance(content, str):
            # 去除命令标记，避免重复噪音
            content = re.sub(r'【命令：(.*?)】', '', content)
            content = content.strip()
            if not content:
                content = "[已执行命令]"
            elif len(content) > 200:
                content = content[:200] + "..."

        lines.append(f"{role}：{content}")

    return header + "\n".join(lines) + "\n"


def save_context(session_name, summary):
    """
    按会话名持久化上下文摘要
    :param session_name: 会话名（空字符串时使用 __default__）
    :param summary: 摘要文本
    """
    data = {}
    if CONTEXT_FILE.exists():
        try:
            with open(CONTEXT_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            pass

    key = session_name if session_name else "__default__"
    data[key] = {
        "summary": summary,
        "ts": datetime.now().isoformat()
    }

    try:
        with open(CONTEXT_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_context(session_name):
    """
    按会话名加载上下文摘要
    :param session_name: 会话名
    :return: str 摘要文本（不存在时返回空字符串）
    """
    if not CONTEXT_FILE.exists():
        return ""
    try:
        with open(CONTEXT_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        key = session_name if session_name else "__default__"
        return data.get(key, {}).get("summary", "")
    except Exception:
        return ""


def clear_context(session_name):
    """
    清除指定会话的上下文摘要
    :param session_name: 会话名
    """
    if not CONTEXT_FILE.exists():
        return
    try:
        with open(CONTEXT_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        key = session_name if session_name else "__default__"
        if key in data:
            del data[key]
        with open(CONTEXT_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
