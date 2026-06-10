"""命令处理器 —— dataframe"""

from fr_cli.command.registry import register

@register(
    name="read_excel",
    triggers=["Excel", "表格", "xlsx", "读取Excel", "分析表格"],
    description="读取 Excel 文件并返回数据摘要",
    params={"path": str},
    security="sec_read",
    aliases=["/read_excel"],
)
def _read_excel(deps, **kwargs):
    from fr_cli.weapon.dataframe import read_excel
    res, err = read_excel(kwargs["path"], lang=deps.lang)
    return (res, None) if not err else (None, err)


@register(
    name="read_csv",
    triggers=["CSV", "csv", "读取CSV", "分析CSV"],
    description="读取 CSV 文件并返回数据摘要",
    params={"path": str},
    security="sec_read",
    aliases=["/read_csv"],
)
def _read_csv(deps, **kwargs):
    from fr_cli.weapon.dataframe import read_csv
    res, err = read_csv(kwargs["path"], lang=deps.lang)
    return (res, None) if not err else (None, err)


# ------------------------------------------------------------------

