"""
计划持久化：保存 / 加载 / 列出已保存的计划文件
"""
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PLANS_DIR = Path.home() / ".fr_cli" / "plans"


def _plan_file_path(session_id: str) -> Path:
    PLANS_DIR.mkdir(parents=True, exist_ok=True)
    return PLANS_DIR / f"{session_id}.json"


def save_plan(state, plan: Dict[str, Any], step_results: Optional[List[Tuple[bool, str]]] = None) -> Optional[Path]:
    """将当前计划持久化到磁盘"""
    session_id = getattr(state, "session_id", None)
    if not session_id or not plan:
        return None
    path = _plan_file_path(session_id)
    data = {
        "session_id": session_id,
        "timestamp": time.time(),
        "plan": plan,
        "step_results": step_results or [],
        "plan_step_idx": getattr(state, "plan_step_idx", 0),
    }
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
    except Exception:
        return None


def load_plan(state) -> Optional[Dict[str, Any]]:
    """从磁盘加载当前会话的计划"""
    session_id = getattr(state, "session_id", None)
    if not session_id:
        return None
    path = _plan_file_path(session_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("plan")
    except Exception:
        return None


def list_saved_plans() -> List[Path]:
    """列出已保存的所有计划文件"""
    if not PLANS_DIR.exists():
        return []
    return sorted(PLANS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)