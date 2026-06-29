"""
会话时间线 HTML 可视化 —— 把会话转成可在浏览器看的 timeline

策略:
- 读取会话消息
- 生成自包含 HTML(无需额外 CSS/JS,内嵌到 <style>/<script>)
- 消息按时间顺序排列
- 区分 user / assistant / system / tool
- 工具调用高亮(检测【调用:...】标记)
- 关键事件:代码块、命令、错误等
- 支持折叠/展开详情
- 一键在浏览器打开(file:// URL + os.system("open ..."))

设计:
- 暗色主题(fr-cli 风格)
- 时间戳左侧 + 内容右侧布局
- 头像 + 角色名
- 工具调用折叠面板

模块拆分:
- fr_cli.weapon.session_html          本文件(入口 + 编排)
- fr_cli.weapon.session_html_md       极简 Markdown → HTML
- fr_cli.weapon.session_html_styles   CSS 常量 + role 映射
- fr_cli.weapon.session_html_render   HTML 片段渲染(head / messages / footer)
"""
from __future__ import annotations

import os
import platform
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fr_cli.weapon.session_html_render import (
    _extract_tool_calls,
    _render_timeline_footer,
    _render_timeline_head,
    _render_timeline_messages,
)
from fr_cli.weapon.session_html_md import (
    _render_content,
    _render_inline_md,
)
from fr_cli.weapon.session_to_ppt import load_session_messages
from fr_cli.conf.paths import ROOT as FR_CLI_DIR

__all__ = [
    "generate_timeline_html",
    "export_session_to_html",
    # 私有辅助(向后兼容 re-export)
    "_escape",
    "_render_content",
    "_render_inline_md",
    "_extract_tool_calls",
]


def _escape(text: str) -> str:
    """HTML 转义(向后兼容 shim)"""
    from fr_cli.weapon.session_html_md import _escape as _impl
    return _impl(text)


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

    head = _render_timeline_head(title, session_filename, now, total, user_count, ai_count)
    body = _render_timeline_messages(messages)
    footer = _render_timeline_footer(now)
    return head + body + footer


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
