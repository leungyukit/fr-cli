"""
Web Console 数据查询函数

每个函数对应一个 /api/* 端点的数据源。
所有查询都做了异常隔离——任意一个数据源失败不会阻塞整体响应。
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from fr_cli.conf.paths import ROOT as FR_CLI_DIR
from fr_cli.core.store import JsonStore


def _try_load_json(path, default=None):
    """安全加载 JSON,失败返回 default

    JsonStore 默认 default=list(因为大多文件是 list),但这里我们总要 .get(),
    所以默认用 dict,缺失字段返回 {}
    """
    if not path.exists():
        return default if default is not None else {}
    try:
        result = JsonStore(str(path), default=dict).read()
        return result if isinstance(result, dict) else (default if default is not None else {})
    except Exception:
        return default if default is not None else {}


def get_global_status(state=None) -> Dict[str, Any]:
    """聚合全局状态(provider/model/Hermes/cron/agents/worktrees/bookmarks/sessions)"""
    status = {
        "timestamp": time.time(),
        "cwd": os.getcwd(),
        "provider": None,
        "model": None,
        "key_configured": False,
        "hermes_tasks": 0,
        "cron_jobs": 0,
        "agent_count": 0,
        "worktree_count": 0,
        "bookmark_count": 0,
        "session_count": 0,
    }

    try:
        from fr_cli.conf.config import load_config
        cfg = load_config()
        status["provider"] = cfg.get("provider")
        status["model"] = cfg.get("model")
        status["key_configured"] = bool(cfg.get("key"))
        status["autonomous_mode"] = cfg.get("autonomous_mode", "manual")
    except Exception:
        pass

    # Hermes 任务
    data = _try_load_json(FR_CLI_DIR / "hermes" / "tasks.json")
    if data:
        status["hermes_tasks"] = len(data.get("tasks", []))

    # Cron jobs
    data = _try_load_json(FR_CLI_DIR / "cron.json")
    if data:
        status["cron_jobs"] = len(data.get("jobs", []))

    # Agent 数量
    try:
        agents_dir = FR_CLI_DIR / "agents"
        if agents_dir.exists():
            status["agent_count"] = sum(
                1 for d in agents_dir.iterdir()
                if d.is_dir() and (d / "persona.md").exists()
            )
    except Exception:
        pass

    # Worktree 数量
    try:
        from fr_cli.weapon.worktree_cleanup import list_worktrees_for_cleanup
        status["worktree_count"] = len(list_worktrees_for_cleanup())
    except Exception:
        pass

    # Bookmark 数量
    data = _try_load_json(FR_CLI_DIR / "bookmarks" / "bookmarks.json")
    if data:
        status["bookmark_count"] = len(data.get("bookmarks", []))

    # Session 数量
    try:
        from fr_cli.memory.session import list_sessions
        status["session_count"] = len(list_sessions())
    except Exception:
        pass

    return status


def get_sessions_list(limit: int = 50) -> List[Dict[str, Any]]:
    """列出最近会话"""
    try:
        from fr_cli.memory.session import list_sessions
        return list_sessions()[:limit]
    except Exception:
        return []


def get_session_detail(idx: int) -> Optional[Dict[str, Any]]:
    """获取会话详情"""
    try:
        from fr_cli.memory.session import load_session
        ok, msgs, filename = load_session(idx)
        if ok:
            return {"filename": filename, "messages": msgs, "count": len(msgs)}
    except Exception:
        pass
    return None


def get_hermes_tasks() -> List[Dict[str, Any]]:
    """列出 Hermes 任务"""
    data = _try_load_json(FR_CLI_DIR / "hermes" / "tasks.json")
    return data.get("tasks", []) if data else []


def get_worktrees() -> List[Dict[str, Any]]:
    """列出 worktree"""
    try:
        from fr_cli.weapon.worktree_cleanup import list_worktrees_for_cleanup
        return list_worktrees_for_cleanup()
    except Exception:
        return []


def get_bookmarks(limit: int = 100) -> List[Dict[str, Any]]:
    """列出 bookmark"""
    try:
        from fr_cli.weapon.bookmark import list_bookmarks
        return list_bookmarks(limit=limit)
    except Exception:
        return []


def get_stats() -> Dict[str, Any]:
    """统计信息:消息数 / token / cost / RAG cache"""
    stats = {
        "total_messages": 0,
        "total_tokens": 0,
        "total_cost": 0.0,
        "rag_cache_hits": 0,
        "rag_cache_total": 0,
    }
    data = _try_load_json(FR_CLI_DIR / "usage.json")
    if data:
        calls = data.get("calls", [])
        stats["total_messages"] = len(calls)
        stats["total_tokens"] = sum(c.get("total_tokens", 0) for c in calls)
        stats["total_cost"] = sum(c.get("cost", 0) for c in calls)

    try:
        stats["rag_cache_total"] = 1  # 占位
    except Exception:
        pass

    return stats
