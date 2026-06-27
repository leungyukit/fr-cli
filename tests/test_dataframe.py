"""
dataframe 数据读取测试
覆盖 Excel/CSV 读取、参数校验、vfs 沙盒、缺依赖处理等。

依赖 pandas + openpyxl,通过 extras 安装:
    pip install -e ".[data]"
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _have_pandas():
    try:
        import pandas  # noqa
        return True
    except ImportError:
        return False


def _have_openpyxl():
    try:
        import openpyxl  # noqa
        return True
    except ImportError:
        return False


pytestmark_data = pytest.mark.skipif(
    not _have_pandas(),
    reason="需要 pandas (pip install -e .[data])",
)


# ==================== CSV 测试 ====================

@pytest.mark.skipif(not _have_pandas(), reason="需要 pandas")
class TestReadCsv:

    def test_read_basic_csv(self, tmp_path):
        from fr_cli.weapon.dataframe import read_csv
        f = tmp_path / "data.csv"
        f.write_text("name,age\nAlice,30\nBob,25\n", encoding="utf-8")

        result, err = read_csv(str(f))
        assert err is None
        assert "Alice" in result
        assert "Bob" in result
        assert "30" in result

    def test_read_empty_csv(self, tmp_path):
        from fr_cli.weapon.dataframe import read_csv
        f = tmp_path / "empty.csv"
        f.write_text("", encoding="utf-8")

        result, err = read_csv(str(f))
        # 空文件应不崩
        assert result is not None or err is not None

    def test_read_nonexistent_csv(self):
        from fr_cli.weapon.dataframe import read_csv
        result, err = read_csv("/nonexistent/file.csv")
        # 应有 error
        assert err is not None
        assert result is None

    def test_read_csv_with_max_rows(self, tmp_path):
        from fr_cli.weapon.dataframe import read_csv
        f = tmp_path / "data.csv"
        lines = ["name,age"]
        for i in range(100):
            lines.append(f"user{i},{i + 20}")
        f.write_text("\n".join(lines), encoding="utf-8")

        result, err = read_csv(str(f), max_rows=10)
        assert err is None
        # max_rows=10 应只读前 10 行(0-9)
        assert "user0" in result
        assert "user9" in result
        # user99 不应出现
        assert "user99" not in result

    def test_read_csv_chinese_content(self, tmp_path):
        from fr_cli.weapon.dataframe import read_csv
        f = tmp_path / "data.csv"
        f.write_text("姓名,年龄\n张三,30\n李四,25\n", encoding="utf-8")

        result, err = read_csv(str(f))
        assert err is None
        assert "张三" in result or "姓名" in result

    def test_read_csv_with_vfs_rejected(self, tmp_path):
        """vfs.check 拒绝路径应返回 None + 错误"""
        from fr_cli.weapon.dataframe import read_csv
        mock_vfs = MagicMock()
        from fr_cli.core.result import Result
        mock_vfs.check.return_value = Result.fail("路径不在允许范围内")

        result, err = read_csv("/etc/passwd", vfs=mock_vfs)
        assert result is None
        assert "不在允许范围" in err or "工作区" in err or "拒绝" in err


# ==================== Excel 测试 ====================

@pytest.mark.skipif(not _have_openpyxl(), reason="需要 openpyxl")
class TestReadExcel:

    def test_read_basic_xlsx(self, tmp_path):
        import pandas as pd
        from fr_cli.weapon.dataframe import read_excel

        f = tmp_path / "data.xlsx"
        df = pd.DataFrame({"name": ["Alice", "Bob"], "age": [30, 25]})
        df.to_excel(f, index=False)

        result, err = read_excel(str(f))
        assert err is None
        assert "Alice" in result
        assert "Bob" in result

    def test_read_nonexistent_xlsx(self):
        from fr_cli.weapon.dataframe import read_excel
        result, err = read_excel("/nonexistent/file.xlsx")
        assert err is not None
        assert result is None

    def test_read_xlsx_with_vfs(self, tmp_path):
        """vfs 通过时应正常读取"""
        import pandas as pd
        from fr_cli.weapon.dataframe import read_excel

        f = tmp_path / "data.xlsx"
        pd.DataFrame({"x": [1, 2, 3]}).to_excel(f, index=False)

        mock_vfs = MagicMock()
        from fr_cli.core.result import Result
        mock_vfs.check.return_value = Result.ok("ok")

        result, err = read_excel(str(f), vfs=mock_vfs)
        assert err is None
        assert result is not None


# ==================== 缺依赖测试(不需要 pandas) ====================

class TestMissingDependency:

    """这些测试在 pandas 装了时也应通过(测 API 行为),不直接依赖 pandas"""

    def test_read_csv_returns_tuple(self):
        """read_csv 应返回 (result, err) 元组"""
        from fr_cli.weapon.dataframe import read_csv
        ret = read_csv("/nonexistent.csv")
        assert isinstance(ret, tuple)
        assert len(ret) == 2

    def test_read_excel_returns_tuple(self):
        from fr_cli.weapon.dataframe import read_excel
        ret = read_excel("/nonexistent.xlsx")
        assert isinstance(ret, tuple)
        assert len(ret) == 2
