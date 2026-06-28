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
from typing import Dict, Any, Optional


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
