"""
@stock 内置 Agent —— 股票/量化交易助手

支持多源股票数据：
- akshare：开源 A 股数据（免 key）
- 麦蕊（mairui）：金融数据 API（需 token）
- tushare：财经数据接口（需 token）
- 通用 trade：券商/量化交易 API 配置占位（仅框架，真实交易需自行扩展）

所有配置收敛在 ~/.fr_cli/config.json 的 stock 命名空间。
"""
import json
import re
from datetime import datetime

import requests

from fr_cli.conf.config import load_namespace, save_namespace
from fr_cli.ui.ui import CYAN, GREEN, RED, YELLOW, DIM, RESET
from fr_cli.core.result import Result

# 可选依赖：未安装时对应数据源不可用
try:
    import akshare as ak
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False
    ak = None

try:
    import tushare as ts
    HAS_TUSHARE = True
except ImportError:
    HAS_TUSHARE = False
    ts = None

_NS_KEY = "stock"

DEFAULT_STOCK_CFG = {
    "default_source": "akshare",
    "akshare": {"enabled": True},
    "mairui": {"enabled": False, "key": "", "base_url": "https://api.mairui.club"},
    "tushare": {"enabled": False, "token": ""},
    "trade": {"enabled": False, "api": "", "key": "", "secret": "", "base_url": ""},
    "portfolio": {},  # 模拟持仓: {code: {quantity, cost, updated}}
}


def _load_stock_cfg():
    """加载股票配置，缺失字段补齐"""
    cfg = load_namespace(_NS_KEY, default={})
    for k, v in DEFAULT_STOCK_CFG.items():
        if k not in cfg or cfg[k] is None:
            cfg[k] = v
        elif isinstance(v, dict):
            for sub_k, sub_v in v.items():
                if sub_k not in cfg[k] or cfg[k][sub_k] is None:
                    cfg[k][sub_k] = sub_v
    return cfg


def _save_stock_cfg(cfg):
    """保存股票配置"""
    save_namespace(_NS_KEY, cfg)


def _normalize_code(code: str) -> str:
    """
    规范化股票代码。
    - 600519 → 600519.SH
    - 000001 → 000001.SZ
    - 00700 → 00700.HK
    - 若已含后缀则原样返回
    """
    code = code.strip().upper()
    if "." in code:
        return code
    if code.startswith("6"):
        return f"{code}.SH"
    if code.startswith(("0", "3")):
        return f"{code}.SZ"
    if code.startswith(("7", "8", "4")):
        return f"{code}.BJ"
    if code.startswith("8") and len(code) == 5:
        return f"{code}.HK"
    return code


def _code_without_suffix(code: str) -> str:
    """去掉市场后缀，返回纯数字代码"""
    return code.split(".")[0]


def _query_akshare_quote(code: str):
    """通过 akshare 获取 A 股实时行情"""
    if not HAS_AKSHARE or ak is None:
        raise ImportError("使用 akshare 请安装: pip install akshare")

    pure = _code_without_suffix(code)
    try:
        df = ak.stock_zh_a_spot_em()
    except Exception as e:
        return None, f"akshare 获取行情失败: {e}"

    row = df[df["代码"] == pure]
    if row.empty:
        return None, f"未找到 A 股代码: {code}"

    r = row.iloc[0]
    return {
        "source": "akshare",
        "code": code,
        "name": str(r.get("名称", "")),
        "price": float(r.get("最新价", 0) or 0),
        "open": float(r.get("今开", 0) or 0),
        "high": float(r.get("最高", 0) or 0),
        "low": float(r.get("最低", 0) or 0),
        "prev_close": float(r.get("昨收", 0) or 0),
        "volume": int(r.get("成交量", 0) or 0),
        "amount": float(r.get("成交额", 0) or 0),
        "change_pct": float(r.get("涨跌幅", 0) or 0),
        "time": str(datetime.now()),
    }, None


def _query_akshare_hist(code: str, period: str = "daily", days: int = 30):
    """通过 akshare 获取 A 股历史 K 线"""
    if not HAS_AKSHARE or ak is None:
        raise ImportError("使用 akshare 请安装: pip install akshare")

    pure = _code_without_suffix(code)
    try:
        df = ak.stock_zh_a_hist(symbol=pure, period=period, start_date="", end_date="", adjust="qfq")
    except Exception as e:
        return None, f"akshare 获取历史 K 线失败: {e}"

    if df.empty:
        return None, f"未找到历史数据: {code}"

    df = df.tail(days)
    records = []
    for _, r in df.iterrows():
        records.append({
            "date": str(r.get("日期", "")),
            "open": float(r.get("开盘", 0) or 0),
            "close": float(r.get("收盘", 0) or 0),
            "high": float(r.get("最高", 0) or 0),
            "low": float(r.get("最低", 0) or 0),
            "volume": int(r.get("成交量", 0) or 0),
        })
    return {"source": "akshare", "code": code, "period": period, "data": records}, None


