"""
会话时间线 HTML 可视化 —— 把会话转成可在浏览器看的 timeline

策略:
- 读取会话消息
- 生成自包含 HTML(无需额外 CSS/JS,内嵌到 <style>/<script>)
- 消息按时间顺序排列
- 区分 user / assistant / system / tool
- 工具调用高亮(检测【调用：...】标记)
- 关键事件:代码块、命令、错误等
- 支持折叠/展开详情
- 一键在浏览器打开(file:// URL + os.system("open ..."))

设计:
- 暗色主题(fr-cli 风格)
- 时间戳左侧 + 内容右侧布局
- 头像 + 角色名
- 工具调用折叠面板
"""
import html
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from fr_cli.weapon.session_to_ppt import (
    load_session_messages,
)
from fr_cli.conf.paths import ROOT as FR_CLI_DIR


def _escape(text: str) -> str:
    """HTML 转义"""
    return html.escape(str(text or ""))


def _render_inline_md(text: str) -> str:
    """极简 Markdown → HTML(只处理粗体 / 行内代码 / 链接 / 标题)"""
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


def _extract_tool_calls(text: str) -> List[Dict[str, str]]:
    """提取【调用：tool_name({...})】标记"""
    calls = []
    for m in re.finditer(r'【调用：(\w+)\((.*?)\)】', text, re.DOTALL):
        calls.append({
            "tool": m.group(1),
            "args": m.group(2)[:200] + ("..." if len(m.group(2)) > 200 else ""),
        })
    return calls


def generate_timeline_html(messages: List[Dict[str, Any]],
                            title: str = "会话时间线",
                            session_filename: str = "") -> str:
    """生成时间线 HTML

    Args:
        messages: 会话消息列表
        title: 页面标题
        session_filename: 会话文件名

    Returns:
        完整的 HTML 字符串
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(messages)
    user_count = sum(1 for m in messages if m.get("role") == "user")
    ai_count = sum(1 for m in messages if m.get("role") == "assistant")

    html_parts = ["""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>""", _escape(title), """</title>
<style>
:root {
  --bg-primary: #0d1117;
  --bg-secondary: #161b22;
  --bg-tertiary: #1c2128;
  --border: #30363d;
  --text-primary: #c9d1d9;
  --text-secondary: #8b949e;
  --accent: #58a6ff;
  --user-color: #3fb950;
  --ai-color: #58a6ff;
  --system-color: #8b949e;
  --tool-color: #d29922;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg-primary);
  color: var(--text-primary);
  font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
  font-size: 14px;
  line-height: 1.6;
  padding: 24px;
  max-width: 900px;
  margin: 0 auto;
}
header {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 24px;
}
header h1 {
  font-size: 24px;
  color: var(--accent);
  margin-bottom: 8px;
}
header .stats {
  display: flex;
  gap: 20px;
  margin-top: 12px;
  font-size: 13px;
  color: var(--text-secondary);
}
header .stats span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}
.dot.user { background: var(--user-color); }
.dot.ai { background: var(--ai-color); }
.timeline { position: relative; padding-left: 32px; }
.timeline::before {
  content: "";
  position: absolute;
  left: 11px;
  top: 0;
  bottom: 0;
  width: 2px;
  background: var(--border);
}
.message {
  position: relative;
  margin-bottom: 20px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
}
.message::before {
  content: "";
  position: absolute;
  left: -25px;
  top: 20px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--bg-primary);
  border: 2px solid var(--border);
}
.message.user::before { border-color: var(--user-color); }
.message.assistant::before { border-color: var(--ai-color); }
.message.system::before { border-color: var(--system-color); }
.message .role {
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 8px;
}
.message.user .role { color: var(--user-color); }
.message.assistant .role { color: var(--ai-color); }
.message.system .role { color: var(--system-color); }
.message .content {
  white-space: pre-wrap;
  word-wrap: break-word;
}
.text-line {
  padding: 2px 0;
}
.code-block {
  background: var(--bg-primary);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 12px;
  margin: 8px 0;
  overflow-x: auto;
  font-family: "SF Mono", "Monaco", monospace;
  font-size: 13px;
}
.inline-code {
  background: var(--bg-tertiary);
  padding: 2px 6px;
  border-radius: 3px;
  font-family: "SF Mono", "Monaco", monospace;
  font-size: 13px;
  color: var(--tool-color);
}
.tool-calls {
  margin-top: 12px;
  padding: 12px;
  background: var(--bg-tertiary);
  border-left: 3px solid var(--tool-color);
  border-radius: 4px;
}
.tool-call {
  margin-bottom: 8px;
}
.tool-call .name {
  color: var(--tool-color);
  font-weight: 600;
  font-family: "SF Mono", monospace;
}
.tool-call .args {
  margin-top: 4px;
  font-family: "SF Mono", monospace;
  font-size: 12px;
  color: var(--text-secondary);
}
details {
  margin-top: 8px;
  cursor: pointer;
}
details summary {
  color: var(--text-secondary);
  font-size: 12px;
}
.message.system {
  background: var(--bg-tertiary);
  font-style: italic;
}
footer {
  margin-top: 32px;
  padding: 16px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 12px;
}
</style>
</head>
<body>
<header>
  <h1>📜 """, _escape(title), """</h1>
  <div style="color: var(--text-secondary); font-size: 13px;">""",
    _escape(session_filename) if session_filename else "", """</div>
  <div class="stats">
    <span><span class="dot user"></span> 用户: """, str(user_count), """</span>
    <span><span class="dot ai"></span> AI: """, str(ai_count), """</span>
    <span>总计: """, str(total), """ 条</span>
    <span>生成于: """, _escape(now), """</span>
  </div>
