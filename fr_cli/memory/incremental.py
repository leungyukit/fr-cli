"""
增量持久化 —— 大 messages 列表的优化写入

痛点:
- update_session 每次写整个 messages JSON,1000 条消息 = ~1MB 文件
- 每轮对话都全量写,IO 浪费

方案:
- 增量写(append last delta):只把新消息追加到 JSONL-like 格式
- 周期 full snapshot:每 N 次增量后写一次完整文件,清理增量
- 启动时合并:读取最新 snapshot + 后续增量 = 完整 messages

存储格式:
```
sessions/auto/2026-06-28_01.json      <- snapshot(全量)
sessions/auto/2026-06-28_01.delta     <- 增量文件(每行一个 message)
sessions/auto/2026-06-28_01.meta      <- 元数据(增量计数 / 上次 snapshot 大小)
```

读:
- read snapshot messages
- 遍历 delta 文件每一行(增量 messages)
- 合并返回

写:
- 新消息追加到 delta
- delta 行数 >= threshold 时(默认 20),触发 snapshot:
  - 读 snapshot + delta → 写新 snapshot
  - 清空 delta
  - 重置 meta
"""
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any


SNAPSHOT_EXT = ".json"
DELTA_EXT = ".delta"
META_EXT = ".meta"

# 默认阈值:delta 累积 20 条消息后做一次 snapshot
DEFAULT_SNAPSHOT_THRESHOLD = 20


class IncrementalSessionWriter:
    """增量会话写入器

    Args:
        snapshot_path: snapshot 文件路径(通常是 .json)
        threshold: delta 累积多少条后做一次 snapshot
    """

    def __init__(self, snapshot_path: str, threshold: int = DEFAULT_SNAPSHOT_THRESHOLD):
        self.snapshot_path = Path(snapshot_path)
        self.delta_path = self.snapshot_path.with_suffix(DELTA_EXT)
        self.meta_path = self.snapshot_path.with_suffix(META_EXT)
        self.threshold = threshold
        self._ensure_files()

    def _ensure_files(self):
        """确保所有文件存在"""
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.snapshot_path.exists():
            self._write_snapshot([])
        if not self.meta_path.exists():
            self._write_meta({"delta_count": 0, "last_snapshot_at": time.time()})

    def _write_snapshot(self, messages: List[Dict[str, Any]]):
        data = {
            "filename": self.snapshot_path.name,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "messages": messages,
            "version": 2,  # 标识增量格式
        }
        _atomic_write_json(self.snapshot_path, data)

    def _write_meta(self, meta: Dict[str, Any]):
        _atomic_write_json(self.meta_path, meta)

    def _read_meta(self) -> Dict[str, Any]:
        if not self.meta_path.exists():
            return {"delta_count": 0}
        try:
            with open(self.meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"delta_count": 0}

    def _append_delta(self, messages: List[Dict[str, Any]]):
        """追加消息到 delta 文件"""
        if not messages:
            return
        with open(self.delta_path, "a", encoding="utf-8") as f:
            for msg in messages:
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    def _clear_delta(self):
        """清空 delta 文件"""
        if self.delta_path.exists():
            self.delta_path.unlink()

    def append(self, new_messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """追加新消息(增量)

        Returns:
            {"snapshot_triggered": bool, "delta_count": int}
        """
        if not new_messages:
            return {"snapshot_triggered": False, "delta_count": self._read_meta().get("delta_count", 0)}

        self._append_delta(new_messages)

        meta = self._read_meta()
        new_delta_count = meta.get("delta_count", 0) + len(new_messages)
        snapshot_triggered = False

        if new_delta_count >= self.threshold:
            # 触发 snapshot
            all_messages = self.read_all()
            self._write_snapshot(all_messages)
            self._clear_delta()
            new_delta_count = 0
            snapshot_triggered = True

        meta["delta_count"] = new_delta_count
        meta["last_append_at"] = time.time()
        self._write_meta(meta)

        return {"snapshot_triggered": snapshot_triggered, "delta_count": new_delta_count}

    def read_all(self) -> List[Dict[str, Any]]:
        """读取所有消息(snapshot + delta)"""
        messages: List[Dict[str, Any]] = []
        if self.snapshot_path.exists():
            try:
                with open(self.snapshot_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                messages = data.get("messages", [])
            except Exception:
                pass

        if self.delta_path.exists():
            try:
                with open(self.delta_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            messages.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            except Exception:
                pass

        return messages

    def snapshot_now(self) -> int:
        """强制做一次 snapshot,返回 delta 清掉的行数"""
        meta = self._read_meta()
        prev_delta = meta.get("delta_count", 0)
        if prev_delta == 0:
            return 0
        all_messages = self.read_all()
        self._write_snapshot(all_messages)
        self._clear_delta()
        meta["delta_count"] = 0
        meta["last_snapshot_at"] = time.time()
        self._write_meta(meta)
        return prev_delta

    def stats(self) -> Dict[str, Any]:
        """统计信息"""
        meta = self._read_meta()
        snapshot_size = self.snapshot_path.stat().st_size if self.snapshot_path.exists() else 0
        delta_size = self.delta_path.stat().st_size if self.delta_path.exists() else 0
        return {
            "snapshot_path": str(self.snapshot_path),
            "snapshot_size_bytes": snapshot_size,
            "delta_size_bytes": delta_size,
            "delta_count": meta.get("delta_count", 0),
            "threshold": self.threshold,
            "last_snapshot_at": meta.get("last_snapshot_at"),
            "last_append_at": meta.get("last_append_at"),
        }


def _atomic_write_json(path: Path, data: dict):
    """原子写 JSON(临时文件 + rename)"""
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise


# 包装 update_session,自动用增量
def update_session_incremental(fpath: str, new_messages: List[Dict[str, Any]],
                                threshold: int = DEFAULT_SNAPSHOT_THRESHOLD) -> Dict[str, Any]:
    """增量更新会话(向后兼容)

    Args:
        fpath: snapshot 文件路径(.json)
        new_messages: 这次要追加的新消息(增量)
        threshold: delta 阈值

    Returns:
        {"ok": bool, "snapshot_triggered": bool, "delta_count": int}
    """
    try:
        writer = IncrementalSessionWriter(fpath, threshold=threshold)
        result = writer.append(new_messages)
        return {"ok": True, **result}
    except Exception as e:
        return {"ok": False, "error": str(e), "snapshot_triggered": False, "delta_count": 0}


def read_session_full(fpath: str) -> List[Dict[str, Any]]:
    """读取完整会话(snapshot + delta)"""
    try:
        writer = IncrementalSessionWriter(fpath)
        return writer.read_all()
    except Exception:
        return []


# 兼容旧 API:全量读(返回 dict 包含 messages + meta)
def read_session_full_data(fpath: str) -> Dict[str, Any]:
    """读取完整会话数据(含元信息)"""
    p = Path(fpath)
    if not p.exists():
        return {"messages": [], "filename": p.name, "version": 2}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 如果是 v2 格式,合并 delta
        if data.get("version") == 2:
            delta_p = p.with_suffix(DELTA_EXT)
            if delta_p.exists():
                try:
                    with open(delta_p, "r", encoding="utf-8") as df:
                        for line in df:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                data["messages"].append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
                except Exception:
                    pass
        return data
    except Exception:
        return {"messages": [], "filename": p.name}