def _query_mairui(code: str, endpoint: str, cfg: dict):
    """
    调用麦蕊 API。
    endpoint 示例: "hsrl/000001"（具体路径取决于麦蕊账户权限）
    """
    key = cfg.get("key", "").strip()
    base_url = cfg.get("base_url", "https://api.mairui.club").strip().rstrip("/")
    if not key:
        return None, "麦蕊 API Key 未配置"

    url = f"{base_url}/{endpoint}/{key}"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return {"source": "mairui", "code": code, "endpoint": endpoint, "data": resp.json()}, None
    except Exception as e:
        return None, f"麦蕊 API 请求失败: {e}"


def _query_tushare(code: str, token: str, api_name: str = "daily", params=None):
    """调用 tushare pro 接口"""
    if not HAS_TUSHARE or ts is None:
        raise ImportError("使用 tushare 请安装: pip install tushare")

    if not token:
        return None, "tushare token 未配置"

    pro = ts.pro_api(token)
    pure = _code_without_suffix(code)
    ts_code = f"{pure}.SH" if pure.startswith("6") else f"{pure}.SZ"
    try:
        df = pro.query(api_name, ts_code=ts_code, **(params or {}))
        if df is None or df.empty:
            return None, f"tushare 未返回数据: {code}"
        return {"source": "tushare", "code": code, "api": api_name, "data": df.to_dict(orient="records")}, None
    except Exception as e:
        return None, f"tushare 请求失败: {e}"


def _fetch_stock_data(query: str, stock_cfg: dict):
    """
    根据用户查询意图和配置，获取股票数据。
    返回 Result[data_dict]
    """
    # 从 query 中提取股票代码（支持 600519、000001、00700 等）
    codes = re.findall(r"\b(\d{5,6})\b", query)
    if not codes:
        return Result.fail("未能从输入中识别股票代码（请输入 5-6 位数字代码）")

    code = _normalize_code(codes[0])
    source = stock_cfg.get("default_source", "akshare")

    # akshare 默认通道
    if source == "akshare" and stock_cfg.get("akshare", {}).get("enabled"):
        # 历史/K线关键词
        if any(k in query for k in ("K线", "k线", "历史", "走势", "chart", "history")):
            return Result.from_tuple(*_query_akshare_hist(code))
        return Result.from_tuple(*_query_akshare_quote(code))

    # 麦蕊
    if source == "mairui" and stock_cfg.get("mairui", {}).get("enabled"):
        # 简单映射：行情/分时/财务（具体 endpoint 以麦蕊文档为准）
        endpoint = "hslt/list"  # 默认列表类接口
        if any(k in query for k in ("行情", "价格", "quote")):
            endpoint = f"hsrl/{_code_without_suffix(code)}"
        return Result.from_tuple(*_query_mairui(code, endpoint, stock_cfg.get("mairui", {})))

    # tushare
    if source == "tushare" and stock_cfg.get("tushare", {}).get("enabled"):
        api_name = "daily"
        if "财务" in query or "finance" in query.lower():
            api_name = "income"
        return Result.from_tuple(*_query_tushare(code, stock_cfg.get("tushare", {}).get("token", ""), api_name=api_name))

    # 若默认源未启用，尝试 akshare（免 key）兜底
    try:
        return Result.from_tuple(*_query_akshare_quote(code))
    except ImportError:
        return Result.fail(f"默认数据源 [{source}] 未启用或未安装依赖")


def _analyze_with_llm(state, query: str, data: dict):
    """调用 LLM 分析股票数据"""
    from fr_cli.core.stream import stream_cnt

    prompt = f"""你是股票/量化分析助手。请根据以下股票数据回答用户问题。

规则：
1. 用中文简洁回答
2. 给出关键数字和结论
3. 如果是行情数据，说明当前价格、涨跌幅、成交量
4. 如果是历史数据，简述近期趋势
5. 不做投资建议，仅作信息整理

用户问题：{query}

数据：
{json.dumps(data, ensure_ascii=False, indent=2, default=str)[:4000]}
"""
    messages = [
        {"role": "system", "content": "你是股票/量化分析助手，擅长整理和解读金融数据。"},
        {"role": "user", "content": prompt},
    ]
    print(f"{CYAN}🧙 正在分析股票数据...{RESET}")
    txt, _, _, _ = stream_cnt(state.client, state.model_name, messages, state.lang, custom_prefix="", max_tokens=2048)
    return txt


