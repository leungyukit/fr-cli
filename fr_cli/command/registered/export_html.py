"""
会话导出 HTML 工具:
- export_session_html: 把会话转成可视化 HTML 时间线
"""
from fr_cli.command.registry import register
from fr_cli.core.result import Result


@register(
    name="export_session_html",
    triggers=["导出HTML", "export HTML", "时间线", "timeline"],
    description="导出会话为可视化 HTML 时间线(暗色主题,自动浏览器打开)",
    params={"session_path": str, "output_path": str, "title": str, "open": bool},
    aliases=["/export_html", "/timeline"],
)
def _register_export_html(deps, **kwargs):
    session_path = kwargs.get("session_path") or None
    output_path = kwargs.get("output_path") or None
    title = kwargs.get("title") or None
    auto_open = bool(kwargs.get("open", True))

    if not session_path:
        from fr_cli.memory.session import list_sessions
        sessions = list_sessions()[:5]
        if not sessions:
            return Result.fail("未找到任何会话")
        lines = ["请提供 session_path。 最近 5 个会话:"]
        for s in sessions:
            lines.append(f"  {s['index']}. {s['filename']} ({s['msg_count']} 条)")
        lines.append("\n用法: /export_html 1 [output_path]")
        return Result.ok("\n".join(lines))

    if session_path.isdigit():
        from fr_cli.memory.session import list_sessions
        idx = int(session_path)
        sessions = list_sessions()
        if idx < 1 or idx > len(sessions):
            return Result.fail(f"索引超出范围: 1-{len(sessions)}")
        session_path = sessions[idx - 1]["path"]

    from fr_cli.weapon.session_html import export_session_to_html
    result = export_session_to_html(
        session_path=session_path,
        output_path=output_path,
        title=title,
        auto_open=auto_open,
    )
    if not result["ok"]:
        return Result.fail(result.get("error", "导出失败"))

    extra = "\n🌐 已在浏览器打开" if result.get("auto_opened") else ""
    return Result.ok(
        f"✅ HTML 时间线已生成:\n"
        f"  标题: {result['title']}\n"
        f"  路径: {result['path']}\n"
        f"  消息: {result['messages']} 条{extra}"
    )
