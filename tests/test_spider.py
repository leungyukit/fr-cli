"""
@spider 智能爬虫测试
覆盖链接提取、文件名清理、依赖检查、爬取逻辑(用 httpbin 或本地 HTML)。

注意:
- 网络爬取测试需要能访问外网,默认使用 httpbin.org(公共测试服务)
- 若网络不可用,会被标记为 skip
- 部分测试用 mock 避免依赖外网
"""
import os
import sys
import socket
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ==================== 依赖检查 ====================

def _have_requests():
    try:
        import requests  # noqa
        return True
    except ImportError:
        return False


# ==================== 本地 HTTP Server ====================

class StaticHTMLHandler(BaseHTTPRequestHandler):
    """简单的 HTML 静态页 server,用于本地测试爬取"""
    html_content = None

    def log_message(self, *args):
        pass  # 静默

    def do_GET(self):
        path = self.path
        if path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(self.html_content or b"<html><body>root</body></html>")
        elif path == "/page2":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html><body>page 2</body></html>")
        elif path == "/page3":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html><body>page 3</body></html>")
        elif path == "/tiny":
            # 故意返回很小的内容,触发"反爬"判定
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html></html>")
        elif path == "/captcha":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html>captcha challenge</body></html>")
        elif path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def local_http_server():
    """起一个本地 HTTP server 返回预设 HTML(长度 > 500 避免触发反爬)"""
    # 注意:_fetch_with_requests 要求 len(text) >= 500 才认为是正常页面
    padding = "x" * 800
    StaticHTMLHandler.html_content = f"""
<!DOCTYPE html>
<html>
<head><title>Test Index</title></head>
<body>
  <h1>Test Page</h1>
  <p>{padding}</p>
  <a href="/page2">Page 2</a>
  <a href="/page3">Page 3</a>
  <a href="https://example.com">External</a>
  <a href="/nonexistent">Broken</a>
  <a href="#anchor">Anchor</a>
  <a href="javascript:void(0)">JS</a>
</body>
</html>
""".encode("utf-8")
    port = _free_port()
    server = HTTPServer(("127.0.0.1", port), StaticHTMLHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.3)
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


# ==================== 测试:文件名清理 ====================

class TestSanitizeFilename:

    def test_basic_url(self):
        from fr_cli.agent.builtins.spider.memory import _sanitize_filename
        result = _sanitize_filename("https://example.com/path")
        # 应是合法文件名,无特殊字符
        assert "/" not in result or result.endswith(".html")
        assert "example.com" in result or "example" in result

    def test_url_with_query(self):
        from fr_cli.agent.builtins.spider.memory import _sanitize_filename
        result = _sanitize_filename("https://example.com/?q=test&p=1")
        assert "?" not in result
        assert "&" not in result

    def test_url_with_fragment(self):
        from fr_cli.agent.builtins.spider.memory import _sanitize_filename
        result = _sanitize_filename("https://example.com/page#section")
        assert "#" not in result

    def test_unsafe_chars_replaced(self):
        from fr_cli.agent.builtins.spider.memory import _sanitize_filename
        result = _sanitize_filename("https://example.com/<>:|*?")
        # 不应包含文件系统非法字符
        unsafe = '<>:|"?'
        for ch in unsafe:
            assert ch not in result, f"包含非法字符 {ch}: {result}"


# ==================== 测试:链接提取 ====================

class TestExtractLinksRegex:

    def test_extract_absolute_links(self):
        from fr_cli.agent.builtins.spider.analyzer import _extract_links_regex
        html = '<a href="https://example.com/a">A</a><a href="https://example.com/b">B</a>'
        links = _extract_links_regex(html, "https://example.com/")
        assert "https://example.com/a" in links
        assert "https://example.com/b" in links

    def test_extract_relative_links(self):
        from fr_cli.agent.builtins.spider.analyzer import _extract_links_regex
        html = '<a href="/page1">1</a><a href="/page2">2</a>'
        links = _extract_links_regex(html, "https://example.com/")
        assert "https://example.com/page1" in links
        assert "https://example.com/page2" in links

    def test_skip_anchor_and_javascript(self):
        from fr_cli.agent.builtins.spider.analyzer import _extract_links_regex
        html = '<a href="#anchor">a</a><a href="javascript:void(0)">j</a>'
        links = _extract_links_regex(html, "https://example.com/")
        # 锚点和 JS 不应作为可爬取链接
        assert all("javascript:" not in l for l in links)
        # 锚点可能保留也可能跳过,只要不含 javascript 即可

    def test_empty_html(self):
        from fr_cli.agent.builtins.spider.analyzer import _extract_links_regex
        links = _extract_links_regex("<html></html>", "https://example.com/")
        assert links == [] or all(isinstance(l, str) for l in links)


# ==================== 测试:requests 抓取 ====================

