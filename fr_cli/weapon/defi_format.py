"""
DeFi 查询 —— 渲染格式化层

从 fr_cli.weapon.defi 拆出(原文件 464 行)。
本文件只做纯函数渲染(ASCII 图表 / 文本排版),不发网络请求;
网络层(_http_get + 各 API 函数)保留在 fr_cli.weapon.defi。

原 defi.py 中的公开函数通过 re-export 保持旧导入路径可用:
    from fr_cli.weapon.defi import format_protocols, render_ascii_chart, ...
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def render_ascii_chart(values: List[float], labels: Optional[List[str]] = None,
                       width: int = 50, height: int = 12,
                       title: str = "") -> str:
    """渲染 ASCII 图表(类似 sparkline)

    Args:
        values: 数据点列表
        labels: 可选标签(与 values 等长)
        width: 输出宽度(默认 50 字符)
        height: 输出高度(默认 12 行)
        title: 图表标题

    Returns:
        多行字符串
    """
    if not values:
        return f"{title}\n(no data)" if title else "(no data)"

    # 归一化
    v_min = min(values)
    v_max = max(values)
    rng = v_max - v_min if v_max > v_min else 1

    # 对每个 height 行,扫描 width 列
    lines = []
    if title:
        lines.append(title)
    lines.append(f"min: {v_min:.2f}  max: {v_max:.2f}  range: {rng:.2f}")
    lines.append("─" * width)

    # 简化为 sparkline(单行 unicode block)
    # 用 ▁▂▃▄▅▆▇█ 表示高低
    spark = "▁▂▃▄▅▆▇█"
    spark_chars = []
    for v in values:
        idx = int((v - v_min) / rng * (len(spark) - 1)) if rng else 0
        spark_chars.append(spark[idx])
    lines.append("".join(spark_chars))
    lines.append("─" * width)

    # 完整 ASCII bar chart
    n = len(values)
    if n > width:
        # 降采样
        step = n / width
        sampled = [values[int(i * step)] for i in range(width)]
    else:
        sampled = values

    # 对每个 height 行
    bar_height = height - 4  # 减掉 header/footer/spark/separator
    if bar_height < 1:
        bar_height = 1

    for row in range(bar_height, 0, -1):
        threshold = v_min + (v_max - v_min) * row / bar_height
        line = ""
        for v in sampled:
            if v >= threshold:
                line += "█"
            elif v >= threshold - (v_max - v_min) / bar_height * 0.4:
                line += "▓"
            elif v >= threshold - (v_max - v_min) / bar_height * 0.7:
                line += "▒"
            else:
                line += " "
        lines.append(line)
    lines.append("─" * width)

    # 显示范围标签
    if labels and len(labels) >= 2:
        first = labels[0]
        last = labels[-1]
        lines.append(f"{first}{' ' * (width - len(first) - len(last))}{last}")
    elif n > 1:
        lines.append(f"point 1{(' ' * (width - 14))}point {n}")

    return "\n".join(lines)


def format_pool_chart(result: Dict[str, Any], width: int = 50,
                      lang: str = "zh") -> str:
    """格式化池子历史图表为可读字符串"""
    if not result["ok"]:
        return f"❌ {result.get('error', '查询失败')}"

    data = result["data"]
    symbol = data.get("symbol", "?")
    project = data.get("project", "?")
    chain = data.get("chain", "?")
    status = data.get("status", "?")

    if status == "INACTIVE":
        return f"⏸️ 池 {symbol} ({project}/{chain}) 已下线"

    # 解析时间序列数据
    apy_data = data.get("apy", {}) or {}
    tvl_data = data.get("tvl", {}) or {}

    apy_points = apy_data.get("data", []) if isinstance(apy_data, dict) else []
    tvl_points = tvl_data.get("data", []) if isinstance(tvl_data, dict) else []

    lines = []
    if lang == "zh":
        lines.append(f"📈 {project} - {symbol} ({chain}) 历史")
    else:
        lines.append(f"📈 {project} - {symbol} ({chain}) History")

    lines.append(f"  状态: {status}")

    if apy_points:
        # APY 时间序列:[[timestamp, value], ...]
        apy_values = [p[1] if len(p) > 1 else 0 for p in apy_points if isinstance(p, list)]
        apy_dates = [
            p[0].split("T")[0] if isinstance(p, list) and len(p) > 0 and isinstance(p[0], str)
            else ""
            for p in apy_points
        ]
        if apy_values:
            current_apy = apy_values[-1] if apy_values else 0
            if lang == "zh":
                lines.append(f"  当前 APY: {current_apy:.2f}%")
            else:
                lines.append(f"  Current APY: {current_apy:.2f}%")

            chart_text = render_ascii_chart(
                apy_values, labels=apy_dates, width=width, height=14,
                title="APY (%)"
            )
            lines.append(chart_text)

    if tvl_points:
        tvl_values = [p[1] if len(p) > 1 else 0 for p in tvl_points if isinstance(p, list)]
        tvl_dates = [
            p[0].split("T")[0] if isinstance(p, list) and len(p) > 0 and isinstance(p[0], str)
            else ""
            for p in tvl_points
        ]
        if tvl_values:
            current_tvl = tvl_values[-1] if tvl_values else 0
            lines.append("")
            if lang == "zh":
                lines.append(f"  当前 TVL: {_human_tvl(current_tvl)}")
            else:
                lines.append(f"  Current TVL: {_human_tvl(current_tvl)}")

            chart_text = render_ascii_chart(
                tvl_values, labels=tvl_dates, width=width, height=14,
                title="TVL (USD)"
            )
            lines.append(chart_text)

    return "\n".join(lines)


# --------------------------- 人类可读格式化 ---------------------------

def _human_tvl(tvl: float) -> str:
    """TVL 人类可读"""
    if not tvl:
        return "$0"
    if tvl >= 1e9:
        return f"${tvl / 1e9:.2f}B"
    if tvl >= 1e6:
        return f"${tvl / 1e6:.2f}M"
    if tvl >= 1e3:
        return f"${tvl / 1e3:.2f}K"
    return f"${tvl:.2f}"


def _human_apy(apy: float) -> str:
    """APY 格式化"""
    if apy is None:
        return "?"
    if apy >= 100:
        return f"{apy:.1f}%"
    return f"{apy:.2f}%"


def format_protocols(result: Dict[str, Any], limit: int = 30, lang: str = "zh") -> str:
    """格式化协议列表"""
    if not result["ok"]:
        return f"❌ {result.get('error', '查询失败')}"

    protocols = result["protocols"][:limit]
    if not protocols:
        return "📭 没有匹配的协议"

    if lang == "zh":
        title = f"🏦 DeFi 协议 (前 {len(protocols)})"
    else:
        title = f"🏦 DeFi Protocols (top {len(protocols)})"

    lines = [title]
    for p in protocols:
        change_1d = p.get("change_1d")
        change_str = ""
        if change_1d is not None and change_1d != 0:
            emoji = "📈" if change_1d > 0 else "📉"
            change_str = f" {emoji} {change_1d:+.2f}%"

        lines.append(
            f"  • {p['name']} ({p['category']})\n"
            f"      TVL: {_human_tvl(p['tvl'])} | {p['chain']}{change_str}"
        )
    return "\n".join(lines)


def format_protocol_detail(result: Dict[str, Any], lang: str = "zh") -> str:
    """格式化协议详情"""
    if not result["ok"]:
        return f"❌ {result.get('error', '查询失败')}"

    if lang == "zh":
        lines = [f"🏦 {result['name']}"]
        lines.append(f"  类别: {result.get('category', '?')}")
        lines.append(f"  链: {result.get('chain', '?')}")
        lines.append(f"  总 TVL: {_human_tvl(result.get('tvl', 0))}")
        change_1d = result.get("change_1d")
        change_7d = result.get("change_7d")
        if change_1d is not None:
            lines.append(f"  24h: {change_1d:+.2f}%")
        if change_7d is not None:
            lines.append(f"  7d: {change_7d:+.2f}%")

        chain_tvls = result.get("chainTvls", {})
        if chain_tvls:
            lines.append("  按链 TVL:")
            for chain, tvl in sorted(chain_tvls.items(), key=lambda x: x[1], reverse=True)[:5]:
                lines.append(f"    • {chain}: {_human_tvl(tvl)}")
        return "\n".join(lines)
    return str(result)


def format_yields(result: Dict[str, Any], lang: str = "zh") -> str:
    """格式化收益池列表"""
    if not result["ok"]:
        return f"❌ {result.get('error', '查询失败')}"

    pools = result["pools"]
    if not pools:
        return "📭 没有匹配的池子"

    if lang == "zh":
        title = f"💰 收益池 (前 {len(pools)})"
    else:
        title = f"💰 Yield Pools (top {len(pools)})"

    lines = [title]
    for p in pools:
        apy = p.get("apy", 0) or 0
        apy_base = p.get("apyBase", 0) or 0
        apy_reward = p.get("apyReward", 0) or 0
        tvl = p.get("tvlUsd", 0) or 0
        symbol = p.get("symbol", "?")
        chain = p.get("chain", "?")
        project = p.get("project", "?")
        pool_id = p.get("pool", "?")[:8]

        apy_str = f"APY {_human_apy(apy)}"
        if apy_reward > 0:
            apy_str += f" (base {_human_apy(apy_base)} + reward {_human_apy(apy_reward)})"

        lines.append(
            f"  • [{project}] {symbol} ({chain})\n"
            f"      {apy_str} | TVL {_human_tvl(tvl)}\n"
            f"      pool: {pool_id}..."
        )
    return "\n".join(lines)
