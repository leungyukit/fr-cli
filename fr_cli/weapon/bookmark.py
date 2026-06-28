"""
Web Bookmark 收藏夹 + RAG 联动

功能:
- /bookmark <url> [tags...]: 收藏 URL,保存元数据 + 抓取正文,可选入 RAG
- /bookmark_list [tag]: 列出收藏(可选按 tag 过滤)
- /bookmark_get <id>: 查看详情 + 正文
- /bookmark_search <query>: 全文搜索(在收藏中)
- /bookmark_rm <id>: 删除收藏
- /bookmark_sync_rag [id]: 把收藏入 RAG(便于后续问答)
- /bookmark_import_chrome: 从 Chrome 浏览器导入书签

存储:
- ~/.fr_cli/bookmarks/bookmarks.json(元数据)
- ~/.fr_cli/bookmarks/content/<id>.md(抓取的正文)
- 入 RAG 后由 RAG 系统管理
"""
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from fr_cli.conf.paths import ROOT as FR_CLI_DIR
from fr_cli.core.store import JsonStore


BOOKMARKS_DIR = FR_CLI_DIR / "bookmarks"
CONTENT_DIR = BOOKMARKS_DIR / "content"
BOOKMARKS_FILE = BOOKMARKS_DIR / "bookmarks.json"


def _ensure_dirs():
    BOOKMARKS_DIR.mkdir(parents=True, exist_ok=True)
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    if not BOOKMARKS_FILE.exists():
        JsonStore(str(BOOKMARKS_FILE), default=dict).write({"bookmarks": []})


def fetch_url(url: str, timeout: int = 15) -> Dict[str, Any]:
    """抓取 URL 内容

    Returns:
        {"ok", "html", "text", "title", "status"}
    """
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) fr-cli/2.8"
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            body = resp.read()
            # 解码
            charset = "utf-8"
            m = re.search(r"charset=([\w-]+)", content_type)
            if m:
                charset = m.group(1)
            try:
                html = body.decode(charset, errors="ignore")
            except LookupError:
                html = body.decode("utf-8", errors="ignore")
            # 提取 title
            title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
            title = title_m.group(1).strip() if title_m else url
            title = re.sub(r"\s+", " ", title)
            # 简单转 md(去掉 script/style)
            text = _html_to_md(html)
            return {"ok": True, "html": html, "text": text, "title": title, "status": resp.status}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}", "status": e.code}
    except urllib.error.URLError as e:
        return {"ok": False, "error": str(e.reason)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _html_to_md(html: str, max_length: int = 30000) -> str:
    """HTML → 简化 Markdown(去掉 script/style/标签)"""
    # 去掉 script/style/noscript(反向引用要避免被解释为位置参数)
    html = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>",
                  "", html, flags=re.DOTALL | re.IGNORECASE, count=0)
    # 标题 h1-h6 → # ...
    html = re.sub(r"<h([1-6])[^>]*>(.*?)</h\1>",
                  lambda m: f"\n{'#' * int(m.group(1))} {m.group(2)}\n",
                  html, flags=re.DOTALL | re.IGNORECASE)
    # 段落
    html = re.sub(r"<p[^>]*>", "\n\n", html, flags=re.IGNORECASE)
    html = re.sub(r"</p>", "\n", html, flags=re.IGNORECASE)
    # 链接
    html = re.sub(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                  r"[\2](\1)", html, flags=re.DOTALL | re.IGNORECASE)
    # 粗体/斜体
    html = re.sub(r"<(strong|b)[^>]*>(.*?)</\1>", r"**\2**", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<(em|i)[^>]*>(.*?)</\1>", r"*\2*", html, flags=re.DOTALL | re.IGNORECASE)
    # 代码
    html = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", html, flags=re.DOTALL | re.IGNORECASE)
    # 换行
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"<li[^>]*>", "\n- ", html, flags=re.IGNORECASE)
    # 去掉所有剩余标签
    html = re.sub(r"<[^>]+>", "", html)
    # HTML entities 解码
    html = (html.replace("&nbsp;", " ")
                .replace("&amp;", "&")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
                .replace("&quot;", '"')
                .replace("&#39;", "'"))
    # 多空行
    html = re.sub(r"\n\s*\n\s*\n+", "\n\n", html)
    text = html.strip()
    if len(text) > max_length:
        text = text[:max_length] + "\n\n... (内容过长,已截断)"
    return text


def add_bookmark(url: str, tags: Optional[List[str]] = None,
                 description: str = "",
                 fetch: bool = True,
                 sync_to_rag: bool = False) -> Dict[str, Any]:
    """添加书签

    Args:
        url: 链接
        tags: 标签列表
        description: 描述
        fetch: 是否抓取正文
        sync_to_rag: 是否同步到 RAG

    Returns:
        {"ok": bool, "id": str, "title": str, "error": str?}
    """
    _ensure_dirs()

    bookmark_id = f"bm-{int(time.time() * 1000)}"
    tags = tags or []

    bookmark = {
        "id": bookmark_id,
        "url": url,
        "title": url,  # 先用 URL,抓取后更新
        "description": description,
        "tags": tags,
        "created_at": time.time(),
        "updated_at": time.time(),
        "in_rag": False,
    }

    if fetch:
        r = fetch_url(url)
        if r["ok"]:
            bookmark["title"] = r.get("title", url)
            # 保存正文
            content_file = CONTENT_DIR / f"{bookmark_id}.md"
            content_file.write_text(
                f"# {bookmark['title']}\n\n"
                f"URL: {url}\n"
                f"收藏于: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                + (f"标签: {', '.join(tags)}\n" if tags else "")
                + (f"描述: {description}\n\n" if description else "\n")
                + "---\n\n"
                + r["text"],
                encoding="utf-8",
            )
            bookmark["content_file"] = str(content_file)
            bookmark["content_length"] = len(r["text"])
        else:
            bookmark["fetch_error"] = r.get("error", "抓取失败")

    # 入库
    data = JsonStore(str(BOOKMARKS_FILE), default=dict).read()
    bookmarks = data.get("bookmarks", [])
    bookmarks.append(bookmark)
    data["bookmarks"] = bookmarks
    JsonStore(str(BOOKMARKS_FILE), default=dict).write(data)

    result = {"ok": True, "id": bookmark_id, "title": bookmark["title"], "tags": tags}

    # 同步 RAG
    if sync_to_rag and bookmark.get("content_file"):
        try:
            from fr_cli.weapon.bookmark_rag import sync_bookmark_to_rag
            rag_result = sync_bookmark_to_rag(bookmark_id)
            result["rag_synced"] = rag_result.get("ok", False)
        except Exception as e:
            result["rag_synced"] = False
            result["rag_error"] = str(e)

    return result


