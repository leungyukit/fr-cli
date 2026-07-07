"""DeFi 查询测试"""
import unittest
from unittest.mock import patch

from fr_cli.weapon.defi import (
    list_protocols, get_protocol, list_yields, get_pool,
    _human_tvl, _human_apy,
    format_protocols, format_protocol_detail, format_yields,
)


class TestHumanize(unittest.TestCase):
    def test_tvl_zero(self):
        self.assertEqual(_human_tvl(0), "$0")

    def test_tvl_k(self):
        self.assertIn("K", _human_tvl(5_000))

    def test_tvl_m(self):
        self.assertIn("M", _human_tvl(5_000_000))

    def test_tvl_b(self):
        self.assertIn("B", _human_tvl(5_000_000_000))

    def test_apy(self):
        self.assertIn("%", _human_apy(5.5))
        self.assertIn("?", _human_apy(None))
        # > 100 用 .1f
        self.assertEqual(_human_apy(150.0), "150.0%")


class TestListProtocols(unittest.TestCase):
    @patch("fr_cli.weapon.defi._http_get")
    def test_success(self, mock_get):
        mock_get.return_value = {
            "ok": True,
            "data": [
                {"id": "aave", "name": "Aave", "category": "Lending",
                 "tvl": 5_000_000_000, "chain": "Ethereum"},
                {"id": "uniswap", "name": "Uniswap", "category": "Dexes",
                 "tvl": 3_000_000_000, "chain": "Multi-Chain"},
            ]
        }
        r = list_protocols()
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["protocols"]), 2)
        # 应该按 TVL 排序
        self.assertEqual(r["protocols"][0]["id"], "aave")

    @patch("fr_cli.weapon.defi._http_get")
    def test_filter_category(self, mock_get):
        mock_get.return_value = {
            "ok": True,
            "data": [
                {"id": "aave", "name": "Aave", "category": "Lending", "tvl": 100, "chain": "Eth"},
                {"id": "uni", "name": "Uniswap", "category": "Dexes", "tvl": 50, "chain": "Eth"},
            ]
        }
        r = list_protocols(category="Lending")
        self.assertEqual(len(r["protocols"]), 1)
        self.assertEqual(r["protocols"][0]["id"], "aave")

    @patch("fr_cli.weapon.defi._http_get")
    def test_fail(self, mock_get):
        mock_get.return_value = {"ok": False, "error": "x"}
        r = list_protocols()
        self.assertFalse(r["ok"])
        self.assertEqual(r["protocols"], [])


class TestGetProtocol(unittest.TestCase):
    @patch("fr_cli.weapon.defi._http_get")
    def test_success(self, mock_get):
        mock_get.return_value = {
            "ok": True,
            "data": {
                "id": "aave", "name": "Aave", "category": "Lending",
                "chain": "Ethereum", "tvl": 5e9,
                "chainTvls": {"Ethereum": 4e9, "Polygon": 1e9},
                "change_1d": 1.5, "change_7d": -2.3,
            }
        }
        r = get_protocol("aave")
        self.assertTrue(r["ok"])
        self.assertEqual(r["name"], "Aave")

    @patch("fr_cli.weapon.defi._http_get")
    def test_fail(self, mock_get):
        mock_get.return_value = {"ok": False, "error": "not found"}
        r = get_protocol("nope")
        self.assertFalse(r["ok"])


class TestListYields(unittest.TestCase):
    @patch("fr_cli.weapon.defi._http_get")
    def test_success(self, mock_get):
        mock_get.return_value = {
            "ok": True,
            "data": {
                "data": [
                    {"pool": "p1", "project": "aave", "symbol": "USDC",
                     "chain": "Ethereum", "apy": 5.5, "apyBase": 3.0,
                     "apyReward": 2.5, "tvlUsd": 100_000_000},
                ]
            }
        }
        r = list_yields()
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["pools"]), 1)

    @patch("fr_cli.weapon.defi._http_get")
    def test_filter(self, mock_get):
        mock_get.return_value = {
            "ok": True,
            "data": {
                "data": [
                    {"pool": "p1", "project": "aave", "symbol": "USDC",
                     "chain": "Ethereum", "apy": 5.5, "tvlUsd": 1_000_000},
                    {"pool": "p2", "project": "aave", "symbol": "USDT",
                     "chain": "Polygon", "apy": 6.0, "tvlUsd": 500},
                ]
            }
        }
        r = list_yields(chain="Ethereum", min_tvl=10_000)
        self.assertEqual(len(r["pools"]), 1)
        self.assertEqual(r["pools"][0]["pool"], "p1")

    @patch("fr_cli.weapon.defi._http_get")
    def test_sort_by_tvl(self, mock_get):
        mock_get.return_value = {
            "ok": True,
            "data": {
                "data": [
                    {"pool": "p1", "project": "x", "symbol": "A",
                     "chain": "Eth", "apy": 10.0, "tvlUsd": 1000},
                    {"pool": "p2", "project": "y", "symbol": "B",
                     "chain": "Eth", "apy": 5.0, "tvlUsd": 5000},
                ]
            }
        }
        r = list_yields(sort_by="tvl")
        # 按 TVL 倒序:p2 > p1
        self.assertEqual(r["pools"][0]["pool"], "p2")


class TestGetPool(unittest.TestCase):
    @patch("fr_cli.weapon.defi._http_get")
    def test_found(self, mock_get):
        mock_get.return_value = {
            "ok": True,
            "data": {"data": [
                {"pool": "abc123", "project": "x", "apy": 5.0, "tvlUsd": 1000}
            ]}
        }
        r = get_pool("abc123")
        self.assertTrue(r["ok"])

    @patch("fr_cli.weapon.defi._http_get")
    def test_not_found(self, mock_get):
        mock_get.return_value = {
            "ok": True,
            "data": {"data": []}
        }
        r = get_pool("nope")
        self.assertFalse(r["ok"])


class TestFormat(unittest.TestCase):
    def test_format_protocols(self):
        result = {
            "ok": True,
            "protocols": [
                {"name": "Aave", "category": "Lending", "tvl": 5e9, "chain": "Eth",
                 "change_1d": 1.5}
            ]
        }
        out = format_protocols(result, lang="zh")
        self.assertIn("Aave", out)
        self.assertIn("Lending", out)
        self.assertIn("📈", out)  # 上升

    def test_format_protocols_empty(self):
        out = format_protocols({"ok": True, "protocols": []})
        self.assertIn("没有匹配", out)

    def test_format_protocol_detail(self):
        result = {
            "ok": True,
            "name": "Uniswap", "category": "Dexes", "chain": "Multi-Chain",
            "tvl": 5e9, "chainTvls": {"Ethereum": 3e9, "Arbitrum": 1e9},
            "change_1d": 0.5, "change_7d": -1.0,
        }
        out = format_protocol_detail(result, lang="zh")
        self.assertIn("Uniswap", out)
        self.assertIn("Ethereum", out)

    def test_format_yields(self):
        result = {
            "ok": True,
            "pools": [
                {"project": "aave", "symbol": "USDC", "chain": "Eth",
                 "apy": 5.5, "apyBase": 3.0, "apyReward": 2.5,
                 "tvlUsd": 100_000_000, "pool": "abc12345..."}
            ]
        }
        out = format_yields(result, lang="zh")
        self.assertIn("aave", out)
        self.assertIn("USDC", out)
        self.assertIn("APY", out)


if __name__ == "__main__":
    unittest.main()
