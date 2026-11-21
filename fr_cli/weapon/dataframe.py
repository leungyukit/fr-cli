"""
数据文件读取器 —— Excel / CSV 分析工具
支持读取表格文件并提交给大模型进行智能分析。
"""

def _try_import_pandas():
    try:
        import pandas as pd
        return pd
    except ImportError:
        return None


def read_excel(path, max_rows=1000, lang="zh", vfs=None):
    """读取 Excel 文件，返回文本摘要。如果传入 vfs，先校验路径在沙盒内。"""
    if vfs is not None:
        result = vfs.check(path)
        if result.is_fail():
            return None, result.error or "路径不在允许范围内"
    pd = _try_import_pandas()
    if not pd:
        return None, "缺少 pandas/openpyxl (pip install pandas openpyxl)"
    try:
        df = pd.read_excel(path, nrows=max_rows)
        return _df_to_summary(df, path, lang), None
    except Exception as e:
        return None, str(e)


def read_csv(path, max_rows=1000, lang="zh", vfs=None):
    """读取 CSV 文件，返回文本摘要。如果传入 vfs，先校验路径在沙盒内。"""
    if vfs is not None:
        result = vfs.check(path)
        if result.is_fail():
            return None, result.error or "路径不在允许范围内"
    pd = _try_import_pandas()
    if not pd:
        return None, "缺少 pandas (pip install pandas)"
    try:
        df = pd.read_csv(path, nrows=max_rows)
        return _df_to_summary(df, path, lang), None
    except Exception as e:
        return None, str(e)


def _df_to_summary(df, path, lang):
    """将 DataFrame 转换为文本摘要，供 LLM 分析"""
    lines = []
    lines.append(f"文件: {path}")
    lines.append(f"总行数: {len(df)}")
    lines.append(f"总列数: {len(df.columns)}")
    lines.append(f"列名: {list(df.columns)}")
    lines.append("")
    lines.append("数据类型:")
    for col in df.columns:
        dtype = str(df[col].dtype)
        non_null = df[col].notna().sum()
        unique = df[col].nunique()
        lines.append(f"  {col}: {dtype} | 非空: {non_null} | 唯一值: {unique}")
    lines.append("")
    lines.append("前10行预览:")
    lines.append(df.head(10).to_string(index=False))
    lines.append("")
    lines.append("数值列统计:")
    try:
        desc = df.describe().to_string()
        lines.append(desc)
    except Exception:
        pass
    return "\n".join(lines)


