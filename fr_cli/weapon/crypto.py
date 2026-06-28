"""
Crypto Wallet —— 加密货币查询(只读)

⚠️ 安全原则:
- 不存私钥/助记词
- 不发起交易签名
- 仅查询公开链上数据
- 调用公共 RPC(Infura / Alchemy / Cloudflare ETH gateway)

支持:
- ETH 主网 / Sepolia / Goerli 等 EVM 链
- 通过 Etherscan-compatible API 查询余额 / 交易 / 代币
- 多链支持(BSC / Polygon / Arbitrum 通过 chain id 切换)

API 来源(无需 Key):
- Cloudflare ETH Gateway: https://cloudflare-eth.com (公开 RPC)
- Blockchair / Blockcypher(部分链)
- Etherscan API(部分功能需要 free API key)

命令:
- /crypto_balance <addr> [--chain eth|bsc|polygon|...]
- /crypto_tx <addr> [limit]
- /crypto_tokens <addr> [--chain eth]
- /crypto_price <symbol>  (CoinGecko API)
"""
import json
import os
import urllib.error
import urllib.request
import urllib.parse
import time
from typing import Dict, Any, Optional


# 公开 RPC 节点(免 key)
PUBLIC_RPCS = {
    "eth": "https://cloudflare-eth.com",
    "sepolia": "https://ethereum-sepolia-rpc.publicnode.com",
    "bsc": "https://bsc-dataseed.binance.org",
    "polygon": "https://polygon-rpc.com",
    "arbitrum": "https://arb1.arbitrum.io/rpc",
    "optimism": "https://mainnet.optimism.io",
    "avalanche": "https://api.avax.network/ext/bc/C/rpc",
}

# Chain ID 映射
CHAIN_IDS = {
    "eth": 1,
    "sepolia": 11155111,
    "bsc": 56,
    "polygon": 137,
    "arbitrum": 42161,
    "optimism": 10,
    "avalanche": 43114,
}

# Etherscan-style API(支持多链)
ETHERSCAN_APIS = {
    "eth": "https://api.etherscan.io/api",
    "bsc": "https://api.bscscan.com/api",
    "polygon": "https://api.polygonscan.com/api",
    "arbitrum": "https://api.arbiscan.io/api",
    "optimism": "https://api-optimistic.etherscan.io/api",
    "avalanche": "https://api.snowtrace.io/api",
}

# 1 ether = 10^18 wei
WEI_PER_ETH = 10 ** 18


def _http_get(url: str, params: Optional[Dict] = None,
              headers: Optional[Dict[str, str]] = None,
              timeout: int = 30) -> Dict[str, Any]:
    """HTTP GET"""
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    headers = headers or {"User-Agent": "fr-cli/2.8"}
    req = urllib.request.Request(url, headers=headers)
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


