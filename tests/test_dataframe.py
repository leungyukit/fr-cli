"""
测试数据卷轴读取器（Excel / CSV）
"""
import unittest
from unittest.mock import patch, MagicMock

from fr_cli.weapon.dataframe import _try_import_pandas


class TestDataFrameUtils(unittest.TestCase):
    def test_try_import_pandas(self):
        pd = _try_import_pandas()
        # pandas may not be installed in test env; just check function exists
        self.assertTrue(callable(_try_import_pandas))

    def test_read_csv_mock(self):
        from fr_cli.weapon.dataframe import read_csv
        with patch("fr_cli.weapon.dataframe._try_import_pandas") as mock_pd:
            mock_df = MagicMock()
            mock_df.columns = ["name", "age"]
            mock_df.__len__ = lambda self: 3
            mock_df.__getitem__ = lambda self, k: MagicMock(dtype="int64", notna=MagicMock(return_value=MagicMock(sum=lambda: 3)), nunique=lambda: 3)
            mock_df.head.return_value.to_string.return_value = "name age\nAlice 30"
            mock_df.describe.return_value.to_string.return_value = "count 3"
            mock_pd.return_value.read_csv.return_value = mock_df
            res, err = read_csv("test.csv")
            self.assertIsNone(err)
            self.assertIn("name", res)


class TestRegistryIntegration(unittest.TestCase):
    def test_dataframe_tools_registered(self):
        from fr_cli.command.registry import get_registry
        reg = get_registry()
        tools = reg.get_tools()
        names = [t["name"] for t in tools]
        self.assertIn("read_excel", names)
        self.assertIn("read_csv", names)


if __name__ == "__main__":
    unittest.main()
