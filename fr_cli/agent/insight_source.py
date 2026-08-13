"""
选品历史数据源 —— MasterAgent 选品经验的"轮回卷轴"

抽象出可插拔的选品历史数据源，让 MasterAgent 能从不同形态的选品记录中
提炼爆款规律。第一版提供 Mock / JSON / CSV 三个 source，并预留 Session 挖掘接口。

设计原则：
  - Source 只负责"加载"，不做提炼（提炼由 InsightExtractor 负责）
  - 返回统一的 SelectionRecord 列表，方便上层做分批/聚合
  - Mock 作为默认 source，让流程在没有真实数据时也能跑通

数据契约（SelectionRecord 字段）：
  - name          str   商品/选品名
  - category      str   品类（"女装/连衣裙"、"3C/充电宝" 等）
  - price         float 售价（元）
  - sales_30d     int   30 天销量
  - lifecycle_days int  上架到爆的周期
  - peak_date     str   爆款峰值日（ISO）
  - tags          list[str] 标签（"应季"、"高频复购"、"高客单" 等）
  - source        str   数据来源标识（"mock"/"json"/"csv"/"session"）
"""
import csv
import json
import random
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


@dataclass
class SelectionRecord:
    """单条选品记录——进入 MasterAgent 选品经验的最小单元"""

    name: str
    category: str
    price: float
    sales_30d: int
    lifecycle_days: int
    peak_date: str
    tags: list = field(default_factory=list)
    source: str = "unknown"

    def to_dict(self):
        return asdict(self)


class SelectionHistorySource(ABC):
    """选品历史数据源抽象基类"""

    name: str = "abstract"

    @abstractmethod
    def load(self, since: Optional[str] = None) -> list:
        """加载选品历史

        Args:
            since: ISO 日期字符串（YYYY-MM-DD），仅返回该日期之后的记录；None 表示全部

        Returns:
            list[SelectionRecord]
        """

    def filter_by_date(self, records, since: Optional[str]):
        if not since:
            return records
        try:
            cutoff = datetime.fromisoformat(since)
        except ValueError:
            return records
        out = []
        for r in records:
            try:
                if datetime.fromisoformat(r.peak_date) >= cutoff:
                    out.append(r)
            except (ValueError, TypeError):
                continue
        return out


# ---------- Mock 数据源 ----------

_MOCK_CATEGORIES = [
    ("女装", ["连衣裙", "打底衫", "阔腿裤", "小香风外套", "碎花裙"]),
    ("3C数码", ["充电宝", "无线耳机", "机械键盘", "便携投影", "智能手表"]),
    ("家居日用", ["香薰蜡烛", "四件套", "保温杯", "电火锅", "收纳盒"]),
    ("美妆个护", ["口红", "面膜", "防晒霜", "洗发水", "美容仪"]),
    ("母婴玩具", ["益智积木", "孕妇装", "婴儿推车", "早教故事机", "儿童平衡车"]),
    ("运动户外", ["瑜伽裤", "冲锋衣", "跑鞋", "露营帐篷", "筋膜枪"]),
    ("食品保健", ["黑咖啡", "代餐奶昔", "坚果礼盒", "维生素", "即食燕窝"]),
]

_MOCK_TAGS_POOL = [
    "应季", "高频复购", "高客单", "低客单", "颜值经济", "情绪价值",
    "送礼场景", "自用场景", "学生党", "白领", "宝妈", "Z世代",
    "小红书爆款", "抖音爆款", "直播间专享", "节庆限定", "联名款",
]


def _generate_mock_records(count: int = 80, seed: int = 42) -> list:
    """生成一批仿真选品记录——覆盖不同品类、价格带、生命周期"""
    rng = random.Random(seed)
    records = []
    base_date = datetime.now() - timedelta(days=180)
    for i in range(count):
        big_cat, items = rng.choice(_MOCK_CATEGORIES)
        item = rng.choice(items)
        # 加上随机变体名
        variant = rng.choice(["", " 春夏款", " 升级版", " mini", " 礼盒装", " 限定色"])
        name = f"{item}{variant}".strip()
        # 价格带:大部分在 9.9 - 999 之间,少量高客单
        price = round(rng.uniform(9.9, 999.0), 2)
        if rng.random() < 0.1:
            price = round(rng.uniform(1000, 5000), 2)
        # 销量:对数分布(大多数中等销量,少量爆款)
        base_sales = int(rng.uniform(50, 5000))
        if rng.random() < 0.15:  # 15% 是爆款
            base_sales = int(rng.uniform(8000, 50000))
        sales = base_sales
        # 生命周期:7 - 90 天
        lifecycle = rng.randint(7, 90)
        # 峰值日:在过去 180 天内随机
        peak_offset = rng.randint(0, 180)
        peak = base_date + timedelta(days=peak_offset)
        # 标签:随机 1-3 个
        tags = rng.sample(_MOCK_TAGS_POOL, k=rng.randint(1, 3))
        records.append(
            SelectionRecord(
                name=name,
                category=f"{big_cat}/{item}",
                price=price,
                sales_30d=sales,
                lifecycle_days=lifecycle,
                peak_date=peak.strftime("%Y-%m-%d"),
                tags=tags,
                source="mock",
            )
        )
    # 按峰值日倒序
    records.sort(key=lambda r: r.peak_date, reverse=True)
    return records


