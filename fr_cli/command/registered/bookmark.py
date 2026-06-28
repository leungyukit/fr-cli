"""
Bookmark 收藏夹工具:
- bookmark_add: 添加书签(可自动抓取正文 + 入 RAG)
- bookmark_list: 列出书签
- bookmark_get: 查看详情
- bookmark_search: 全文搜索
- bookmark_rm: 删除书签
- bookmark_sync_rag: 同步到 RAG
- bookmark_import_chrome: 从 Chrome 导入
"""
from fr_cli.command.registry import register
from fr_cli.core.result import Result


@register(
    name="bookmark_add",
    triggers=["收藏书签", "bookmark", "收藏网页"],
    description="收藏 URL 到书签(自动抓取正文,可入 RAG)",
    params={"url": str, "tags": list, "desc": str, "fetch": bool, "rag": bool},
    aliases=["/bookmark", "/bm"],
)
def _register_bookmark_add(deps, **kwargs):
    url = kwargs.get("url") or ""
    tags_raw = kwargs.get("tags") or ""
    desc = kwargs.get("desc") or ""
    fetch = bool(kwargs.get("fetch", True))
    rag = bool(kwargs.get("rag", False))

    if not url:
        return Result.fail("需要提供 URL")

    # tags 可能是 list 或 str
    if isinstance(tags_raw, list):
        tags = tags_raw
    else:
        tags = [t.strip() for t in str(tags_raw).split(",") if t.strip()]

    from fr_cli.weapon.bookmark import add_bookmark
    result = add_bookmark(url, tags=tags, description=desc,
                          fetch=fetch, sync_to_rag=rag)

    extra = ""
    if result.get("rag_synced"):
        extra = "\n  🧠 已同步到 RAG(下次可用 /RAG 查询)"
    elif result.get("rag_error"):
        extra = f"\n  ⚠️ RAG 同步失败: {result['rag_error']}"

    return Result.ok(
        f"✅ 书签已添加:\n"
        f"  ID: {result['id']}\n"
        f"  标题: {result['title']}\n"
        f"  标签: {', '.join(result.get('tags', []))}{extra}"
    )


@register(
    name="bookmark_list",
    triggers=["书签列表", "list bookmarks"],
    description="列出书签(可选按 tag 过滤)",
    params={"tag": str, "limit": int},
    aliases=["/bm_list"],
)
def _register_bookmark_list(deps, **kwargs):
    tag = kwargs.get("tag") or None
    limit = int(kwargs.get("limit", 50))

    from fr_cli.weapon.bookmark import list_bookmarks, format_bookmarks_list
    bms = list_bookmarks(tag=tag, limit=limit)
    return Result.ok(format_bookmarks_list(bms, lang="zh"))


@register(
    name="bookmark_get",
    triggers=["查看书签", "get bookmark"],
    description="查看书签详情 + 正文",
    params={"id": str},
    aliases=["/bm_get"],
)
def _register_bookmark_get(deps, **kwargs):
    bid = kwargs.get("id") or ""
    if not bid:
        return Result.fail("需要提供书签 ID")

    from fr_cli.weapon.bookmark import get_bookmark
    bm = get_bookmark(bid)
    if not bm:
        return Result.fail(f"书签不存在: {bid}")

    text = (
        f"📖 书签详情:\n"
        f"  ID: {bm['id']}\n"
        f"  标题: {bm.get('title', '?')}\n"
        f"  URL: {bm.get('url', '?')}\n"
        f"  标签: {', '.join(bm.get('tags', []))}\n"
        f"  描述: {bm.get('description', '(无)')}\n"
        f"  入 RAG: {'是' if bm.get('in_rag') else '否'}\n"
    )
    if bm.get("fetch_error"):
        text += f"  抓取错误: {bm['fetch_error']}\n"

    # 显示内容前 500 字
    content_file = bm.get("content_file")
    if content_file and os.path.exists(content_file):
        try:
            content = open(content_file, encoding="utf-8").read()
            preview = content[:500] + ("..." if len(content) > 500 else "")
            text += f"\n--- 正文预览 ---\n{preview}\n"
        except Exception:
            pass

    return Result.ok(text)


@register(
    name="bookmark_search",
    triggers=["搜书签", "search bookmarks"],
    description="在书签中全文搜索",
    params={"query": str},
    aliases=["/bm_search"],
)
def _register_bookmark_search(deps, **kwargs):
    query = kwargs.get("query") or ""
    if not query:
        return Result.fail("需要提供 query")

    from fr_cli.weapon.bookmark import search_bookmarks, format_bookmarks_list
    results = search_bookmarks(query)
    if not results:
        return Result.ok(f"🔍 没找到匹配 '{query}' 的书签")
    return Result.ok(f"🔍 找到 {len(results)} 个匹配:\n\n" + format_bookmarks_list(results, lang="zh"))


@register(
    name="bookmark_rm",
    triggers=["删除书签", "rm bookmark"],
    description="删除书签",
    params={"id": str},
    aliases=["/bm_rm"],
)
def _register_bookmark_rm(deps, **kwargs):
    bid = kwargs.get("id") or ""
    if not bid:
        return Result.fail("需要提供书签 ID")

    from fr_cli.weapon.bookmark import remove_bookmark
    if remove_bookmark(bid):
        return Result.ok(f"✅ 书签 {bid} 已删除")
    return Result.fail(f"书签不存在: {bid}")


@register(
    name="bookmark_sync_rag",
    triggers=["书签入 RAG", "sync bookmark rag"],
    description="把书签同步到 RAG(便于后续 @RAG 查询)",
    params={"id": str, "all": bool},
    aliases=["/bm_rag"],
)
def _register_bookmark_rag(deps, **kwargs):
    bid = kwargs.get("id") or None
    sync_all = bool(kwargs.get("all", False))

    if sync_all:
        from fr_cli.weapon.bookmark_rag import sync_all_bookmarks_to_rag
        result = sync_all_bookmarks_to_rag()
        return Result.ok(
            f"🧠 全部同步:\n"
            f"  新增: {result['synced']}\n"
            f"  跳过(已入 RAG): {result['skipped']}\n"
            f"  错误: {len(result['errors'])}\n\n"
            f"💡 下次可用 /RAG 查询这些收藏的内容"
        )

    if not bid:
        return Result.fail("需要提供书签 ID,或用 --all 同步全部")

    from fr_cli.weapon.bookmark_rag import sync_bookmark_to_rag
    result = sync_bookmark_to_rag(bid)
    if not result["ok"]:
        return Result.fail(result.get("error", "同步失败"))
    return Result.ok(
        f"✅ 已入 RAG:\n"
        f"  ID: {bid}\n"
        f"  路径: {result['path']}"
    )


@register(
    name="bookmark_import_chrome",
    triggers=["导入 Chrome 书签", "import chrome bookmarks"],
    description="从 Chrome 导出的 HTML 书签文件导入",
    params={"path": str},
    aliases=["/bm_chrome"],
)
def _register_bookmark_chrome(deps, **kwargs):
    path = kwargs.get("path") or ""
    if not path:
        return Result.fail("需要提供 Chrome 书签 HTML 文件路径")

    from fr_cli.weapon.bookmark import import_chrome_bookmarks
    result = import_chrome_bookmarks(path)
    if not result["ok"]:
        return Result.fail(result.get("error", "导入失败"))
    return Result.ok(f"✅ 已从 Chrome 导入 {result['imported']} 个书签")


import os  # noqa: E402
