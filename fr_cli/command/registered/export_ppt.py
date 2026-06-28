"""
会话导出工具:
- export_session_ppt: 导出单个会话为 PPTX / Markdown
- list_exportable_sessions: 列出可导出的会话
"""
from fr_cli.command.registry import register
from fr_cli.core.result import Result
from fr_cli.weapon.session_to_ppt import (
    export_session_to_ppt,
)
from fr_cli.memory.session import list_sessions as _list_sessions


@register(
    name="export_session_ppt",
    triggers=["导出PPT", "export PPT", "export pptx", "转PPT"],
    description="导出会话为 PPTX(python-pptx)或 Markdown 大纲(fallback)",
    params={"session_path": str, "output_path": str, "format": str,
            "title": str, "max_slides": int},
    aliases=["/export_ppt", "/session_ppt"],
)
def _register_export_ppt(deps, **kwargs):
    session_path = kwargs.get("session_path") or None
    output_path = kwargs.get("output_path") or None
    fmt = kwargs.get("format") or "auto"
    title = kwargs.get("title") or None
    max_slides = int(kwargs.get("max_slides", 50))

    # 提示:未指定路径时列出可用会话
    if not session_path:
        sessions = _list_sessions()[:5]  # 最近 5 个
        if not sessions:
            return Result.fail("未找到任何会话。请先使用 fr-cli 进行对话。")
        lines = ["请提供 session_path。可用的最近会话:"]
        for s in sessions:
            lines.append(f"  {s['index']}. {s['filename']} ({s['msg_count']} 条,{s['updated_at']})")
        return Result.ok("\n".join(lines) + "\n\n用法: /export_ppt 1 [output_path]")

    # 如果传入数字索引
    if session_path.isdigit():
        idx = int(session_path)
        sessions = _list_sessions()
        if idx < 1 or idx > len(sessions):
            return Result.fail(f"索引超出范围: 1-{len(sessions)}")
        session_path = sessions[idx - 1]["path"]

    result = export_session_to_ppt(
        session_path=session_path,
        output_path=output_path,
        format=fmt,
        title=title,
        max_slides=max_slides,
    )
    if not result["ok"]:
        return Result.fail(result.get("error", "导出失败"))

    pptx_error = result.get("pptx_error")
    extra = ""
    if pptx_error:
        extra = f"\n\n⚠️ PPTX 生成失败,已回退到 Markdown: {pptx_error}"
    return Result.ok(
        f"✅ 会话导出成功\n"
        f"  格式: {result.get('format', '?')}\n"
        f"  路径: {result['path']}\n"
        f"  幻灯片: {result.get('slides', 0)} 张{extra}"
    )


@register(
    name="list_exportable_sessions",
    triggers=["可导出会话", "exportable sessions"],
    description="列出可导出为 PPT 的会话",
    params={"limit": int},
    aliases=["/export_list"],
)
def _register_list_exportable(deps, **kwargs):
    limit = int(kwargs.get("limit", 10))
    sessions = _list_sessions()[:limit]
    if not sessions:
        return Result.ok("未找到任何会话")

    lines = [f"📂 最近 {len(sessions)} 个可导出会话:"]
    for s in sessions:
        lines.append(f"  {s['index']}. {s['filename']}")
        lines.append(f"     {s['updated_at']} | {s['msg_count']} 条消息")
    lines.append("")
    lines.append("用法: /export_ppt <索引> [输出路径]")
    return Result.ok("\n".join(lines))