def list_bookmarks(tag: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """列出书签"""
    _ensure_dirs()
    data = JsonStore(str(BOOKMARKS_FILE), default=dict).read()
    bookmarks = data.get("bookmarks", [])
    if tag:
        bookmarks = [b for b in bookmarks if tag in (b.get("tags") or [])]
    # 按时间倒序
    bookmarks.sort(key=lambda x: x.get("created_at", 0), reverse=True)
    return bookmarks[:limit]


def get_bookmark(bookmark_id: str) -> Optional[Dict[str, Any]]:
    """获取书签详情"""
    data = JsonStore(str(BOOKMARKS_FILE), default=dict).read()
    bookmarks = data.get("bookmarks", [])
    for b in bookmarks:
        if b.get("id") == bookmark_id:
            return b
    return None


def remove_bookmark(bookmark_id: str) -> bool:
    """删除书签"""
    data = JsonStore(str(BOOKMARKS_FILE), default=dict).read()
    bookmarks = data.get("bookmarks", [])
    target = None
    for b in bookmarks:
        if b.get("id") == bookmark_id:
            target = b
            break
    if not target:
        return False

    # 删除内容文件
    content_file = target.get("content_file")
    if content_file and os.path.exists(content_file):
        try:
            os.remove(content_file)
        except Exception:
            pass

    bookmarks = [b for b in bookmarks if b.get("id") != bookmark_id]
    data["bookmarks"] = bookmarks
    JsonStore(str(BOOKMARKS_FILE), default=dict).write(data)
    return True


def search_bookmarks(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """全文搜索书签"""
    _ensure_dirs()
    query_lower = query.lower()
    matches = []

    bookmarks = list_bookmarks(limit=10000)
    for b in bookmarks:
        score = 0
        title = (b.get("title") or "").lower()
        desc = (b.get("description") or "").lower()
        url = (b.get("url") or "").lower()
        tags = [t.lower() for t in b.get("tags", [])]

        if query_lower in title:
            score += 10
        if query_lower in desc:
            score += 5
        if query_lower in url:
            score += 2
        if any(query_lower in t for t in tags):
            score += 3

        # 搜索内容
        content_file = b.get("content_file")
        if content_file and os.path.exists(content_file):
            try:
                content = Path(content_file).read_text(encoding="utf-8").lower()
                if query_lower in content:
                    # 出现次数
                    count = content.count(query_lower)
                    score += min(count, 20)
            except Exception:
                pass

        if score > 0:
            matches.append({**b, "score": score})

    matches.sort(key=lambda x: x.get("score", 0), reverse=True)
    return matches[:limit]


def import_chrome_bookmarks(html_file: str) -> Dict[str, Any]:
    """从 Chrome 导出的 HTML 书签文件导入

    Returns:
        {"ok": bool, "imported": int, "error": str?}
    """
    if not os.path.exists(html_file):
        return {"ok": False, "error": f"文件不存在: {html_file}"}

    try:
        content = Path(html_file).read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return {"ok": False, "error": str(e)}

    # Chrome 书签格式:<A HREF="...">title</A>
    pattern = re.compile(r'<A\s+HREF="([^"]+)"[^>]*>(.*?)</A>', re.IGNORECASE | re.DOTALL)
    imported = 0
    for m in pattern.finditer(content):
        url = m.group(1).strip()
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if not url or not url.startswith("http"):
            continue
        try:
            add_bookmark(url, tags=["imported"], description=title, fetch=False)
            imported += 1
        except Exception:
            pass

    return {"ok": True, "imported": imported}


def format_bookmarks_list(bookmarks: List[Dict[str, Any]], lang: str = "zh") -> str:
    """格式化书签列表"""
    if not bookmarks:
        return "📚 没有书签"

    if lang == "zh":
        title = f"📚 书签列表 ({len(bookmarks)})"
    else:
        title = f"📚 Bookmarks ({len(bookmarks)})"

    lines = [title]
    for b in bookmarks:
        tags_str = " ".join(f"#{t}" for t in b.get("tags", []))
        title_short = b.get("title", b.get("url", "?"))[:50]
        rag_marker = " 🧠" if b.get("in_rag") else ""
        ts = datetime.fromtimestamp(b.get("created_at", 0)).strftime("%Y-%m-%d")
        lines.append(f"  [{b['id']}] {title_short}{rag_marker}")
        lines.append(f"    {b.get('url', '')}")
        lines.append(f"    {ts} {tags_str}")
    return "\n".join(lines)