class TestFetchWithRequests:

    def test_fetch_local_server(self, local_http_server):
        """本地 server,无反爬特征:应能抓到"""
        if not _have_requests():
            pytest.skip("requests 未装")
        from fr_cli.agent.builtins.spider.fetcher import _fetch_with_requests
        html, err = _fetch_with_requests(local_http_server + "/")
        assert err is None, f"error: {err}"
        assert html is not None
        assert "Test Page" in html or "Test Index" in html

    def test_fetch_tiny_page_triggers_anti_bot(self, local_http_server):
        """过小的页面应被判定为反爬"""
        from fr_cli.agent.builtins.spider.fetcher import _fetch_with_requests
        html, err = _fetch_with_requests(local_http_server + "/tiny")
        assert html is None or err is not None
        if err:
            assert "反爬" in err or "captcha" in err.lower() or "content" in err.lower()

    def test_fetch_captcha_page_triggers_anti_bot(self, local_http_server):
        """含 captcha 关键词的页面应被判定"""
        from fr_cli.agent.builtins.spider.fetcher import _fetch_with_requests
        html, err = _fetch_with_requests(local_http_server + "/captcha")
        assert html is None or err is not None

    def test_fetch_404_returns_error(self, local_http_server):
        """404 应返回错误"""
        from fr_cli.agent.builtins.spider.fetcher import _fetch_with_requests
        html, err = _fetch_with_requests(local_http_server + "/nonexistent-xxx")
        # 404 应让 err 不为 None
        assert html is None or err is not None

    def test_fetch_invalid_url(self):
        """无效 URL 应捕获异常并返回 error"""
        from fr_cli.agent.builtins.spider.fetcher import _fetch_with_requests
        html, err = _fetch_with_requests("not-a-valid-url://xxx")
        # 应该要么有 error,要么 html 为 None
        assert html is None or err is not None


# ==================== 测试:依赖检查 ====================

class TestDeps:

    def test_requests_available(self):
        """_get_requests 应能拿到 requests 模块(如果装了)"""
        from fr_cli.agent.builtins.spider.deps import _get_requests
        r = _get_requests()
        if _have_requests():
            assert r is not None
        # 如果没装,可能是 None,这不算 bug

    def test_selenium_available(self):
        """_get_selenium 应能拿到 selenium(如果装了)"""
        from fr_cli.agent.builtins.spider.deps import _get_selenium
        s = _get_selenium()
        try:
            import selenium  # noqa
            assert s is not None
        except ImportError:
            pass  # 没装不算 bug


# ==================== 测试:自适应抓取 ====================

class TestFetchAdaptive:

    def test_fetch_adaptive_uses_requests_first(self, local_http_server):
        """默认应先用 requests,成功则返回 method=requests"""
        from fr_cli.agent.builtins.spider.fetcher import _fetch_adaptive
        # 创建一个有 size > 500 的页面 → 走 requests 成功路径
        html, err, method = _fetch_adaptive(local_http_server + "/", state=None)
        assert err is None, f"err: {err}"
        assert method == "requests"
        assert html is not None

    def test_fetch_adaptive_falls_back_to_selenium_on_anti_bot(self, local_http_server):
        """遇到反爬特征应降级到 selenium(但本地 server selenium 也会失败,这是预期)"""
        from fr_cli.agent.builtins.spider.fetcher import _fetch_adaptive
        # 用 /tiny 页面,会触发反爬 → 走 selenium
        # 没有 chromedriver 时 selenium 会失败,这是预期
        # 我们只验证会尝试 selenium
        with patch("fr_cli.agent.builtins.spider.fetcher._fetch_with_selenium") as mock_se:
            mock_se.return_value = ("<html>fake selenium result</html>", None)
            html, err, method = _fetch_adaptive(local_http_server + "/tiny", state=None)
            assert mock_se.called
            assert method == "selenium"


# ==================== 测试:handle_spider 命令处理 ====================

class TestHandleSpider:

    def test_empty_url_prints_usage(self, capsys):
        from fr_cli.agent.builtins.spider.crawler import handle_spider
        mock_state = MagicMock()
        mock_state.vfs = MagicMock(cwd="/tmp")
        handle_spider("@spider ", mock_state)
        captured = capsys.readouterr()
        assert "用法" in captured.out or "用法" in captured.err

    def test_url_without_protocol_gets_https_prefix(self, capsys):
        """无 http:// 前缀的 URL 应自动补 https://"""
        from fr_cli.agent.builtins.spider.crawler import handle_spider

        mock_state = MagicMock()
        mock_state.vfs = MagicMock(cwd="/tmp")

        with patch("fr_cli.agent.builtins.spider.crawler.crawl") as mock_crawl:
            from fr_cli.core.result import Result
            mock_crawl.return_value = Result.ok(([], [], {
                "total_pages": 0, "success_requests": 0, "success_selenium": 0,
                "selector_memory_hits": 0, "selector_ai_hits": 0,
                "regex_fallbacks": 0, "domains": set(),
            }))
            handle_spider("@spider example.com", mock_state)
            # 调用 crawl 时 URL 应是 https://example.com
            assert mock_crawl.called
            called_url = mock_crawl.call_args[0][0]
            assert called_url.startswith("https://example.com")


# ==================== 测试:页面保存 ====================

class TestSavePage:

    def test_save_creates_file(self, tmp_path):
        from fr_cli.agent.builtins.spider.fetcher import _save_page
        url = "https://example.com/test"
        html = "<html><body>hello</body></html>"
        filepath = _save_page(url, html, tmp_path)
        assert Path(filepath).exists()
        content = Path(filepath).read_text(encoding="utf-8")
        assert "hello" in content

    def test_save_creates_output_dir(self, tmp_path):
        """不存在的目录应自动创建"""
        from fr_cli.agent.builtins.spider.fetcher import _save_page
        output_dir = tmp_path / "subdir" / "deeper"
        filepath = _save_page("https://example.com/x", "<html></html>", output_dir)
        assert output_dir.exists()
        assert Path(filepath).exists()
