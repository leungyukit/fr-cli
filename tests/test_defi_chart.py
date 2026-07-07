"""DeFi 历史 APY 图表测试"""
import unittest
from unittest.mock import patch

from fr_cli.weapon.defi import (
    get_pool_chart, render_ascii_chart, format_pool_chart,
)


class TestAsciiChart(unittest.TestCase):
    def test_empty(self):
        out = render_ascii_chart([], width=30, height=8)
        self.assertIn("no data", out)

    def test_basic(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        out = render_ascii_chart(values, width=20, height=10, title="Test")
        self.assertIn("Test", out)
        self.assertIn("min: 1.00", out)
        self.assertIn("max: 5.00", out)
        # 应该包含 sparkline 字符
        self.assertIn("█", out)

    def test_with_labels(self):
        values = [1, 2, 3, 4, 5]
        labels = ["2024-01", "2024-02", "2024-03", "2024-04", "2024-05"]
        out = render_ascii_chart(values, labels=labels, width=20, height=8)
        self.assertIn("2024-01", out)
        self.assertIn("2024-05", out)

    def test_long_series_downsample(self):
        # 比 width 长的 series 应该降采样
        values = list(range(100))
        out = render_ascii_chart(values, width=30, height=8)
        self.assertIn("min:", out)
        self.assertIn("max:", out)


class TestGetPoolChart(unittest.TestCase):
    @patch("fr_cli.weapon.defi._http_get")
    def test_success(self, mock_get):
        mock_get.return_value = {
            "ok": True,
            "data": {
                "status": "ACTIVE",
                "symbol": "USDC",
                "project": "aave",
                "chain": "Ethereum",
                "apy": {"data": [["2024-01-01", 3.0], ["2024-02-01", 4.0], ["2024-03-01", 5.0]]},
                "tvl": {"data": [["2024-01-01", 1000], ["2024-02-01", 2000], ["2024-03-01", 3000]]},
            }
        }
        r = get_pool_chart("uuid-123")
        self.assertTrue(r["ok"])

    @patch("fr_cli.weapon.defi._http_get")
    def test_fail(self, mock_get):
        mock_get.return_value = {"ok": False, "error": "x"}
        r = get_pool_chart("uuid")
        self.assertFalse(r["ok"])


class TestFormatPoolChart(unittest.TestCase):
    def test_inactive(self):
        r = {"ok": True, "data": {"status": "INACTIVE", "symbol": "X", "project": "p", "chain": "c"}}
        out = format_pool_chart(r, lang="zh")
        self.assertIn("已下线", out)

    def test_active(self):
        r = {
            "ok": True,
            "data": {
                "status": "ACTIVE",
                "symbol": "USDC",
                "project": "aave",
                "chain": "Ethereum",
                "apy": {"data": [
                    ["2024-01-01T00:00:00Z", 3.0],
                    ["2024-02-01T00:00:00Z", 4.0],
                    ["2024-03-01T00:00:00Z", 5.0],
                ]},
                "tvl": {"data": [
                    ["2024-01-01T00:00:00Z", 1_000_000],
                    ["2024-02-01T00:00:00Z", 2_000_000],
                    ["2024-03-01T00:00:00Z", 3_000_000],
                ]},
            }
        }
        out = format_pool_chart(r, lang="zh", width=30)
        self.assertIn("aave", out)
        self.assertIn("USDC", out)
        self.assertIn("当前 APY", out)
        self.assertIn("当前 TVL", out)
        # 应该有 sparkline + bar chart
        self.assertIn("█", out)

    def test_fail(self):
        r = {"ok": False, "error": "x"}
        out = format_pool_chart(r, lang="zh")
        self.assertIn("❌", out)


if __name__ == "__main__":
    unittest.main()
