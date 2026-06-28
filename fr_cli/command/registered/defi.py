"""
DeFi 查询工具:
- defi_protocols: 列出协议
- defi_tvl: 协议详情
- defi_yields: 收益池(APY)
- defi_pool: 池详情
"""
from fr_cli.command.registry import register
from fr_cli.core.result import Result


@register(
    name="defi_protocols",
    triggers=["DeFi 协议", "defi protocols", "协议列表"],
    description="列出 DeFi 协议(DeFi Llama,免 key)",
    params={"category": str, "limit": int},
    aliases=["/defi", "/defi_list"],
)
def _register_defi_protocols(deps, **kwargs):
    category = kwargs.get("category") or None
    limit = int(kwargs.get("limit", 30))

    from fr_cli.weapon.defi import list_protocols, format_protocols
    result = list_protocols(category=category)
    return Result.ok(format_protocols(result, limit=limit, lang="zh"))


@register(
    name="defi_tvl",
    triggers=["DeFi TVL", "defi tvl", "协议详情"],
    description="查询 DeFi 协议 TVL 详情",
    params={"protocol": str},
    aliases=["/defi_tvl"],
)
def _register_defi_tvl(deps, **kwargs):
    protocol = kwargs.get("protocol") or ""
    if not protocol:
        return Result.fail("需要提供协议 slug(如 uniswap / aave / compound)")

    from fr_cli.weapon.defi import get_protocol, format_protocol_detail
    result = get_protocol(protocol)
    return Result.ok(format_protocol_detail(result, lang="zh"))


@register(
    name="defi_yields",
    triggers=["DeFi 收益", "defi yields", "APY"],
    description="列出 DeFi 收益池(APY,DeFi Llama,免 key)",
    params={"chain": str, "project": str, "min_tvl": float, "limit": int, "sort": str},
    aliases=["/defi_yields", "/apy"],
)
def _register_defi_yields(deps, **kwargs):
    chain = kwargs.get("chain") or None
    project = kwargs.get("project") or None
    min_tvl = float(kwargs.get("min_tvl", 0))
    limit = int(kwargs.get("limit", 20))
    sort_by = kwargs.get("sort") or "apy"

    from fr_cli.weapon.defi import list_yields, format_yields
    result = list_yields(chain=chain, project=project,
                        min_tvl=min_tvl, limit=limit, sort_by=sort_by)
    return Result.ok(format_yields(result, lang="zh"))


@register(
    name="defi_pool",
    triggers=["DeFi 池", "defi pool"],
    description="查询单个 DeFi 池详情(用 defi_yields 列出的 pool id 前 8 位)",
    params={"pool_id": str},
    aliases=["/defi_pool"],
)
def _register_defi_pool(deps, **kwargs):
    pool_id = kwargs.get("pool_id") or ""
    if not pool_id:
        return Result.fail("需要提供 pool ID(从 /defi_yields 列表里拿)")

    from fr_cli.weapon.defi import get_pool
    result = get_pool(pool_id)
    if not result["ok"]:
        return Result.fail(result.get("error"))
    pool = result["pool"]
    return Result.ok(
        f"💰 池详情:\n"
        f"  协议: {pool.get('project')}\n"
        f"  代币: {pool.get('symbol')}\n"
        f"  链: {pool.get('chain')}\n"
        f"  APY: {pool.get('apy', 0):.2f}%\n"
        f"  Base APY: {pool.get('apyBase', 0):.2f}%\n"
        f"  Reward APY: {pool.get('apyReward', 0):.2f}%\n"
        f"  TVL: ${pool.get('tvlUsd', 0):,.0f}\n"
        f"  Pool: {pool.get('pool')}"
    )


@register(
    name="defi_pool_chart",
    triggers=["DeFi APY 图表", "defi pool chart", "apy 图表"],
    description="查询 DeFi 池历史 APY/TVL 图表(ASCII 渲染)",
    params={"pool_id": str, "period": str, "width": int},
    aliases=["/defi_chart", "/apy_chart"],
)
def _register_defi_pool_chart(deps, **kwargs):
    pool_id = kwargs.get("pool_id") or ""
    period = kwargs.get("period") or "1Y"
    width = int(kwargs.get("width", 50))

    if not pool_id:
        return Result.fail("需要提供 pool ID")

    from fr_cli.weapon.defi import get_pool_chart, format_pool_chart
    result = get_pool_chart(pool_id, period=period)
    return Result.ok(format_pool_chart(result, width=width, lang="zh"))
