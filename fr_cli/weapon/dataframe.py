"""
数据卷轴读取器 —— Excel / CSV 分析神通
支持读取表格文件并提交给大模型进行智能分析。
"""

def _try_import_pandas():
    try:
        import pandas as pd
        return pd
    except ImportError:
        return None


def read_excel(path, max_rows=1000, lang="zh"):
    """读取 Excel 文件，返回文本摘要"""
    pd = _try_import_pandas()
    if not pd:
        return None, "缺少 pandas/openpyxl (pip install pandas openpyxl)"
    try:
        df = pd.read_excel(path, nrows=max_rows)
        return _df_to_summary(df, path, lang), None
    except Exception as e:
        return None, str(e)


def read_csv(path, max_rows=1000, lang="zh"):
    """读取 CSV 文件，返回文本摘要"""
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


def analyze_dataframe(path, query, client, model, lang="zh"):
    """读取表格并提交给大模型分析"""
    pd = _try_import_pandas()
    if not pd:
        return None, "缺少 pandas"

    # 根据扩展名判断类型
    ext = str(path).lower().split(".")[-1] if "." in str(path) else ""
    if ext in ("xlsx", "xls"):
        summary, err = read_excel(path, lang=lang)
    elif ext in ("csv",):
        summary, err = read_csv(path, lang=lang)
    else:
        # 尝试两种
        summary, err = read_csv(path, lang=lang)
        if err:
            summary, err = read_excel(path, lang=lang)

    if err:
        return None, err

    prompt = f"""你是一个数据分析专家。请根据以下表格数据和用户问题进行分析。

{summary}

用户问题: {query}

请用中文给出清晰、简洁的分析结果。如果涉及计算，请展示计算过程。
"""
    from fr_cli.core.stream import stream_cnt
    messages = [{"role": "user", "content": prompt}]
    result, _, _ = stream_cnt(client, model, messages, lang, custom_prefix="", max_tokens=4096)
    return result, None
