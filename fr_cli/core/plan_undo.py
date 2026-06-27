"""
Plan mode 撤销栈 —— 让用户可以回退到上一步计划

场景:
- 用户批准了一个 plan,但执行到一半想换思路
- 用户编辑了 plan 但后悔
- 用户想对比多个版本的 plan

实现:
- 每次 save_pending_plan / edit_pending_plan 时,把当前版本压栈
- /plan_undo / plan_undo N:回退 N 步
- /plan_redo:重做(从回退栈恢复)
- 栈持久化到 ~/.fr_cli/plan_history/<session_id>.json

栈结构:
```json
{
  "session_id": "...",
  "undo_stack": [<plan_v1>, <plan_v2>, ...],   // 老的在前
  "redo_stack": [<plan_v3>, ...],                // redo 的版本
  "current": <current_plan>,                     // 当前 plan
  "updated_at": "..."
}
```
"""
import time
from pathlib import Path
from typing import Dict, Any, Optional

from fr_cli.conf.paths import ROOT as FR_CLI_DIR
from fr_cli.core.store import JsonStore


HISTORY_DIR = FR_CLI_DIR / "plan_history"
MAX_UNDO_DEPTH = 20  # 最多保留 20 步历史


def _ensure_dir():
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def _history_path(session_id: str) -> Path:
    safe_id = "".join(c for c in session_id if c.isalnum() or c in "-_")
    return HISTORY_DIR / f"{safe_id}.json"


def load_history(session_id: str) -> Dict[str, Any]:
    """加载 plan 历史

    Returns:
        {"undo_stack": [...], "redo_stack": [...], "current": ...}
    """
    path = _history_path(session_id)
    if not path.exists():
        return {"undo_stack": [], "redo_stack": [], "current": None}
    try:
        return JsonStore(str(path), default=dict).read()
    except Exception:
        return {"undo_stack": [], "redo_stack": [], "current": None}


def save_history(session_id: str, history: Dict[str, Any]) -> bool:
    """保存 plan 历史"""
    _ensure_dir()
    path = _history_path(session_id)
    try:
        data = {
            "session_id": session_id,
            "undo_stack": history.get("undo_stack", []),
            "redo_stack": history.get("redo_stack", []),
            "current": history.get("current"),
            "updated_at": time.time(),
        }
        JsonStore(str(path), default=dict).write(data)
        return True
    except Exception:
        return False


def push_version(session_id: str, plan: Dict[str, Any]) -> Dict[str, Any]:
    """推入新版本(会自动清空 redo_stack,因为新动作废弃了未来分支)

    Returns:
        更新后的 history
    """
    history = load_history(session_id)
    if history.get("current") is not None:
        # 把 current 压入 undo
        undo_stack = history.get("undo_stack", [])
        undo_stack.append(history["current"])
        # 限制深度
        if len(undo_stack) > MAX_UNDO_DEPTH:
            undo_stack = undo_stack[-MAX_UNDO_DEPTH:]
        history["undo_stack"] = undo_stack
    history["redo_stack"] = []  # 新动作清 redo
    history["current"] = plan
    save_history(session_id, history)
    return history


def undo(session_id: str, steps: int = 1) -> Optional[Dict[str, Any]]:
    """回退 N 步,返回回退后的 current plan(失败/没有历史返回 None)"""
    history = load_history(session_id)
    if not history.get("undo_stack"):
        return None

    steps = min(steps, len(history["undo_stack"]))
    new_current = None
    for _ in range(steps):
        if not history["undo_stack"]:
            break
        new_current = history["undo_stack"].pop()
        if history.get("current") is not None:
            history["redo_stack"].append(history["current"])
        history["current"] = new_current

    save_history(session_id, history)
    return new_current


def redo(session_id: str) -> Optional[Dict[str, Any]]:
    """重做一步,返回重做后的 current plan"""
    history = load_history(session_id)
    if not history.get("redo_stack"):
        return None

    new_current = history["redo_stack"].pop()
    if history.get("current") is not None:
        history["undo_stack"].append(history["current"])
    history["current"] = new_current

    save_history(session_id, history)
    return new_current


def clear_history(session_id: str) -> bool:
    """清空历史(批准 plan 后调用)"""
    path = _history_path(session_id)
    try:
        if path.exists():
            path.unlink()
        return True
    except Exception:
        return False


def history_summary(session_id: str) -> Dict[str, Any]:
    """历史摘要(用于展示)"""
    history = load_history(session_id)
    return {
        "undo_count": len(history.get("undo_stack", [])),
        "redo_count": len(history.get("redo_stack", [])),
        "has_current": history.get("current") is not None,
        "max_depth": MAX_UNDO_DEPTH,
    }


def format_history_summary(session_id: str, lang: str = "zh") -> str:
    """格式化历史摘要为可读文本"""
    summary = history_summary(session_id)
    if lang == "zh":
        return (
            f"📚 Plan 历史: "
            f"↩️ 可撤销 {summary['undo_count']} 步 | "
            f"↪️ 可重做 {summary['redo_count']} 步 | "
            f"📍 当前{'有' if summary['has_current'] else '无'} plan"
        )
    return (
        f"📚 Plan History: "
        f"↩️ {summary['undo_count']} undo | "
        f"↪️ {summary['redo_count']} redo | "
        f"📍 {'has' if summary['has_current'] else 'no'} current"
    )
