"""
选品经验档案 —— MasterAgent 选品洞察的"洞府"

把 InsightExtractor 提炼出的规律持久化到磁盘，供：
  1. master_prompt_builder 注入到 system prompt
  2. /insight show 查看最新
  3. /insight history 回溯对比

存储布局：
  ~/.fr_cli/master/insights/
    latest.json                    # 最新洞察(供 prompt 注入)
    history/YYYY-MM-DD_HHMMSS.json # 历史快照(每次提炼一份)
    index.json                     # 历史索引(只保留元信息,体积小)

latest.json 结构：
  {
    "version": 1,
    "created_at": "ISO 时间",
    "source_name": "mock/json/csv",
    "record_count": 80,
    "since": null,
    "insights": {...}
  }
"""
import json
from datetime import datetime
from typing import Optional

from fr_cli.conf import paths as _paths

# 路径用 lambda/函数,确保测试可通过 monkeypatch MASTER_DIR 隔离
INSIGHTS_DIR = lambda: _paths.MASTER_DIR / "insights"  # noqa
HISTORY_DIR = lambda: INSIGHTS_DIR() / "history"  # noqa
LATEST_FILE = lambda: INSIGHTS_DIR() / "latest.json"  # noqa
INDEX_FILE = lambda: INSIGHTS_DIR() / "index.json"  # noqa

INSIGHT_VERSION = 1


def _ensure_dirs():
    INSIGHTS_DIR().mkdir(parents=True, exist_ok=True)
    HISTORY_DIR().mkdir(parents=True, exist_ok=True)


def _load_index() -> dict:
    if not INDEX_FILE().exists():
        return {"version": INSIGHT_VERSION, "entries": []}
    try:
        return json.loads(INDEX_FILE().read_text(encoding="utf-8"))
    except Exception:
        return {"version": INSIGHT_VERSION, "entries": []}


def _save_index(idx: dict):
    _ensure_dirs()
    # 只保留最近 50 条索引
    idx["entries"] = idx.get("entries", [])[-50:]
    INDEX_FILE().write_text(
        json.dumps(idx, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save(insights: dict, *, source_name: str = "unknown", record_count: int = 0, since: Optional[str] = None) -> str:
    """保存一次洞察

    Args:
        insights: InsightExtractor 提炼出的洞察 dict
        source_name: 用了哪个数据源
        record_count: 输入记录数
        since: 过滤起始日期(如有)

    Returns:
        保存路径(latest.json)
    """
    _ensure_dirs()
    now = datetime.now()
    payload = {
        "version": INSIGHT_VERSION,
        "created_at": now.isoformat(),
        "source_name": source_name,
        "record_count": record_count,
        "since": since,
        "insights": insights,
    }
    LATEST_FILE().write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 写入历史快照
    stamp = now.strftime("%Y-%m-%d_%H%M%S")
    history_path = HISTORY_DIR() / f"{stamp}.json"
    history_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 更新索引
    idx = _load_index()
    idx["entries"].append({
        "created_at": now.isoformat(),
        "source_name": source_name,
        "record_count": record_count,
        "summary": (insights.get("summary") or "")[:80],
        "history_path": str(history_path.relative_to(INSIGHTS_DIR())),
    })
    _save_index(idx)
    return str(LATEST_FILE())


def load_latest() -> Optional[dict]:
    """加载最新洞察;不存在返回 None"""
    if not LATEST_FILE().exists():
        return None
    try:
        return json.loads(LATEST_FILE().read_text(encoding="utf-8"))
    except Exception:
        return None


def list_history(limit: int = 10) -> list:
    """列出最近 N 条历史快照元信息"""
    idx = _load_index()
    return list(reversed(idx.get("entries", [])[-limit:]))


def load_history(history_path: str) -> Optional[dict]:
    """按相对路径加载某条历史快照(从 list_history 拿到 path)"""
    full = INSIGHTS_DIR() / history_path
    if not full.exists():
        return None
    try:
        return json.loads(full.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_latest_meta() -> Optional[dict]:
    """只读 latest 的元信息(不返回完整 insights)—— 用于轻量展示"""
    payload = load_latest()
    if not payload:
        return None
    return {
        "created_at": payload.get("created_at"),
        "source_name": payload.get("source_name"),
        "record_count": payload.get("record_count"),
        "summary": (payload.get("insights") or {}).get("summary", ""),
    }


__all__ = [
    "INSIGHTS_DIR",
    "HISTORY_DIR",
    "LATEST_FILE",
    "INDEX_FILE",
    "INSIGHT_VERSION",
    "save",
    "load_latest",
    "list_history",
    "load_history",
    "get_latest_meta",
]
