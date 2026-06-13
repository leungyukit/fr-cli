"""
注册表分组：图表生成工具
- generate_chart
"""
from fr_cli.command.registry import register


@register(
    name="generate_chart",
    triggers=["图表", "柱状图", "饼图", "趋势图", "折线图", "chart", "graph"],
    description="生成控制台文本图表（柱状图/饼图/折线图）",
    params={"type": str, "labels": list, "values": list},
    security="sec_read",
    aliases=["/chart"],
)
def _generate_chart(deps, **kwargs):
    from fr_cli.weapon.charts import generate_chart

    chart_type = kwargs.get("type", "bar")
    labels = kwargs.get("labels", [])
    values = kwargs.get("values", [])
    title = kwargs.get("title")
    width = kwargs.get("width")
    height = kwargs.get("height")

    # 安全校验：限制最大尺寸，防止恶意输入导致过大输出
    if width is not None:
        try:
            width = min(int(width), 120)
        except (ValueError, TypeError):
            width = None
    if height is not None:
        try:
            height = min(int(height), 40)
        except (ValueError, TypeError):
            height = None

    result = generate_chart(
        chart_type, labels, values,
        title=title,
        width=width,
        height=height,
        color=getattr(deps, "color_enabled", True),
    )
    return result
