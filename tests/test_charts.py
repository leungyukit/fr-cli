"""
控制台图表生成模块测试
"""



class TestBarChart:
    """测试柱状图"""

    def test_bar_chart_output(self):
        from fr_cli.weapon.charts import bar_chart
        result = bar_chart(["A", "B", "C"], [10, 20, 30], title="销售", color=False)
        assert result.is_ok()
        chart = result.unwrap()
        assert "销售" in chart
        assert "A" in chart
        assert "B" in chart
        assert "C" in chart
        assert "30" in chart

    def test_bar_chart_mismatched_length(self):
        from fr_cli.weapon.charts import bar_chart
        result = bar_chart(["A", "B"], [1], color=False)
        assert result.is_fail()

    def test_bar_chart_empty(self):
        from fr_cli.weapon.charts import bar_chart
        result = bar_chart([], [], color=False)
        assert result.is_fail()


class TestPieChart:
    """测试饼图"""

    def test_pie_chart_output(self):
        from fr_cli.weapon.charts import pie_chart
        result = pie_chart(["A", "B", "C"], [10, 20, 30], title="占比", color=False)
        assert result.is_ok()
        chart = result.unwrap()
        assert "占比" in chart
        assert "A:" in chart
        assert "B:" in chart
        assert "C:" in chart
        # 检查百分比
        assert "16.7%" in chart or "16.6%" in chart
        assert "33.3%" in chart or "33.4%" in chart
        assert "50.0%" in chart

    def test_pie_chart_zero_total(self):
        from fr_cli.weapon.charts import pie_chart
        result = pie_chart(["A", "B"], [0, 0], color=False)
        assert result.is_fail()


class TestLineChart:
    """测试折线图"""

    def test_line_chart_output(self):
        from fr_cli.weapon.charts import line_chart
        result = line_chart(["1", "2", "3", "4"], [10, 20, 15, 30], title="趋势", color=False)
        assert result.is_ok()
        chart = result.unwrap()
        assert "趋势" in chart
        # 应该有坐标轴
        assert "│" in chart
        assert "└" in chart

    def test_line_chart_too_few_points(self):
        from fr_cli.weapon.charts import line_chart
        result = line_chart(["1"], [10], color=False)
        assert result.is_fail()


class TestGenerateChart:
    """测试统一入口"""

    def test_generate_bar(self):
        from fr_cli.weapon.charts import generate_chart
        result = generate_chart("bar", ["A", "B"], [1, 2], color=False)
        assert result.is_ok()
        assert "A" in result.unwrap()

    def test_generate_pie(self):
        from fr_cli.weapon.charts import generate_chart
        result = generate_chart("pie", ["A", "B"], [1, 2], color=False)
        assert result.is_ok()
        assert "A:" in result.unwrap()

    def test_generate_line(self):
        from fr_cli.weapon.charts import generate_chart
        result = generate_chart("line", ["1", "2", "3"], [1, 2, 3], color=False)
        assert result.is_ok()
        assert "│" in result.unwrap()

    def test_generate_unknown(self):
        from fr_cli.weapon.charts import generate_chart
        result = generate_chart("unknown", ["A"], [1], color=False)
        assert result.is_fail()


class TestRegistryParsing:
    """测试 /chart 命令参数解析"""

    def test_parse_chart_bar(self):
        from fr_cli.command.registry import get_registry
        reg = get_registry()
        kwargs = reg._parse_cmd_args(
            ["/chart", "bar", "--labels", "A,B,C", "--values", "10,20,30", "--title", "销售"],
            {"name": "generate_chart"},
            None,
        )
        assert kwargs["type"] == "bar"
        assert kwargs["labels"] == ["A", "B", "C"]
        assert kwargs["values"] == ["10", "20", "30"]
        assert kwargs["title"] == "销售"

    def test_parse_chart_line(self):
        from fr_cli.command.registry import get_registry
        reg = get_registry()
        kwargs = reg._parse_cmd_args(
            ["/chart", "line", "--labels", "1,2,3", "--values", "10,20,30", "--width", "60", "--height", "10"],
            {"name": "generate_chart"},
            None,
        )
        assert kwargs["type"] == "line"
        assert kwargs["width"] == 60
        assert kwargs["height"] == 10


class TestChartTool:
    """测试注册表工具调用"""

    def test_generate_chart_tool(self):
        from fr_cli.command.registered.charts import _generate_chart
        from types import SimpleNamespace
        deps = SimpleNamespace(color_enabled=False)
        chart, err = _generate_chart(deps, type="bar", labels=["A", "B"], values=[1, 2])
        assert err is None
        assert "A" in chart
