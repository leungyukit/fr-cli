"""
会话隔离存储 —— 按 session_key 隔离消息与上下文摘要

v2.8.7 新增。

**这是 bot 化里最关键的数据隔离点。**

fr-cli 原有的上下文摘要在 ``~/.fr_cli/config.json`` 的 ``context.summaries``
命名空间里，key 是**全局** ``session_name``（默认为 ``"__default__"``），
并在 ``core/chat/pipeline_intent.py`` 里注入 system prompt。

后果：两个用户同时用 bot，A 的对话摘要会被喂进 B 的 system prompt ——
**跨用户数据串台**。这是比任何功能缺失都严重的问题。

本模块提供**按 session_key 隔离**的消息与摘要存储：
  - 消息：每个 session 独立的 messages 列表
  - 摘要：每个 session 独立的上下文摘要
  - 可选落盘到 ``~/.fr_cli/bot/sessions/``（进程重启后仍能续接）

不触碰全局 ``config.json`` 的 ``context.summaries``。
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

__all__ = ["SessionStore"]


class SessionStore:
    """按 session_key 隔离的消息 / 摘要存储（线程安全）。

    Attributes:
        persist_dir: 落盘目录；None 表示纯内存
        max_sessions: 内存中最多保留多少个会话（LRU 淘汰）
    """

    def __init__(self, persist_dir: Optional[Path] = None, max_sessions: int = 500):
        self.persist_dir = Path(persist_dir) if persist_dir else None
        self.max_sessions = max(1, int(max_sessions))
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._order: List[str] = []
        self._lock = threading.RLock()

    # ---------- 内部 ----------

    def _file_for(self, session_key: str) -> Optional[Path]:
        if not self.persist_dir:
            return None
        digest = hashlib.sha1(session_key.encode("utf-8")).hexdigest()[:16]
        safe = "".join(c for c in session_key if c.isalnum() or c in "-_")[:40]
        return self.persist_dir / f"{safe}_{digest}.json"

    def _touch(self, session_key: str) -> Dict[str, Any]:
        """取（或建）会话槽位，并把 session_key 移到 LRU 尾部。"""
        with self._lock:
            slot = self._sessions.get(session_key)
            if slot is None:
                slot = {"messages": [], "summary": "", "updated_at": 0.0}
                self._sessions[session_key] = slot
            if session_key in self._order:
                self._order.remove(session_key)
            self._order.append(session_key)
            while len(self._order) > self.max_sessions:
                evicted = self._order.pop(0)
                self._sessions.pop(evicted, None)
            return slot

    def _load(self, session_key: str) -> Dict[str, Any]:
        """从磁盘恢复会话（若存在）。"""
        path = self._file_for(session_key)
        if not path or not path.exists():
            return {"messages": [], "summary": "", "updated_at": 0.0}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {
                "messages": data.get("messages") or [],
                "summary": data.get("summary") or "",
                "updated_at": data.get("updated_at") or 0.0,
            }
        except Exception:
            return {"messages": [], "summary": "", "updated_at": 0.0}

    def _persist(self, session_key: str, slot: Dict[str, Any]) -> None:
        path = self._file_for(session_key)
        if not path:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(slot, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            tmp.replace(path)
        except Exception:
            pass

    # ---------- 公开接口 ----------

    def get_messages(self, session_key: str) -> List[Dict[str, Any]]:
        """取会话的消息列表副本。"""
        with self._lock:
            slot = self._sessions.get(session_key)
            if slot is None:
                slot = self._load(session_key)
                self._sessions[session_key] = slot
                if session_key not in self._order:
                    self._order.append(session_key)
            return list(slot.get("messages") or [])

    def set_messages(self, session_key: str, messages: List[Dict[str, Any]]) -> None:
        """整体替换会话消息。"""
        with self._lock:
            slot = self._touch(session_key)
            slot["messages"] = list(messages or [])
            slot["updated_at"] = time.time()
            self._persist(session_key, slot)

    def append_message(self, session_key: str, message: Dict[str, Any]) -> None:
        """追加一条消息。"""
        with self._lock:
            slot = self._touch(session_key)
            slot.setdefault("messages", []).append(message)
            slot["updated_at"] = time.time()
            self._persist(session_key, slot)

    def get_summary(self, session_key: str) -> str:
        """取会话的上下文摘要。"""
        with self._lock:
            slot = self._sessions.get(session_key)
            if slot is None:
                slot = self._load(session_key)
                self._sessions[session_key] = slot
            return slot.get("summary") or ""

    def set_summary(self, session_key: str, summary: str) -> None:
        """设置会话的上下文摘要。"""
        with self._lock:
            slot = self._touch(session_key)
            slot["summary"] = summary or ""
            slot["updated_at"] = time.time()
            self._persist(session_key, slot)

    def clear(self, session_key: str) -> None:
        """清空一个会话（重置上下文）。"""
        with self._lock:
            self._sessions.pop(session_key, None)
            if session_key in self._order:
                self._order.remove(session_key)
            path = self._file_for(session_key)
            if path and path.exists():
                try:
                    path.unlink()
                except Exception:
                    pass

    def list_sessions(self) -> List[str]:
        """列出所有已知 session_key。"""
        with self._lock:
            return list(self._order)

    def stats(self) -> Dict[str, Any]:
        """统计信息（用于 /bot_status）。"""
        with self._lock:
            return {
                "sessions": len(self._sessions),
                "messages": sum(len(s.get("messages") or []) for s in self._sessions.values()),
                "persist_dir": str(self.persist_dir) if self.persist_dir else None,
            }
