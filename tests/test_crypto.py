"""Crypto wallet 测试(只读查询,不联网的部分)"""
import json
import unittest
from unittest.mock import patch

from fr_cli.weapon.crypto import (
    get_balance, format_balance, get_transactions, format_transactions,
    get_price, format_price, resolve_symbol,
    PUBLIC_RPCS, CHAIN_IDS, SYMBOL_TO_COINGECKO, WEI_PER_ETH,
)


VALID_ADDR = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb1"


class TestResolveSymbol(unittest.TestCase):
    def test_known(self):
        self.assertEqual(resolve_symbol("ETH"), "ethereum")
        self.assertEqual(resolve_symbol("BTC"), "bitcoin")
        self.assertEqual(resolve_symbol("USDT"), "tether")

    def test_case_insensitive(self):
        self.assertEqual(resolve_symbol("eth"), "ethereum")
        self.assertEqual(resolve_symbol("Eth"), "ethereum")

    def test_unknown(self):
        self.assertEqual(resolve_symbol("xxx_unknown"), "xxx_unknown")


class TestGetBalanceValidation(unittest.TestCase):
    """测试余额查询的参数校验(不联网)"""

    def test_invalid_address_no_prefix(self):
        r = get_balance("742d35Cc6634C0532925a3b844Bc9e7595f0bEb1")
        self.assertFalse(r["ok"])

    def test_empty_address(self):
        r = get_balance("")
        self.assertFalse(r["ok"])

    def test_short_address(self):
        r = get_balance("0xabc")
        self.assertFalse(r["ok"])

    def test_unsupported_chain(self):
        r = get_balance(VALID_ADDR, chain="unknown_chain")
        self.assertFalse(r["ok"])


class TestGetBalanceRPC(unittest.TestCase):
    @patch("fr_cli.weapon.crypto._http_post_json")
    def test_success(self, mock_post):
        # 1.5 ETH = 1.5 * 10^18 wei = 0x14d1120d7b160000
        mock_post.return_value = {
            "ok": True,
            "data": {"jsonrpc": "2.0", "id": 1, "result": "0x14d1120d7b160000"}
        }
        r = get_balance(VALID_ADDR, chain="eth")
        self.assertTrue(r["ok"])
        self.assertEqual(r["chain"], "eth")
        self.assertEqual(r["chain_id"], 1)
        self.assertEqual(r["balance_eth"], 1.5)
        self.assertEqual(r["balance"], "1.50000000")

    @patch("fr_cli.weapon.crypto._http_post_json")
    def test_zero_balance(self, mock_post):
        mock_post.return_value = {
            "ok": True,
            "data": {"result": "0x0"}
        }
        r = get_balance(VALID_ADDR)
        self.assertTrue(r["ok"])
        self.assertEqual(r["balance_eth"], 0.0)

    @patch("fr_cli.weapon.crypto._http_post_json")
    def test_rpc_error(self, mock_post):
        mock_post.return_value = {"ok": False, "error": "connection refused"}
        r = get_balance(VALID_ADDR)
        self.assertFalse(r["ok"])

    @patch("fr_cli.weapon.crypto._http_post_json")
    def test_invalid_hex(self, mock_post):
        mock_post.return_value = {
            "ok": True,
            "data": {"result": "not-a-hex"}
        }
        r = get_balance(VALID_ADDR)
        self.assertFalse(r["ok"])

    def test_custom_rpc(self):
        with patch("fr_cli.weapon.crypto._http_post_json") as mock_post:
            mock_post.return_value = {"ok": True, "data": {"result": "0x0"}}
            r = get_balance(VALID_ADDR, chain="eth", rpc_url="http://custom:8545")
            self.assertTrue(r["ok"])
            # 验证用的是 custom url
            args = mock_post.call_args
            self.assertEqual(args[0][0], "http://custom:8545")


class TestFormatBalance(unittest.TestCase):
    def test_success_zh(self):
        result = {
            "ok": True,
            "address": VALID_ADDR,
            "chain": "eth",
            "chain_id": 1,
            "balance": "1.50000000",
            "balance_eth": 1.5,
            "balance_wei": 1500000000000000000,
        }
        out = format_balance(result, "zh")
        self.assertIn("余额", out)
        self.assertIn("ETH", out)

    def test_fail(self):
        out = format_balance({"ok": False, "error": "网络失败"}, "zh")
        self.assertIn("❌", out)
        self.assertIn("网络失败", out)


