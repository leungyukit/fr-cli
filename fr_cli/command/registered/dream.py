"""
注册表分组:梦境整理命令（dream）

(从 services.py 按功能拆分,registry 目录扫描自动加载)
"""
from fr_cli.command.registry import register
from fr_cli.core.result import Result


# ============== 梦境整理（Dream） ==============

@register(
    name="dream",
    description="手动触发 MasterAgent 梦境整理（提炼长期记忆）",
    params={"action": str},
    aliases=["/dream"],
)
def _dream(deps, **kwargs):
    """手动触发梦境整理。

    子命令：
      /dream            立即整理一次
      /dream search <关键词>  搜索长期记忆
      /dream status     显示梦境统计
    """
    from fr_cli.agent.dream import (
        DreamEngine, get_dream_summary,
    )

    action = (kwargs.get("action") or "").strip()
    engine = DreamEngine(client=deps.client, model_name=deps.model_name, lang=deps.lang)

    if action == "search":
        # /dream search <query>
        return Result.ok("用法: /dream search <关键词>")
    if action == "status":
        s = get_dream_summary()
        msg = "🌙 梦境档案\n"
        msg += f"  总次数: {s['total_dreams']}\n"
        msg += f"  最近: {s['last_dream'] or '从未'}\n"
        if s["top_themes"]:
            msg += "  热门主题:\n"
            for t in s["top_themes"]:
                msg += f"    - {t['name']}: {t['count']} 次\n"
        return Result.ok(msg)

    # 立即整理一次
    try:
        result = engine.dream_now()
    except Exception as e:
        return Result.fail(f"梦境整理失败: {e}")
    if result.get("skipped"):
        return Result.ok(f"⏭ 跳过梦境整理: {result.get('reason', '?')}")
    data = result.get("data", {})
    summary = data.get("summary", "")
    themes = data.get("themes", [])
    msg = f"🌙 梦境整理完成 ({result.get('saved_at', '?')[:16]})\n"
    if summary:
        msg += f"  摘要: {summary}\n"
    if themes:
        msg += "  提炼主题:\n"
        for t in themes:
            if isinstance(t, dict):
                msg += f"    - {t.get('name', '?')} ({t.get('frequency', '?')}): {t.get('description', '')}\n"
    msg += "  档案已写入 ~/.fr_cli/master/dream_log.md"
    return Result.ok(msg)
