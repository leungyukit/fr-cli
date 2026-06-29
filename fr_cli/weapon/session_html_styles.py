"""
session_html_styles.py —— 时间线 HTML 的 CSS 样式

_TICKLINE_CSS:完整的暗色主题 CSS,内嵌到 HTML <style> 标签中
ROLE_ICONS / ROLE_LABELS:role → 图标 / 标签映射
"""
from __future__ import annotations


_TIMELINE_CSS = """
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
"""


ROLE_ICONS = {"user": "👤", "assistant": "🤖", "system": "⚙️"}
ROLE_LABELS = {"user": "用户", "assistant": "AI", "system": "系统"}
