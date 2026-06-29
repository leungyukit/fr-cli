"""
session_html_md.py —— 极简 Markdown → HTML 渲染

- _escape           HTML 转义
- _render_inline_md 处理行内格式(粗体/行内代码/链接)
- _render_content   处理完整消息内容(代码块 + 行内)
"""
from __future__ import annotations

import html
import re


def _escape(text: str) -> str:
    """HTML 转义"""
    return html.escape(str(text or ""))


def _render_inline_md(text: str) -> str:
    """极简 Markdown → HTML(只处理粗体 / 行内代码 / 链接)"""
    text = _escape(text)
    # 行内代码
    text = re.sub(
        r"`([^`]+)`",
        r'<code class="inline-code">\1</code>',
        text,
    )
    # 粗体
    text = re.sub(
        r"\*\*([^*]+)\*\*",
        r"<strong>\1</strong>",
        text,
    )
    # 链接
    text = re.sub(
        r'\[([^\]]+)\]\(([^)]+)\)',
        r'<a href="\2" target="_blank">\1</a>',
        text,
    )
    return text


def _render_content(text: str) -> str:
    """渲染消息内容(代码块、行内格式等)"""
    if not text:
        return ""

    parts = []
    lines = text.split("\n")
    in_code = False
    code_buffer = []
    code_lang = ""

    for line in lines:
        if line.strip().startswith("```"):
            if in_code:
                # 结束代码块
                lang = code_lang or "code"
                parts.append(
                    f'<pre class="code-block"><code class="lang-{lang}">'
                    f'{_escape(chr(10).join(code_buffer))}</code></pre>'
                )
                code_buffer = []
                code_lang = ""
                in_code = False
            else:
                # 开始代码块
                in_code = True
                code_lang = line.strip()[3:].strip()
            continue

        if in_code:
            code_buffer.append(line)
        else:
            parts.append(f'<div class="text-line">{_render_inline_md(line)}</div>')

    if in_code:
        # 没闭合的代码块
        parts.append(
            f'<pre class="code-block"><code class="lang-{code_lang or "code"}">'
            f'{_escape(chr(10).join(code_buffer))}</code></pre>'
        )

    return "\n".join(parts)
