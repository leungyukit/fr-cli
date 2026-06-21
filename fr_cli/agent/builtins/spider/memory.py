"""
域名策略记忆 —— 跨爬取记住每个域名的最优获取方式 / 选择器

持久化到 ~/.fr_cli/spider/memory.json：
{
  "example.com": {
    "fetch_method": "selenium",
    "link_selector": "article a",
    "delay": 2.0,
    "success_rate": 0.85
  }
}
"""
import json
import re
from pathlib import Path
from typing import Optional

SPIDER_MEMORY_DIR = Path.home() / ".fr_cli" / "spider"
SPIDER_MEMORY_FILE = SPIDER_MEMORY_DIR / "memory.json"
SPIDER_EVOLUTION_FILE = SPIDER_MEMORY_DIR / "evolution.json"


def _ensure_spider_memory_dir():
    SPIDER_MEMORY_DIR.mkdir(parents=True, exist_ok=True)


def _load_spider_memory():
    """加载爬虫记忆（域名 → 策略映射）"""
    _ensure_spider_memory_dir()
    if not SPIDER_MEMORY_FILE.exists():
        return {}
    try:
        with open(SPIDER_MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_spider_memory(memory):
    """保存爬虫记忆"""
    _ensure_spider_memory_dir()
    try:
        with open(SPIDER_MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _get_domain_strategy(domain, memory=None):
    if memory is None:
        memory = _load_spider_memory()
    return memory.get(domain)


def _update_domain_strategy_in_memory(domain, strategy, success=True, memory=None):
    if memory is None:
        memory = _load_spider_memory()
    if domain not in memory:
        memory[domain] = {"success_count": 0, "failure_count": 0}
    entry = memory[domain]
    if success:
        entry["success_count"] = entry.get("success_count", 0) + 1
    else:
        entry["failure_count"] = entry.get("failure_count", 0) + 1
    # 合并新策略（不覆盖已有的字段）
    for k, v in strategy.items():
        if v is not None:
            entry[k] = v
    # 重新计算成功率
    total = entry["success_count"] + entry["failure_count"]
    if total > 0:
        entry["success_rate"] = entry["success_count"] / total
    return memory


def _sanitize_filename(url):
    """从 URL 生成安全的本地文件名"""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    path = parsed.path.strip("/") or "index"
    name = f"{parsed.netloc}_{path}"
    name = re.sub(r'[^\w\-_]', '_', name)[:100]
    return name + ".html"
