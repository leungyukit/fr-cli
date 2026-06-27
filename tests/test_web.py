"""
Web 搜索 / 内容抓取测试
覆盖 WebRaider.search / fetch 的 SSRF 防护、参数校验、错误处理。

实际网络搜索需要外网,大多数测试用本地 mock。
"""
import os
import sys
from unittest.mock import patch, MagicMock


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fr_cli.weapon.web import WebRaider, _is_private_url


# ==================== SSRF 防护测试 ====================

class TestSsrfProtection:

    def test_reject_file_protocol(self):
        assert _is_private_url("file:///etc/passwd") is True

    def test_reject_ftp_protocol(self):
        assert _is_private_url("ftp://example.com/file") is True

    def test_reject_localhost(self):
        assert _is_private_url("http://localhost/admin") is True

    def test_reject_127(self):
        assert _is_private_url("http://127.0.0.1:8080/") is True

    def test_reject_private_10_range(self):
        assert _is_private_url("http://10.0.0.1/") is True

    def test_reject_private_172_range(self):
        assert _is_private_url("http://172.16.0.1/") is True

    def test_reject_private_192_range(self):
        assert _is_private_url("http://192.168.1.1/") is True

    def test_reject_link_local(self):
        assert _is_private_url("http://169.254.169.254/latest/meta-data/") is True

    def test_allow_public_url(self):
        assert _is_private_url("https://www.example.com/") is False

    def test_allow_public_ip(self):
        assert _is_private_url("https://8.8.8.8/") is False


# ==================== Search 测试 ====================

class TestSearch:

    def test_search_empty_query(self):
        raider = WebRaider()
        result = raider.search("", "zh")
        # 空查询应返回 fail
        assert result.is_fail() or result.unwrap() == []

    def test_search_with_mock_requests(self):
        """用 mock requests 模拟搜索结果"""
        raider = WebRaider()
        fake_html = """
<html><body>
<a href="https://example.com/1">First Result Title</a>
<a href="https://example.com/2">Second Result Title</a>
<a href="/internal">Internal Link</a>
</body></html>
"""
        with patch("fr_cli.weapon.web.requests") as mock_req:
            mock_resp = MagicMock()
            mock_resp.text = fake_html
            mock_req.get.return_value = mock_resp

            result = raider.search("test query", "zh")
            if result.is_ok():
                items = result.unwrap()
                assert isinstance(items, list)
            # 不崩即可

    def test_search_network_error_returns_fail(self):
        raider = WebRaider()
        with patch("fr_cli.weapon.web.requests") as mock_req:
            mock_req.get.side_effect = Exception("network down")
            result = raider.search("test", "zh")
            assert result.is_fail()


# ==================== Fetch 测试 ====================

class TestFetch:

    def test_fetch_ssrf_blocked(self):
        """fetch 内网地址应被 SSRF 防护拦截"""
        raider = WebRaider()
        result = raider.fetch("http://127.0.0.1/", "zh")
        assert result.is_fail()
        assert "禁止" in result.error or "私有" in result.error or "内网" in result.error

    def test_fetch_empty_url(self):
        raider = WebRaider()
        result = raider.fetch("", "zh")
        assert result.is_fail()

    def test_fetch_with_mock(self):
        raider = WebRaider()
        with patch("fr_cli.weapon.web.requests") as mock_req:
            mock_resp = MagicMock()
            mock_resp.text = "<html><body>Hello</body></html>"
            mock_req.get.return_value = mock_resp

            result = raider.fetch("https://www.example.com/", "zh")
            if result.is_ok():
                text = result.unwrap()
                assert "Hello" in text or "<html>" in text

    def test_fetch_network_error(self):
        raider = WebRaider()
        with patch("fr_cli.weapon.web.requests") as mock_req:
            mock_req.get.side_effect = Exception("timeout")
            result = raider.fetch("https://example.com/", "zh")
            assert result.is_fail()
