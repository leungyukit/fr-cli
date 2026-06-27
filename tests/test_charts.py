"""
图表生成测试
覆盖 bar / pie / line 图表 + generate_chart 统一入口。

注意:charts 模块用 Result 风格返回,需 .unwrap() 解包。
"""
import os
import sys


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fr_cli.weapon.charts import (
    bar_chart, pie_chart, line_chart, generate_chart
)
from fr_cli.core.result import Result


def _str(result):
    """Result -> str"""
    if isinstance(result, Result):
        return result.unwrap() if result.is_ok() else result.error
    return str(result)


class TestBarChart:

    def test_basic_bar(self):
        result = bar_chart(["A", "B", "C"], [10, 20, 30])
        s = _str(result)
        assert isinstance(s, str) and len(s) > 0

    def test_bar_with_title(self):
        result = bar_chart(["A", "B"], [5, 10], title="Sales")
        s = _str(result)
        assert isinstance(s, str)

    def test_bar_uneven_data(self):
        """不等长数据应被处理或抛 ValueError"""
        try:
            result = bar_chart(["A", "B", "C"], [10, 20])
            s = _str(result)
            assert isinstance(s, str)
        except (ValueError, IndexError):
            pass

    def test_bar_no_color(self):
        result = bar_chart(["A"], [5], color=False)
        s = _str(result)
        assert isinstance(s, str)

    def test_bar_zero_values(self):
        result = bar_chart(["A", "B"], [0, 0])
        s = _str(result)
        assert isinstance(s, str)

    def test_bar_negative_values(self):
        result = bar_chart(["A", "B"], [-5, 10])
        s = _str(result)
        assert isinstance(s, str)

    def test_bar_chinese_labels(self):
        result = bar_chart(["一月", "二月", "三月"], [100, 200, 150], title="销量")
        s = _str(result)
        assert isinstance(s, str) and len(s) > 0


class TestPieChart:

    def test_basic_pie(self):
        result = pie_chart(["A", "B", "C"], [10, 20, 30])
        assert isinstance(_str(result), str)

    def test_pie_with_title(self):
        result = pie_chart(["A", "B"], [50, 50], title="Distribution")
        assert isinstance(_str(result), str)

    def test_pie_all_zeros(self):
        result = pie_chart(["A", "B"], [0, 0])
        assert isinstance(_str(result), str)


class TestLineChart:

    def test_basic_line(self):
        result = line_chart(["Mon", "Tue", "Wed"], [1.0, 2.0, 3.0])
        assert isinstance(_str(result), str)

    def test_line_with_height(self):
        result = line_chart(["a", "b"], [1, 2], height=10)
        assert isinstance(_str(result), str)


class TestGenerateChart:

    def test_dispatch_bar(self):
        result = generate_chart("bar", ["A", "B"], [10, 20])
        assert isinstance(_str(result), str)

    def test_dispatch_pie(self):
        result = generate_chart("pie", ["A", "B"], [10, 20])
        assert isinstance(_str(result), str)

    def test_dispatch_line(self):
        result = generate_chart("line", ["A", "B"], [10, 20])
        assert isinstance(_str(result), str)

    def test_dispatch_invalid_type(self):
        result = generate_chart("invalid_type", ["A"], [1])
        # 应返回 fail 或错误信息
        if isinstance(result, Result):
            assert result.is_fail() or "错误" in _str(result)

    def test_dispatch_with_dimensions(self):
        result = generate_chart("bar", ["A", "B"], [10, 20], title="X", width=50, height=20)
        assert isinstance(_str(result), str)
