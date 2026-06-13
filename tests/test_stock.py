"""
StockShareAgent 股票/量化助手测试
"""
import pytest
from unittest.mock import patch, MagicMock
from types import SimpleNamespace


class TestStockConfig:
    """测试股票配置加载"""

    @patch("fr_cli.agent.builtins.stock.load_namespace")
    def test_load_stock_cfg_default(self, mock_load):
        from fr_cli.agent.builtins.stock import _load_stock_cfg
        mock_load.return_value = {}
        cfg = _load_stock_cfg()
        assert cfg["default_source"] == "akshare"
        assert cfg["akshare"]["enabled"] is True
        assert cfg["mairui"]["enabled"] is False
        assert cfg["portfolio"] == {}


class TestStockCode:
    """测试股票代码规范化"""

    def test_normalize_sh(self):
        from fr_cli.agent.builtins.stock import _normalize_code
        assert _normalize_code("600519") == "600519.SH"

    def test_normalize_sz(self):
        from fr_cli.agent.builtins.stock import _normalize_code
        assert _normalize_code("000001") == "000001.SZ"

    def test_normalize_with_suffix(self):
        from fr_cli.agent.builtins.stock import _normalize_code
        assert _normalize_code("00700.HK") == "00700.HK"


class TestStockDataSources:
    """测试各数据源调用"""

    def test_query_akshare_quote(self):
        from fr_cli.agent.builtins.stock import _query_akshare_quote
        from unittest.mock import MagicMock, patch

        row = MagicMock()
        row.get.side_effect = lambda key, default=None: {
            "代码": "600519",
            "名称": "贵州茅台",
            "最新价": 1500.0,
            "今开": 1490.0,
            "最高": 1510.0,
            "最低": 1480.0,
            "昨收": 1485.0,
            "成交量": 10000,
            "成交额": 15000000.0,
            "涨跌幅": 1.01,
        }.get(key, default)
        row.__getitem__ = row.get

        filtered = MagicMock()
        filtered.empty = False
        filtered.iloc = [row]

        df = MagicMock()
        df.__getitem__.return_value = filtered

        mock_ak = MagicMock()
        mock_ak.stock_zh_a_spot_em.return_value = df
        with patch("fr_cli.agent.builtins.stock.HAS_AKSHARE", True), \
             patch("fr_cli.agent.builtins.stock.ak", mock_ak):
            result, err = _query_akshare_quote("600519.SH")
        assert err is None
        assert result["name"] == "贵州茅台"
        assert result["price"] == 1500.0

    def test_query_akshare_quote_no_akshare(self):
        from fr_cli.agent.builtins.stock import _query_akshare_quote
        with patch.dict("sys.modules", {"akshare": None}):
            with pytest.raises(ImportError):
                _query_akshare_quote("600519.SH")

    @patch("fr_cli.agent.builtins.stock.requests.get")
    def test_query_mairui(self, mock_get):
        from fr_cli.agent.builtins.stock import _query_mairui
        mock_get.return_value = MagicMock(json=lambda: {"code": "600519", "price": 1500.0}, raise_for_status=lambda: None)
        cfg = {"key": "mr-test", "base_url": "https://api.test.com"}
        result, err = _query_mairui("600519.SH", "hsrl/600519", cfg)
        assert err is None
        assert result["source"] == "mairui"

    def test_query_tushare(self):
        from fr_cli.agent.builtins.stock import _query_tushare
        from unittest.mock import MagicMock, patch
        fake_df = MagicMock()
        fake_df.empty = False
        fake_df.to_dict.return_value = [{"ts_code": "600519.SH", "close": 1500.0}]
        mock_pro = MagicMock()
        mock_pro.query.return_value = fake_df
        mock_ts = MagicMock()
        mock_ts.pro_api.return_value = mock_pro
        with patch("fr_cli.agent.builtins.stock.HAS_TUSHARE", True), \
             patch("fr_cli.agent.builtins.stock.ts", mock_ts):
            result, err = _query_tushare("600519.SH", "ts-test", api_name="daily")
        assert err is None
        assert result["source"] == "tushare"


class TestSimulateTrade:
    """测试模拟交易"""

    @patch("fr_cli.agent.builtins.stock._save_stock_cfg")
    def test_buy_and_sell(self, mock_save):
        from fr_cli.agent.builtins.stock import _simulate_trade
        cfg = {"portfolio": {}}
        result = _simulate_trade(cfg, "600519.SH", "buy", 100, 1500.0)
        assert result.is_ok()
        assert cfg["portfolio"]["600519.SH"]["quantity"] == 100

        result = _simulate_trade(cfg, "600519.SH", "sell", 50, 1600.0)
        assert result.is_ok()
        assert cfg["portfolio"]["600519.SH"]["quantity"] == 50

    @patch("fr_cli.agent.builtins.stock._save_stock_cfg")
    def test_sell_not_enough(self, mock_save):
        from fr_cli.agent.builtins.stock import _simulate_trade
        cfg = {"portfolio": {"600519.SH": {"quantity": 10, "cost": 1500.0}}}
        result = _simulate_trade(cfg, "600519.SH", "sell", 100, 1600.0)
        assert result.is_fail()
        assert "持仓不足" in result.error


class TestDispatchBuiltin:
    """测试 @ 调度器内置 Agent 路由"""

    @patch("fr_cli.agent.builtins.stock.handle_stock")
    def test_dispatch_stock_builtin(self, mock_handle_stock):
        from fr_cli.agent.dispatch import dispatch_agent_call
        state = SimpleNamespace()
        result = dispatch_agent_call(state, "@stock 查询茅台股价")
        assert result is True
        mock_handle_stock.assert_called_once()


class TestStockConfigCommand:
    """测试 /stock_config 命令"""

    @patch("fr_cli.repl.commands.stock._load_stock_cfg")
    @patch("fr_cli.repl.commands.stock._save_stock_cfg")
    def test_cmd_stock_config_show(self, mock_save, mock_load, capsys):
        from fr_cli.repl.commands.stock import _cmd_stock_config
        mock_load.return_value = {
            "default_source": "akshare",
            "akshare": {"enabled": True},
            "mairui": {"enabled": False, "key": ""},
        }
        state = SimpleNamespace()
        _cmd_stock_config(state, ["/stock_config"])
        captured = capsys.readouterr()
        assert "akshare" in captured.out

    @patch("fr_cli.repl.commands.stock._load_stock_cfg")
    @patch("fr_cli.repl.commands.stock._save_stock_cfg")
    def test_cmd_stock_config_source(self, mock_save, mock_load):
        from fr_cli.repl.commands.stock import _cmd_stock_config
        mock_load.return_value = {"default_source": "akshare"}
        state = SimpleNamespace()
        _cmd_stock_config(state, ["/stock_config", "source", "mairui"])
        assert mock_save.called
        saved = mock_save.call_args[0][0]
        assert saved["default_source"] == "mairui"
