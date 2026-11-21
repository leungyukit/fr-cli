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

模块拆分(原单文件 464 行):
- defi.py:        本文件——网络层(_http_get + API 函数)
- defi_format.py: 渲染层(ASCII 图表 / 文本排版,经本模块 re-export 保持旧路径)

注意:测试通过 @patch("fr_cli.weapon.defi._http_get") 打桩,
因此 _http_get 必须留在本模块(API 函数在本地命名空间解析它)。
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from fr_cli.weapon.defi_format import (  # noqa: F401 (re-export,旧导入路径兼容)
    _human_apy,
    _human_tvl,
    format_pool_chart,
    format_protocol_detail,
    format_protocols,
    format_yields,
    render_ascii_chart,
)


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