class TestGetTransactionsValidation(unittest.TestCase):
    @patch("fr_cli.weapon.crypto._http_get")
    def test_invalid_address(self, mock_get):
        r = get_transactions("bad-address")
        self.assertFalse(r["ok"])

    @patch("fr_cli.weapon.crypto._http_get")
    def test_unsupported_chain(self, mock_get):
        r = get_transactions(VALID_ADDR, chain="unknown")
        self.assertFalse(r["ok"])

    @patch("fr_cli.weapon.crypto._http_get")
    def test_no_transactions(self, mock_get):
        mock_get.return_value = {
            "ok": True,
            "data": {"status": "0", "message": "No transactions found", "result": "No transactions found"}
        }
        r = get_transactions(VALID_ADDR)
        self.assertTrue(r["ok"])
        self.assertEqual(r["txs"], [])

    @patch("fr_cli.weapon.crypto._http_get")
    def test_invalid_api_key(self, mock_get):
        mock_get.return_value = {
            "ok": True,
            "data": {"status": "0", "result": "Invalid API Key"}
        }
        r = get_transactions(VALID_ADDR)
        self.assertFalse(r["ok"])
        self.assertIn("key", r["error"].lower())

    @patch("fr_cli.weapon.crypto._http_get")
    def test_success(self, mock_get):
        mock_get.return_value = {
            "ok": True,
            "data": {
                "status": "1",
                "result": [
                    {
                        "hash": "0x" + "a" * 64,
                        "from": "0x" + "b" * 40,
                        "to": "0x" + "c" * 40,
                        "value": str(int(0.5 * WEI_PER_ETH)),
                        "timeStamp": "1700000000",
                    }
                ]
            }
        }
        r = get_transactions(VALID_ADDR, limit=10)
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["txs"]), 1)
        self.assertEqual(r["txs"][0]["hash"], "0x" + "a" * 64)


class TestFormatTransactions(unittest.TestCase):
    def test_empty(self):
        out = format_transactions({"ok": True, "txs": []}, "zh")
        self.assertIn("没有交易", out)

    def test_fail(self):
        out = format_transactions({"ok": False, "error": "x"}, "zh")
        self.assertIn("❌", out)


class TestGetPrice(unittest.TestCase):
    @patch("fr_cli.weapon.crypto._http_get")
    def test_success(self, mock_get):
        mock_get.return_value = {
            "ok": True,
            "data": {"ethereum": {"usd": 3000.5}}
        }
        r = get_price("ethereum", "usd")
        self.assertTrue(r["ok"])
        self.assertEqual(r["price"], 3000.5)

    @patch("fr_cli.weapon.crypto._http_get")
    def test_unknown_symbol(self, mock_get):
        mock_get.return_value = {"ok": True, "data": {}}
        r = get_price("unknown_xyz", "usd")
        self.assertFalse(r["ok"])

    @patch("fr_cli.weapon.crypto._http_get")
    def test_no_vs_currency(self, mock_get):
        mock_get.return_value = {
            "ok": True,
            "data": {"ethereum": {}}
        }
        r = get_price("ethereum", "usd")
        self.assertFalse(r["ok"])

    @patch("fr_cli.weapon.crypto._http_get")
    def test_http_fail(self, mock_get):
        mock_get.return_value = {"ok": False, "error": "rate limit"}
        r = get_price("ethereum", "usd")
        self.assertFalse(r["ok"])


class TestFormatPrice(unittest.TestCase):
    def test_success(self):
        out = format_price({"ok": True, "symbol": "ethereum", "vs_currency": "usd", "price": 3000})
        # price 3000 用千分位格式化为 "3,000.0000"
        self.assertIn("3,000", out)
        self.assertIn("USD", out)

    def test_fail(self):
        out = format_price({"ok": False, "error": "x"})
        self.assertIn("❌", out)


class TestConstants(unittest.TestCase):
    def test_public_rpcs(self):
        self.assertIn("eth", PUBLIC_RPCS)
        self.assertIn("bsc", PUBLIC_RPCS)
        self.assertIn("polygon", PUBLIC_RPCS)

    def test_chain_ids(self):
        self.assertEqual(CHAIN_IDS["eth"], 1)
        self.assertEqual(CHAIN_IDS["bsc"], 56)
        self.assertEqual(CHAIN_IDS["polygon"], 137)

    def test_symbol_mapping(self):
        self.assertEqual(SYMBOL_TO_COINGECKO["ETH"], "ethereum")
        self.assertEqual(SYMBOL_TO_COINGECKO["BTC"], "bitcoin")

    def test_wei_per_eth(self):
        self.assertEqual(WEI_PER_ETH, 10**18)


class TestSetApiKey(unittest.TestCase):
    @patch("fr_cli.conf.config.save_config")
    @patch("fr_cli.conf.config.load_config")
    def test_set(self, mock_load, mock_save):
        mock_load.return_value = {}
        from fr_cli.weapon.crypto import set_api_key
        self.assertTrue(set_api_key("my_key"))


if __name__ == "__main__":
    unittest.main()