"""
DeFi 查询 —— 通过 DeFi Llama API(免 key)

DeFi Llama 提供免费的 DeFi 协议数据:
- 协议 TVL 总锁仓量
- 收益池 APY
- 代币价格
- 链上稳定币数据

API:https://api.llama.fi(免 key)

命令:
- /defi_protocols: 列出所有协议(可按类别过滤)
- /defi_tvl <protocol>: 查询协议 TVL
- /defi_yields [--chain eth] [--limit 10]: 列出收益池
- /defi_pool <pool_id>: 查询具体池子 APY/TVL
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Any, Optional, List


DEFILLAMA_API = "https://api.llama.fi"
DEFAULT_TIMEOUT = 30


def _http_get(url: str, params: Optional[Dict] = None, timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "fr-cli/2.8"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            try:
                return {"ok": True, "data": json.loads(body), "status": resp.status}
            except json.JSONDecodeError:
                return {"ok": True, "data": body, "status": resp.status}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "error": f"HTTP {e.code}: {e.reason}"}
    except urllib.error.URLError as e:
        return {"ok": False, "error": f"URL 错误: {e.reason}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# --------------------------- 协议列表 ---------------------------

def list_protocols(category: Optional[str] = None) -> Dict[str, Any]:
    """列出所有 DeFi 协议

    Args:
        category: 可选类别过滤(Dexes / Lending / Yield / Liquid Staking / ...)

    Returns:
        {"ok": bool, "protocols": [{id, name, category, tvl, chain}], "error": str?}
    """
    r = _http_get(f"{DEFILLAMA_API}/protocols")
    if not r["ok"]:
        return {"ok": False, "error": r.get("error", "查询失败"), "protocols": []}

    data = r.get("data") or []
    if not isinstance(data, list):
        return {"ok": False, "error": "API 返回格式异常", "protocols": []}

    protocols = []
    for p in data:
        if category and p.get("category", "").lower() != category.lower():
            continue
        protocols.append({
            "id": p.get("id", ""),
            "name": p.get("name", ""),
            "category": p.get("category", ""),
            "tvl": p.get("tvl", 0),
            "chain": (p.get("chain") or "Multi-Chain"),
            "change_1d": p.get("change_1d"),
            "change_7d": p.get("change_7d"),
            "mcap": p.get("mcap"),
        })

    # TVL 排序
    protocols.sort(key=lambda x: x.get("tvl", 0), reverse=True)
    return {"ok": True, "protocols": protocols}


def get_protocol(protocol_slug: str) -> Dict[str, Any]:
    """获取协议详情(包含 TVL 历史)"""
    r = _http_get(f"{DEFILLAMA_API}/protocol/{protocol_slug}")
    if not r["ok"]:
        return {"ok": False, "error": r.get("error", "查询失败")}
    data = r.get("data") or {}
    return {
        "ok": True,
        "id": data.get("id", protocol_slug),
        "name": data.get("name", protocol_slug),
        "category": data.get("category", ""),
        "chain": (data.get("chain") or "Multi-Chain"),
        "tvl": data.get("tvl", 0),
        "chainTvls": data.get("chainTvls", {}),
        "change_1d": data.get("change_1d"),
        "change_7d": data.get("change_7d"),
    }


# --------------------------- 收益池 ---------------------------

def list_yields(chain: Optional[str] = None,
                project: Optional[str] = None,
                min_tvl: float = 0,
                limit: int = 20,
                sort_by: str = "apy") -> Dict[str, Any]:
    """列出收益池

    Args:
        chain: eth / bsc / polygon / ...
        project: 协议名(aave / compound / uniswap / ...)
        min_tvl: 最低 TVL 过滤
        limit: 最多返回数
        sort_by: apy(默认) / tvl /apyReward /apyBase

    Returns:
        {"ok": bool, "pools": [...], "error": str?}
    """
    r = _http_get(f"{DEFILLAMA_API}/yields/pools")
    if not r["ok"]:
        return {"ok": False, "error": r.get("error", "查询失败"), "pools": []}

    data = r.get("data") or {}
    pools = data.get("data", [])
    if not isinstance(pools, list):
        return {"ok": False, "error": "API 返回格式异常", "pools": []}

    # 过滤
    filtered = []
    for p in pools:
        if chain and p.get("chain", "").lower() != chain.lower():
            continue
        if project and p.get("project", "").lower() != project.lower():
            continue
        tvl = p.get("tvlUsd", 0) or 0
        if tvl < min_tvl:
            continue
        filtered.append(p)

    # 排序
    sort_key = {
        "apy": lambda x: x.get("apy", 0) or 0,
        "tvl": lambda x: x.get("tvlUsd", 0) or 0,
        "apyReward": lambda x: x.get("apyReward", 0) or 0,
        "apyBase": lambda x: x.get("apyBase", 0) or 0,
    }.get(sort_by, lambda x: x.get("apy", 0) or 0)
    filtered.sort(key=sort_key, reverse=True)

    return {"ok": True, "pools": filtered[:limit]}


def get_pool(pool_id: str) -> Dict[str, Any]:
    """获取单个池详情

    Args:
        pool_id: DeFi Llama 的 pool uuid
    """
    # 注意:DeFi Llama 池 ID 用 UUID 形式
    r = _http_get(f"{DEFILLAMA_API}/yields/pools")
    if not r["ok"]:
        return {"ok": False, "error": r.get("error", "查询失败")}

    pools = (r.get("data") or {}).get("data", [])
    for p in pools:
        if p.get("pool") == pool_id:
            return {"ok": True, "pool": p}
    return {"ok": False, "error": f"未找到 pool: {pool_id}"}


def get_pool_chart(pool_uuid: str, period: str = "1Y") -> Dict[str, Any]:
    """获取池子历史 APY/TVL 图表数据

    Args:
        pool_uuid: DeFi Llama pool uuid
        period: 时间段(1W / 1M / 3M / 6M / 1Y / All)

    Returns:
        {"ok": bool, "data": {status, symbol, apy, tvl, price, points: [...]}, "error": str?}
    """
    r = _http_get(f"https://yields.llama.fi/chart/{pool_uuid}",
                 params={"period": period})
    if not r["ok"]:
        return {"ok": False, "error": r.get("error", "查询失败")}
    data = r.get("data") or {}
    return {"ok": True, "data": data}


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


# --------------------------- 价格 ---------------------------

def get_token_price(tokens: str) -> Dict[str, Any]:
    """查询代币价格(DeFi Llama 的 prices API)

    Args:
        tokens: 逗号分隔的代币地址(支持 search)
        searchwidth: 搜索宽度
    """
    r = _http_get(f"https://coins.llama.fi/prices/current/{tokens}")
    if not r["ok"]:
        return {"ok": False, "error": r.get("error", "查询失败")}
    return {"ok": True, "data": r.get("data")}


# --------------------------- 格式化 ---------------------------

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
