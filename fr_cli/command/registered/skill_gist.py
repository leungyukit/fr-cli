"""
Skill 远程共享工具:
- skill_share: 分享本地 skill 到 Gist
- skill_import: 从 Gist URL/ID 导入 skill
- skill_browse: 浏览本地已分享的 skills
"""
from fr_cli.command.registry import register
from fr_cli.core.result import Result


@register(
    name="skill_share",
    triggers=["分享 skill", "share skill", "skill gist"],
    description="分享本地 skill 到 GitHub Gist(需 GITHUB_TOKEN)",
    params={"name": str, "description": str, "public": bool},
    aliases=["/skill_share"],
)
def _register_skill_share(deps, **kwargs):
    name = kwargs.get("name") or ""
    description = kwargs.get("description") or ""
    public = bool(kwargs.get("public", True))

    if not name:
        return Result.fail("需要提供 skill 名")

    from fr_cli.weapon.skill_gist import share_skill
    result = share_skill(name, description=description, public=public)
    if not result["ok"]:
        return Result.fail(result.get("error", "分享失败"))

    visibility = "公开" if public else "私密"
    return Result.ok(
        f"✅ Skill 分享成功 ({visibility}):\n"
        f"  名称: {result['name']}\n"
        f"  Gist ID: {result['gist_id']}\n"
        f"  URL: {result['url']}\n"
        f"\n📋 分享方式:把 URL 发给别人,他们用 /skill_import <URL> 导入"
    )


@register(
    name="skill_import",
    triggers=["导入 skill", "import skill"],
    description="从 GitHub Gist 导入 skill",
    params={"url": str, "name": str},
    aliases=["/skill_import"],
)
def _register_skill_import(deps, **kwargs):
    url = kwargs.get("url") or ""
    name = kwargs.get("name") or None

    if not url:
        return Result.fail("需要提供 Gist URL 或 ID")

    from fr_cli.weapon.skill_gist import import_skill
    result = import_skill(url, name=name)
    if not result["ok"]:
        return Result.fail(result.get("error", "导入失败"))

    return Result.ok(
        f"✅ Skill 导入成功:\n"
        f"  名称: {result['name']}\n"
        f"  路径: {result['path']}\n"
        f"  Gist: {result.get('url', '?')}\n"
        f"\n下一步: /skill {result['name']} 加载使用"
    )


@register(
    name="skill_browse_shared",
    triggers=["已分享 skill", "shared skills"],
    description="列出本地已分享过的 skills",
    params={},
    aliases=["/skill_shared"],
)
def _register_skill_browse(deps, **kwargs):
    from fr_cli.weapon.skill_gist import list_shared_skills, format_shared_skills
    records = list_shared_skills()
    return Result.ok(format_shared_skills(records, lang="zh"))


@register(
    name="skill_search_gist",
    triggers=["搜 skill", "search skill"],
    description="搜索 Gist 上的 fr-cli skills(返回搜索链接)",
    params={"query": str},
    aliases=["/skill_search"],
)
def _register_skill_search(deps, **kwargs):
    query = kwargs.get("query") or ""
    if not query:
        return Result.fail("需要提供 query")

    from fr_cli.weapon.skill_gist import search_gists
    result = search_gists(query)
    if not result["ok"]:
        return Result.fail(result.get("error", "搜索失败"))

    return Result.ok(
        f"🔍 Gist 搜索结果:\n"
        f"  Query: {query}\n"
        f"  搜索 URL: {result.get('search_url', '?')}\n\n"
        f"💡 GitHub 没有官方 Gist search API。请用上面链接在浏览器搜索,\n"
        f"   找到喜欢的 gist 后,用 /skill_import <URL> 导入。"
    )