class MockSelectionSource(SelectionHistorySource):
    """Mock 数据源——用合成数据让 insight 流程在没有真实记录时也能跑通"""

    name = "mock"

    def __init__(self, count: int = 80, seed: int = 42):
        self.count = count
        self.seed = seed

    def load(self, since: Optional[str] = None) -> list:
        records = _generate_mock_records(self.count, self.seed)
        return self.filter_by_date(records, since)


# ---------- JSON 数据源 ----------

class JSONSelectionSource(SelectionHistorySource):
    """从 JSON 文件加载选品历史

    文件格式：list[dict]，每条 dict 至少包含
      name, category, price, sales_30d, lifecycle_days, peak_date
    可选：tags (list[str])
    """

    name = "json"

    def __init__(self, path: str):
        self.path = Path(path)

    def load(self, since: Optional[str] = None) -> list:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if not isinstance(raw, list):
            return []
        records = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            # 关键字段必须非空,否则视为无效行
            if not item.get("name") or not item.get("category") or not item.get("peak_date"):
                continue
            try:
                rec = SelectionRecord(
                    name=str(item.get("name", "")),
                    category=str(item.get("category", "")),
                    price=float(item.get("price", 0)),
                    sales_30d=int(item.get("sales_30d", 0)),
                    lifecycle_days=int(item.get("lifecycle_days", 0)),
                    peak_date=str(item.get("peak_date", "")),
                    tags=list(item.get("tags", []) or []),
                    source=self.name,
                )
            except (TypeError, ValueError):
                continue
            records.append(rec)
        return self.filter_by_date(records, since)


# ---------- CSV 数据源 ----------

class CSVSelectionSource(SelectionHistorySource):
    """从 CSV 文件加载选品历史

    必填列：name, category, price, sales_30d, lifecycle_days, peak_date
    可选列：tags (以 '|' 分隔)
    """

    name = "csv"

    def __init__(self, path: str):
        self.path = Path(path)

    def load(self, since: Optional[str] = None) -> list:
        if not self.path.exists():
            return []
        records = []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        tags_raw = row.get("tags", "") or ""
                        tags = [t.strip() for t in tags_raw.split("|") if t.strip()]
                        rec = SelectionRecord(
                            name=str(row.get("name", "")),
                            category=str(row.get("category", "")),
                            price=float(row.get("price", 0) or 0),
                            sales_30d=int(row.get("sales_30d", 0) or 0),
                            lifecycle_days=int(row.get("lifecycle_days", 0) or 0),
                            peak_date=str(row.get("peak_date", "")),
                            tags=tags,
                            source=self.name,
                        )
                    except (TypeError, ValueError):
                        continue
                    records.append(rec)
        except Exception:
            return []
        return self.filter_by_date(records, since)


# ---------- Source 工厂 ----------

# 注册表:简单 dict,扩展时直接 import 然后 register
_REGISTRY = {
    "mock": MockSelectionSource,
}


def register_source(name: str, cls):
    """注册一个选品数据源(供动态扩展)"""
    if not name or not isinstance(name, str):
        raise ValueError("source name 必须是非空字符串")
    _REGISTRY[name] = cls


def list_sources() -> list:
    """列出所有可用数据源"""
    return list(_REGISTRY.keys())


def get_source(name: str, **kwargs) -> SelectionHistorySource:
    """根据名称获取数据源实例

    Args:
        name: source 名(mock / json / csv / 已注册的自定义名)
        **kwargs: 传给 source 构造函数的参数

    Raises:
        ValueError: 未知 source 名
    """
    if name not in _REGISTRY:
        raise ValueError(
            f"未知的选品数据源: {name}。可用: {list_sources()}"
        )
    return _REGISTRY[name](**kwargs)


def get_default_source() -> SelectionHistorySource:
    """获取默认数据源(目前是 Mock)

    未来若用户配置了真实数据源,应在此处读取配置后返回。
    """
    return MockSelectionSource()


__all__ = [
    "SelectionRecord",
    "SelectionHistorySource",
    "MockSelectionSource",
    "JSONSelectionSource",
    "CSVSelectionSource",
    "register_source",
    "list_sources",
    "get_source",
    "get_default_source",
]
