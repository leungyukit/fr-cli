"""
Crypto 工具(只读,不存私钥):
- crypto_balance: 查询地址余额
- crypto_tx: 查询最近交易
- crypto_price: 查询价格(CoinGecko)
- crypto_chains: 列出支持的链
- crypto_apikey: 设置 Etherscan API key
"""
from fr_cli.command.registry import register
from fr_cli.core.result import Result


@register(
    name="crypto_balance",
    triggers=["查余额", "crypto balance", "wallet balance"],
    description="查询加密货币地址余额(ETH/BSC/Polygon 等多链)",
    params={"address": str, "chain": str, "rpc": str},
    aliases=["/crypto", "/balance"],
)
def _register_crypto_balance(deps, **kwargs):
    address = kwargs.get("address") or ""
    chain = kwargs.get("chain") or "eth"
    rpc = kwargs.get("rpc") or None

    if not address:
        return Result.fail("需要提供地址(0x...)")

    from fr_cli.weapon.crypto import get_balance, format_balance
    result = get_balance(address, chain=chain, rpc_url=rpc)
    return Result.ok(format_balance(result, lang="zh"))


@register(
    name="crypto_tx",
    triggers=["查交易", "crypto tx"],
    description="查询地址最近交易(需要 Etherscan API key 效果好)",
    params={"address": str, "chain": str, "limit": int},
    aliases=["/crypto_tx"],
)
def _register_crypto_tx(deps, **kwargs):
    address = kwargs.get("address") or ""
    chain = kwargs.get("chain") or "eth"
    limit = int(kwargs.get("limit", 10))

    if not address:
        return Result.fail("需要提供地址")

    from fr_cli.weapon.crypto import get_transactions, format_transactions, get_api_key
    result = get_transactions(address, chain=chain, limit=limit, api_key=get_api_key())
    return Result.ok(format_transactions(result, lang="zh"))


@register(
    name="crypto_price",
    triggers=["加密价格", "crypto price"],
    description="查询加密货币价格(CoinGecko,无需 key)",
    params={"symbol": str, "vs": str},
    aliases=["/crypto_price", "/price"],
)
def _register_crypto_price(deps, **kwargs):
    symbol = kwargs.get("symbol") or "ETH"
    vs = kwargs.get("vs") or "usd"

    from fr_cli.weapon.crypto import get_price, format_price, resolve_symbol
    cg_id = resolve_symbol(symbol)
    result = get_price(cg_id, vs_currency=vs)
    return Result.ok(format_price(result, lang="zh"))


@register(
    name="crypto_chains",
    triggers=["支持链", "crypto chains"],
    description="列出 Crypto 工具支持的区块链",
    params={},
    aliases=["/crypto_chains"],
)
def _register_crypto_chains(deps, **kwargs):
    from fr_cli.weapon.crypto import PUBLIC_RPCS, CHAIN_IDS
    lines = ["🔗 支持的链:"]
    for chain, rpc in PUBLIC_RPCS.items():
        cid = CHAIN_IDS.get(chain, "?")
        lines.append(f"  • {chain} (id={cid}) → {rpc}")
    lines.append("\n💡 用法:")
    lines.append("  /crypto_balance 0x... --chain bsc")
    lines.append("  /crypto_tx 0x... --chain polygon")
    return Result.ok("\n".join(lines))


@register(
    name="crypto_apikey",
    triggers=["etherscan key", "设置 etherscan key"],
    description="设置 Etherscan API key(免费,https://etherscan.io/apis)",
    params={"key": str},
    aliases=["/crypto_apikey"],
)
def _register_crypto_apikey(deps, **kwargs):
    key = kwargs.get("key") or ""
    if not key:
        return Result.fail("需要提供 API key")

    from fr_cli.weapon.crypto import set_api_key
    if set_api_key(key):
        return Result.ok("✅ Etherscan API key 已保存到 ~/.fr_cli/config.json")
    return Result.fail("保存失败")