def _http_post_json(url: str, payload: Dict[str, Any],
                    headers: Optional[Dict[str, str]] = None,
                    timeout: int = 30) -> Dict[str, Any]:
    """HTTP POST JSON"""
    headers = headers or {}
    headers["Content-Type"] = "application/json"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            response_body = resp.read().decode("utf-8")
            try:
                return {"ok": True, "data": json.loads(response_body), "status": resp.status}
            except json.JSONDecodeError:
                return {"ok": True, "data": response_body, "status": resp.status}
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8")
        except Exception:
            err_body = ""
        return {"ok": False, "status": e.code, "error": f"HTTP {e.code}: {e.reason}", "body": err_body}
    except urllib.error.URLError as e:
        return {"ok": False, "error": f"URL 错误: {e.reason}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# --------------------------- 余额 ---------------------------

def get_balance(address: str, chain: str = "eth",
                rpc_url: Optional[str] = None) -> Dict[str, Any]:
    """获取原生代币余额

    Args:
        address: 0x 开头的钱包地址
        chain: 链名(eth / bsc / polygon / ...)
        rpc_url: 自定义 RPC URL

    Returns:
        {"ok": bool, "balance": str, "balance_eth": float, "chain": str, "error": str?}
    """
    if not address or not address.startswith("0x") or len(address) != 42:
        return {"ok": False, "error": f"无效地址: {address}"}

    rpc_url = rpc_url or PUBLIC_RPCS.get(chain)
    if not rpc_url:
        return {"ok": False, "error": f"不支持的链: {chain}"}

    chain_id = CHAIN_IDS.get(chain, 1)

    payload = {
        "jsonrpc": "2.0",
        "method": "eth_getBalance",
        "params": [address, "latest"],
        "id": 1,
    }

    r = _http_post_json(rpc_url, payload)
    if not r["ok"]:
        return {"ok": False, "error": r.get("error", "RPC 调用失败")}

    result_hex = r["data"].get("result", "0x0")
    try:
        wei = int(result_hex, 16)
        balance = wei / WEI_PER_ETH
    except (ValueError, TypeError):
        return {"ok": False, "error": f"无法解析余额: {result_hex}"}

    return {
        "ok": True,
        "address": address,
        "chain": chain,
        "chain_id": chain_id,
        "balance_wei": wei,
        "balance": f"{balance:.8f}",
        "balance_eth": balance,  # alias(对所有链都是 native token)
        "rpc_url": rpc_url,
    }


def format_balance(result: Dict[str, Any], lang: str = "zh") -> str:
    """格式化余额结果"""
    if not result["ok"]:
        return f"❌ {result.get('error', '查询失败')}"

    chain = result["chain"]
    symbol = {"eth": "ETH", "bsc": "BNB", "polygon": "MATIC",
              "arbitrum": "ETH", "optimism": "ETH",
              "avalanche": "AVAX", "sepolia": "SepETH"}.get(chain, chain.upper())

    if lang == "zh":
        return (
            f"💰 余额:\n"
            f"  地址: {result['address']}\n"
            f"  链: {chain} (id={result['chain_id']})\n"
            f"  余额: {result['balance']} {symbol}\n"
            f"  Wei: {result['balance_wei']}"
        )
    return (
        f"💰 Balance:\n"
        f"  Address: {result['address']}\n"
        f"  Chain: {chain} (id={result['chain_id']})\n"
        f"  Balance: {result['balance']} {symbol}\n"
        f"  Wei: {result['balance_wei']}"
    )


# --------------------------- 交易 ---------------------------

def get_transactions(address: str, chain: str = "eth",
                     limit: int = 10,
                     api_key: Optional[str] = None) -> Dict[str, Any]:
    """获取最近交易(Etherscan API)

    Returns:
        {"ok": bool, "txs": [{hash, from, to, value, time, ...}], "error": str?}
    """
    if not address or not address.startswith("0x"):
        return {"ok": False, "error": f"无效地址: {address}"}

    api_url = ETHERSCAN_APIS.get(chain)
    if not api_url:
        return {"ok": False, "error": f"不支持的链: {chain}"}

    params = {
        "module": "account",
        "action": "txlist",
        "address": address,
        "startblock": 0,
        "endblock": 99999999,
        "page": 1,
        "offset": limit,
        "sort": "desc",
    }
    if api_key:
        params["apikey"] = api_key

    r = _http_get(api_url, params=params, timeout=30)
    if not r["ok"]:
        return {"ok": False, "error": r.get("error", "查询失败")}

    data = r.get("data") or {}
    if isinstance(data, dict):
        status = data.get("status", "0")
        if status == "0":
            msg = data.get("message", "")
            result_field = data.get("result", "")
            # 没有交易 → 返回空数组
            if "No transactions found" in str(result_field) or msg == "No transactions found":
                return {"ok": True, "txs": []}
            # 需要 API key
            if "Invalid API Key" in str(result_field) or "API Key" in str(result_field):
                return {
                    "ok": False,
                    "error": "Etherscan API 需要免费 key(https://etherscan.io/apis),请 /crypto_apikey <your_key>"
                }
            return {"ok": False, "error": f"API 返回错误: {result_field}"}
        txs = data.get("result", [])
        if isinstance(txs, list):
            return {"ok": True, "txs": txs[:limit]}
        return {"ok": False, "error": "返回格式异常"}

    return {"ok": False, "error": "返回格式异常"}


def format_transactions(result: Dict[str, Any], lang: str = "zh") -> str:
    """格式化交易列表"""
    if not result["ok"]:
        return f"❌ {result.get('error', '查询失败')}"

    txs = result["txs"]
    if not txs:
        return "📭 没有交易记录"

    lines = [f"📜 最近 {len(txs)} 笔交易:"]
    for tx in txs:
        h = tx.get("hash", "")
        h_short = (h[:10] + "...") if h else "?"
        from_short = tx.get("from", "")[:10] + "..."
        to_short = tx.get("to", "")[:10] + "..."
        value_wei = int(tx.get("value", "0"))
        value = value_wei / WEI_PER_ETH
        ts = int(tx.get("timeStamp", 0))
        time_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else "?"
        lines.append(
            f"  • {h_short} | {value:.6f} ETH\n"
            f"      {from_short} → {to_short}\n"
            f"      时间: {time_str}"
        )
    return "\n".join(lines)


# --------------------------- 价格 ---------------------------

def get_price(symbol: str = "ethereum",
              vs_currency: str = "usd") -> Dict[str, Any]:
    """获取加密货币价格(CoinGecko 免费 API,无需 key)

    Args:
        symbol: ethereum / bitcoin / dogecoin (CoinGecko id)
        vs_currency: usd / cny / eur

    Returns:
        {"ok": bool, "price": float, "symbol": str, "vs": str, "error": str?}
    """
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": symbol, "vs_currencies": vs_currency}
    r = _http_get(url, params=params, timeout=15)
    if not r["ok"]:
        return {"ok": False, "error": r.get("error", "查询失败")}

    data = r.get("data") or {}
    if symbol not in data:
        return {"ok": False, "error": f"未知币种: {symbol} (试 ethereum / bitcoin / dogecoin)"}
    price = data[symbol].get(vs_currency)
    if price is None:
        return {"ok": False, "error": f"无 {vs_currency} 价格"}

    return {
        "ok": True,
        "symbol": symbol,
        "vs_currency": vs_currency,
        "price": price,
    }


def format_price(result: Dict[str, Any], lang: str = "zh") -> str:
    """格式化价格"""
    if not result["ok"]:
        return f"❌ {result.get('error', '查询失败')}"

    vs = result["vs_currency"].upper()
    sym = result["symbol"]
    price = result["price"]
    if lang == "zh":
        return f"💲 {sym} 价格: {price:,.4f} {vs}"
    return f"💲 {sym} price: {price:,.4f} {vs}"


# --------------------------- 配置 ---------------------------

def get_api_key() -> Optional[str]:
    """获取 Etherscan API key(env 或 config)"""
    key = os.environ.get("ETHERSCAN_API_KEY") or os.environ.get("ETH_API_KEY")
    if key:
        return key
    try:
        from fr_cli.conf.config import load_config
        cfg = load_config()
        return cfg.get("etherscan_api_key")
    except Exception:
        return None


def set_api_key(key: str) -> bool:
    """设置 Etherscan API key"""
    try:
        from fr_cli.conf.config import load_config, save_config
        cfg = load_config()
        cfg["etherscan_api_key"] = key
        save_config(cfg)
        return True
    except Exception:
        return False


# 常用 CoinGecko symbol 映射
SYMBOL_TO_COINGECKO = {
    "ETH": "ethereum",
    "BTC": "bitcoin",
    "BNB": "binancecoin",
    "USDT": "tether",
    "USDC": "usd-coin",
    "MATIC": "matic-network",
    "ARB": "arbitrum",
    "OP": "optimism",
    "AVAX": "avalanche-2",
    "DOGE": "dogecoin",
    "SOL": "solana",
}


def resolve_symbol(symbol: str) -> str:
    """把常见 symbol 转 CoinGecko id"""
    s = symbol.upper()
    return SYMBOL_TO_COINGECKO.get(s, symbol.lower())
