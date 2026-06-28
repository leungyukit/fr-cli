"""
Bookmark → RAG 同步工具

把 bookmark 的 markdown 内容存到 RAG 知识库目录
"""
import os
from pathlib import Path
from typing import Dict, Any, Optional

from fr_cli.weapon.bookmark import get_bookmark


def sync_bookmark_to_rag(bookmark_id: str, rag_dir: Optional[str] = None) -> Dict[str, Any]:
    """同步单个 bookmark 到 RAG

    Args:
        bookmark_id: 书签 ID
        rag_dir: RAG 知识库目录(默认 ~/.fr_cli/rag/)

    Returns:
        {"ok": bool, "path": str, "error": str?}
    """
    bm = get_bookmark(bookmark_id)
    if not bm:
        return {"ok": False, "error": f"书签不存在: {bookmark_id}"}

    content_file = bm.get("content_file")
    if not content_file or not os.path.exists(content_file):
        return {"ok": False, "error": "书签没有内容文件,先抓取正文"}

    if not rag_dir:
        from fr_cli.conf.paths import ROOT as FR_CLI_DIR
        rag_dir = str(FR_CLI_DIR / "rag")

    os.makedirs(rag_dir, exist_ok=True)

    # 用书签标题作为文件名
    title = bm.get("title", "untitled")
    safe_title = "".join(c if c.isalnum() or c in "-_ " else "_" for c in title)[:50]
    target = os.path.join(rag_dir, f"bookmark_{bookmark_id}_{safe_title}.md")

    # 复制内容
    try:
        content = Path(content_file).read_text(encoding="utf-8")
        Path(target).write_text(content, encoding="utf-8")
    except Exception as e:
        return {"ok": False, "error": str(e)}

    # 更新书签的 in_rag 标记
    try:
        from fr_cli.conf.paths import ROOT as FR_CLI_DIR
        from fr_cli.core.store import JsonStore
        from fr_cli.weapon.bookmark import BOOKMARKS_FILE
        data = JsonStore(str(BOOKMARKS_FILE), default=dict).read()
        bookmarks = data.get("bookmarks", [])
        for b in bookmarks:
            if b.get("id") == bookmark_id:
                b["in_rag"] = True
                b["rag_path"] = target
                break
        data["bookmarks"] = bookmarks
        JsonStore(str(BOOKMARKS_FILE), default=dict).write(data)
    except Exception:
        pass

    return {"ok": True, "path": target}


def sync_all_bookmarks_to_rag(rag_dir: Optional[str] = None) -> Dict[str, Any]:
    """同步所有未入 RAG 的书签"""
    from fr_cli.weapon.bookmark import list_bookmarks
    bookmarks = list_bookmarks(limit=10000)
    synced = 0
    skipped = 0
    errors = []

    for b in bookmarks:
        if b.get("in_rag"):
            skipped += 1
            continue
        result = sync_bookmark_to_rag(b["id"], rag_dir=rag_dir)
        if result["ok"]:
            synced += 1
        else:
            errors.append({"id": b["id"], "error": result.get("error")})

    return {
        "ok": len(errors) == 0,
        "synced": synced,
        "skipped": skipped,
        "errors": errors,
    }