def _simulate_trade(stock_cfg: dict, code: str, action: str, quantity: int, price: float):
    """
    模拟交易：记录到本地 portfolio，不执行真实交易。
    action: buy / sell
    返回 Result[holding]
    """
    portfolio = stock_cfg.get("portfolio", {})
    holding = portfolio.get(code, {"quantity": 0, "cost": 0.0, "updated": ""})
    total_cost = holding["quantity"] * holding["cost"]

    if action == "buy":
        new_total = total_cost + quantity * price
        new_qty = holding["quantity"] + quantity
        holding["cost"] = round(new_total / new_qty, 4) if new_qty else 0
        holding["quantity"] = new_qty
    elif action == "sell":
        if holding["quantity"] < quantity:
            return Result.fail(f"持仓不足：当前 {holding['quantity']}，欲卖出 {quantity}")
        holding["quantity"] -= quantity
        if holding["quantity"] == 0:
            holding["cost"] = 0.0
    else:
        return Result.fail(f"不支持的交易动作: {action}")

    holding["updated"] = datetime.now().isoformat()
    if holding["quantity"] > 0:
        portfolio[code] = holding
    else:
        portfolio.pop(code, None)
    stock_cfg["portfolio"] = portfolio
    _save_stock_cfg(stock_cfg)
    return Result.ok(holding)


def handle_stock(user_input, state):
    """处理 @stock 前缀的请求"""
    text = user_input[len("@stock"):].strip()
    if not text:
        _print_usage()
        return

    stock_cfg = _load_stock_cfg()

    # 配置类命令
    if text in ("config", "配置"):
        _print_config(stock_cfg)
        return
    if text in ("portfolio", "持仓"):
        _print_portfolio(stock_cfg)
        return

    # 交易意图识别（模拟）
    trade_match = re.match(r"(买入|卖出|buy|sell)\s+(\d{5,6})\s+(\d+(?:\.\d+)?)\s*(\d+)?", text, re.IGNORECASE)
    if trade_match:
        action_zh = trade_match.group(1).lower()
        action = "buy" if action_zh in ("买入", "buy") else "sell"
        code = _normalize_code(trade_match.group(2))
        price = float(trade_match.group(3))
        quantity = int(trade_match.group(4)) if trade_match.group(4) else 100

        # 交易是高风险操作，必须确认
        from fr_cli.agent.builtins._utils import confirm_execute
        print(f"\n{YELLOW}模拟交易确认:{RESET}")
        print(f"  动作: {action.upper()}")
        print(f"  代码: {code}")
        print(f"  数量: {quantity}")
        print(f"  价格: {price}")
        if not confirm_execute("确认执行模拟交易", default_yes=False):
            print(f"{DIM}已取消。{RESET}")
            return

        result = _simulate_trade(stock_cfg, code, action, quantity, price)
        if result.is_ok():
            print(f"{GREEN}✅ 模拟交易已记录: {code} {action} {quantity} @ {price}{RESET}")
            print(f"{DIM}当前持仓: {result.unwrap()}{RESET}")
        else:
            print(f"{RED}❌ {result.error}{RESET}")
        return

    # 数据查询与分析
    result = _fetch_stock_data(text, stock_cfg)
    if result.is_fail():
        print(f"{RED}❌ {result.error}{RESET}")
        print(f"{DIM}提示: 使用 /stock_config setup 配置数据源，或安装 akshare: pip install akshare{RESET}")
        return
    data = result.unwrap()

    # 如果用户只是想查原始数据，直接输出 JSON；否则调用 LLM 分析
    if any(k in text for k in ("原始数据", "raw", "json")):
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        return

    analysis = _analyze_with_llm(state, text, data)
    print(f"\n{GREEN}{analysis}{RESET}")


def _print_usage():
    print(f"{YELLOW}用法:{RESET}")
    print("  @stock 600519              查询贵州茅台实时行情")
    print("  @stock 000001 历史走势      查询平安银行历史 K 线")
    print("  @stock 买入 600519 1480.00 100   模拟买入（记录到本地持仓）")
    print("  @stock 持仓                 查看模拟持仓")
    print("  @stock 配置                 查看当前数据源配置")
    print(f"\n{DIM}配置:{RESET}")
    print("  /stock_config setup         交互式配置数据源")


def _print_config(stock_cfg: dict):
    print(f"{CYAN}📈 当前 StockShareAgent 配置{RESET}")
    print(f"  默认数据源: {DIM}{stock_cfg.get('default_source', 'akshare')}{RESET}")
    for source in ("akshare", "mairui", "tushare", "trade"):
        cfg = stock_cfg.get(source, {})
        enabled = cfg.get("enabled", False)
        status = f"{GREEN}已启用{RESET}" if enabled else f"{DIM}未启用{RESET}"
        print(f"  {source}: {status}")
        if source in ("mairui", "tushare") and enabled:
            key = cfg.get("key") or cfg.get("token", "")
            print(f"    Key: {DIM}{key[:6] + '****' if len(key) > 6 else key}{RESET}")


def _print_portfolio(stock_cfg: dict):
    portfolio = stock_cfg.get("portfolio", {})
    print(f"{CYAN}💼 模拟持仓{RESET}")
    if not portfolio:
        print(f"{DIM}暂无持仓{RESET}")
        return
    total_value = 0.0
    for code, h in portfolio.items():
        qty = h.get("quantity", 0)
        cost = h.get("cost", 0.0)
        print(f"  {code}: 数量={qty} 成本={cost} 更新={h.get('updated', '')}")
        total_value += qty * cost
    print(f"{DIM}总成本市值: {total_value:.2f}{RESET}")