</header>
<div class="timeline">
"""]

    # 渲染消息
    role_icons = {"user": "👤", "assistant": "🤖", "system": "⚙️"}
    role_labels = {"user": "用户", "assistant": "AI", "system": "系统"}

    for i, msg in enumerate(messages):
        role = msg.get("role", "user")
        content = msg.get("content", "")
        tool_calls = _extract_tool_calls(content) if role == "assistant" else []

        icon = role_icons.get(role, "?")
        label = role_labels.get(role, role)

        html_parts.append(f'<div class="message {role}">\n')
        html_parts.append(f'  <div class="role">{icon} {label}</div>\n')
        html_parts.append('  <div class="content">\n')
        html_parts.append(f'    {_render_content(content)}\n')
        html_parts.append('  </div>\n')

        if tool_calls:
            html_parts.append('  <div class="tool-calls">\n')
            html_parts.append('    <strong>🔧 工具调用</strong>\n')
            for tc in tool_calls:
                html_parts.append(
                    f'    <div class="tool-call">\n'
                    f'      <span class="name">{_escape(tc["tool"])}</span>\n'
                    f'      <details><summary>参数</summary>\n'
                    f'        <div class="args">{_escape(tc["args"])}</div>\n'
                    f'      </details>\n'
                    f'    </div>\n'
                )
            html_parts.append('  </div>\n')

        html_parts.append('</div>\n')

    html_parts.append(f"""</div>
<footer>
  Generated by fr-cli • {_escape(now)}
</footer>
</body>
</html>""")

    return "".join(html_parts)


def export_session_to_html(session_path: str, output_path: Optional[str] = None,
                            title: Optional[str] = None,
                            auto_open: bool = False) -> Dict[str, Any]:
    """导出会话为 HTML 时间线

    Args:
        session_path: 会话文件路径
        output_path: 输出路径
        title: 标题
        auto_open: 是否自动用浏览器打开

    Returns:
        {"ok": bool, "path": str, "title": str, "error": str?}
    """
    messages = load_session_messages(session_path)
    if not messages:
        return {"ok": False, "error": f"无法读取会话: {session_path}"}

    # 默认输出路径
    if not output_path:
        export_dir = FR_CLI_DIR / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = str(export_dir / f"session_{ts}.html")

    # 默认 title 用第一条 user
    if not title:
        for m in messages:
            if m.get("role") == "user":
                first_user = m.get("content", "会话")[:50]
                title = first_user + ("..." if len(first_user) == 50 else "")
                break
        else:
            title = "会话时间线"

    session_filename = os.path.basename(session_path)
    html_content = generate_timeline_html(messages, title=title,
                                          session_filename=session_filename)

    try:
        Path(output_path).write_text(html_content, encoding="utf-8")
    except Exception as e:
        return {"ok": False, "error": f"写入失败: {e}"}

    # 自动打开
    if auto_open:
        try:
            import subprocess
            import platform
            if platform.system() == "Darwin":
                subprocess.run(["open", output_path], check=False)
            elif platform.system() == "Linux":
                subprocess.run(["xdg-open", output_path], check=False)
            elif platform.system() == "Windows":
                os.startfile(output_path)  # type: ignore
        except Exception:
            pass  # 自动打开失败不影响主流程

    return {
        "ok": True,
        "path": output_path,
        "title": title,
        "messages": len(messages),
        "auto_opened": auto_open,
    }
