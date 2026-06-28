"""Bookmark 收藏夹测试"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fr_cli.weapon.bookmark import (
    _html_to_md, _ensure_dirs, list_bookmarks, remove_bookmark,
    get_bookmark, search_bookmarks, import_chrome_bookmarks,
    format_bookmarks_list,
)


SIMPLE_HTML = """<!DOCTYPE html>
<html>
<head><title>测试页面</title></head>
<body>
<h1>标题 1</h1>
<p>这是 <strong>粗体</strong> 和 <em>斜体</em> 文本。</p>
<p>看 <code>print()</code> 函数。</p>
<a href="https://example.com">链接</a>
<ul><li>列表项 1</li><li>列表项 2</li></ul>
<script>console.log('hidden')</script>
<style>body { color: red; }</style>
</body>
</html>
"""


class TestHtmlToMd(unittest.TestCase):
    def test_strip_script_style(self):
        out = _html_to_md(SIMPLE_HTML)
        self.assertNotIn("console.log", out)
        self.assertNotIn("color: red", out)

    def test_h1_to_heading(self):
        out = _html_to_md(SIMPLE_HTML)
        self.assertIn("# 标题 1", out)

    def test_bold_italic(self):
        out = _html_to_md(SIMPLE_HTML)
        self.assertIn("**粗体**", out)
        self.assertIn("*斜体*", out)

    def test_inline_code(self):
        out = _html_to_md(SIMPLE_HTML)
        self.assertIn("`print()`", out)

    def test_links(self):
        out = _html_to_md(SIMPLE_HTML)
        self.assertIn("[链接](https://example.com)", out)

    def test_list(self):
        out = _html_to_md(SIMPLE_HTML)
        self.assertIn("- 列表项 1", out)

    def test_html_entities(self):
        html = "<p>5 &lt; 10 &amp; 7 &gt; 3</p>"
        out = _html_to_md(html)
        self.assertIn("5 < 10 & 7 > 3", out)

    def test_long_truncate(self):
        html = "<p>" + ("x" * 50000) + "</p>"
        out = _html_to_md(html, max_length=1000)
        self.assertIn("已截断", out)


class TestBookmarkCRUD(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="test_bm_")
        # patch 所有 path
        from fr_cli.conf.paths import ROOT as FR_CLI_DIR
        import fr_cli.weapon.bookmark as mod
        self.real_dir = mod.BOOKMARKS_DIR
        self.real_content = mod.CONTENT_DIR
        self.real_file = mod.BOOKMARKS_FILE
        mod.BOOKMARKS_DIR = Path(self.tmp)
        mod.CONTENT_DIR = Path(self.tmp) / "content"
        mod.BOOKMARKS_FILE = Path(self.tmp) / "bookmarks.json"
        # 也 patch bookmark_rag
        import fr_cli.weapon.bookmark_rag as rag_mod
        rag_mod.BOOKMARKS_FILE = Path(self.tmp) / "bookmarks.json"

    def tearDown(self):
        import fr_cli.weapon.bookmark as mod
        import fr_cli.weapon.bookmark_rag as rag_mod
        mod.BOOKMARKS_DIR = self.real_dir
        mod.CONTENT_DIR = self.real_content
        mod.BOOKMARKS_FILE = self.real_file
        rag_mod.BOOKMARKS_FILE = self.real_file
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_add_no_fetch(self):
        from fr_cli.weapon.bookmark import add_bookmark
        r = add_bookmark("https://example.com", tags=["test"], fetch=False)
        self.assertTrue(r["ok"])
        self.assertIn("id", r)
        bms = list_bookmarks()
        self.assertEqual(len(bms), 1)
        self.assertEqual(bms[0]["tags"], ["test"])

    @patch("fr_cli.weapon.bookmark.fetch_url")
    def test_add_with_fetch(self, mock_fetch):
        mock_fetch.return_value = {
            "ok": True,
            "title": "Example Domain",
            "text": "Example content",
        }
        from fr_cli.weapon.bookmark import add_bookmark
        r = add_bookmark("https://example.com", fetch=True)
        self.assertTrue(r["ok"])
        self.assertEqual(r["title"], "Example Domain")
        bms = list_bookmarks()
        self.assertEqual(bms[0]["content_file"], bms[0]["content_file"])  # 存在

    @patch("fr_cli.weapon.bookmark.fetch_url")
    def test_add_fetch_fail(self, mock_fetch):
        mock_fetch.return_value = {"ok": False, "error": "404"}
        from fr_cli.weapon.bookmark import add_bookmark
        r = add_bookmark("https://example.com", fetch=True)
        self.assertTrue(r["ok"])
        self.assertIn("fetch_error", get_bookmark(r["id"]))

    def test_get(self):
        from fr_cli.weapon.bookmark import add_bookmark
        r = add_bookmark("https://x.com", fetch=False)
        bm = get_bookmark(r["id"])
        self.assertIsNotNone(bm)
        self.assertEqual(bm["url"], "https://x.com")

    def test_get_nonexistent(self):
        bm = get_bookmark("nonexistent")
        self.assertIsNone(bm)

    def test_remove(self):
        from fr_cli.weapon.bookmark import add_bookmark
        r = add_bookmark("https://x.com", fetch=False)
        self.assertTrue(remove_bookmark(r["id"]))
        self.assertIsNone(get_bookmark(r["id"]))

    def test_remove_nonexistent(self):
        self.assertFalse(remove_bookmark("nope"))

    def test_list_filter_tag(self):
        from fr_cli.weapon.bookmark import add_bookmark
        add_bookmark("https://a.com", tags=["ai"], fetch=False)
        add_bookmark("https://b.com", tags=["doc"], fetch=False)
        bms = list_bookmarks(tag="ai")
        self.assertEqual(len(bms), 1)


class TestSearch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="test_bms_")
        import fr_cli.weapon.bookmark as mod
        self.real_file = mod.BOOKMARKS_FILE
        mod.BOOKMARKS_FILE = Path(self.tmp) / "bookmarks.json"

    def tearDown(self):
        import fr_cli.weapon.bookmark as mod
        mod.BOOKMARKS_FILE = self.real_file
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_search_in_title(self):
        from fr_cli.weapon.bookmark import add_bookmark
        add_bookmark("https://python.org", tags=["doc"], description="python 官方", fetch=False)
        add_bookmark("https://rust-lang.org", tags=["doc"], description="rust 官方", fetch=False)

        results = search_bookmarks("python")
        self.assertEqual(len(results), 1)
        self.assertIn("python", results[0]["url"])

    def test_search_no_match(self):
        from fr_cli.weapon.bookmark import add_bookmark
        add_bookmark("https://x.com", fetch=False)
        results = search_bookmarks("nonexistent_keyword_xyz")
        self.assertEqual(len(results), 0)


class TestImportChrome(unittest.TestCase):
    def test_import(self):
        with tempfile.NamedTemporaryFile(suffix=".html", mode="w", delete=False, encoding="utf-8") as f:
            f.write("""<html><body>
<DL><p>
<DT><H3>Bookmarks bar</H3>
<DL><p>
<DT><A HREF="https://example.com">Example</A>
<DT><A HREF="https://python.org">Python</A>
<DT><A HREF="not-a-url">Invalid</A>
</DL><p>
</DL><p>
</body></html>
""")
            path = f.name

        try:
            # patch BOOKMARKS_FILE
            import fr_cli.weapon.bookmark as mod
            tmp = tempfile.mkdtemp(prefix="test_imp_")
            real_file = mod.BOOKMARKS_FILE
            mod.BOOKMARKS_FILE = Path(tmp) / "bookmarks.json"
            mod.BOOKMARKS_DIR = Path(tmp)
            try:
                result = import_chrome_bookmarks(path)
                self.assertTrue(result["ok"])
                # 不算 invalid 那条,应该有 2 个
                self.assertEqual(result["imported"], 2)
            finally:
                mod.BOOKMARKS_FILE = real_file
                import shutil
                shutil.rmtree(tmp, ignore_errors=True)
        finally:
            os.unlink(path)

    def test_import_nonexistent(self):
        result = import_chrome_bookmarks("/nonexistent.html")
        self.assertFalse(result["ok"])


class TestFormat(unittest.TestCase):
    def test_empty(self):
        out = format_bookmarks_list([])
        self.assertIn("没有", out)

    def test_with_data(self):
        bms = [
            {"id": "bm-1", "title": "test", "url": "https://x.com", "tags": ["ai"], "created_at": 1234567890}
        ]
        out = format_bookmarks_list(bms)
        self.assertIn("bm-1", out)
        self.assertIn("test", out)


if __name__ == "__main__":
    unittest.main()