"""
自动会话存档引擎 —— 按日期会话
每次启动自动创建日期编号会话文件，实时追加对话记录。
"""
from fr_cli.conf.paths import SESSIONS_AUTO_DIR
from datetime import datetime
from pathlib import Path
import json
import time
from fr_cli.core.store import JsonStore

SESSION_DIR = SESSIONS_AUTO_DIR  # from fr_cli.conf.paths


def _ensure_dir():
    SESSION_DIR.mkdir(parents=True, exist_ok=True)


def _list_session_files():
    """返回所有会话文件路径列表（按修改时间倒序）"""
    _ensure_dir()
    files = list(SESSION_DIR.glob("*.json"))
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def _get_next_session_filename():
    """根据日期生成下一个可用会话文件名 YYYY-MM-DD_01.json, YYYY-MM-DD_02.json ..."""
    _ensure_dir()
    today = datetime.now().strftime("%Y-%m-%d")
    existing = [f.stem for f in SESSION_DIR.glob(f"{today}_*.json")]
    nums = []
    for stem in existing:
        parts = stem.split("_")
        if len(parts) == 2 and parts[1].isdigit():
            nums.append(int(parts[1]))
    next_num = max(nums, default=0) + 1
    return f"{today}_{next_num:02d}.json"


def create_session(messages, session_id=None):
    """创建新的自动会话文件，返回文件路径
    :param session_id: 若提供，以此 UUID 作为文件名（如 abc123.json）
    """
    _ensure_dir()
    if session_id:
        fname = f"{session_id}.json"
    else:
        fname = _get_next_session_filename()
    fpath = SESSION_DIR / fname
    data = {
        "filename": fname,
        "session_id": session_id,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "messages": messages,
        # v2.8.7（长线-4）：v2 = 增量格式（snapshot + delta）
        # 首轮仍然把全量写进 snapshot，后续每轮只追加增量
        "version": 2,
    }
    try:
        JsonStore(fpath, default=dict).write(data)
        # 同步增量写入器的 meta（total_count / chain_hash）
        try:
            from fr_cli.memory.incremental import IncrementalSessionWriter, _chain_hash
            IncrementalSessionWriter(str(fpath))._write_meta({
                "delta_count": 0,
                "total_count": len(messages or []),
                "chain_hash": _chain_hash(messages or []),
                "last_snapshot_at": time.time(),
            })
        except Exception:
            pass
        return str(fpath)
    except Exception:
        return None


def update_session(fpath, messages):
    """更新会话文件中的消息记录（**增量写**）。

    v2.8.7（长线-4）：此前这里每轮都把整个 messages 列表重写一遍
    （1000 条消息 ≈ 1MB，每轮全量写一遍）。现在走增量：
    只把**新增**的消息追加进 delta 文件，累计到阈值再做一次全量 snapshot。

    两种情况退回全量重写：
    - 历史被截断（``/undo`` 撤销了几轮）—— 增量语义不再成立
    - 增量写入异常 —— 退回旧的整份写，保证不丢数据
    """
    if not fpath:
        return False
    try:
        from fr_cli.memory.incremental import IncrementalSessionWriter

        writer = IncrementalSessionWriter(str(fpath))
        persisted = writer.total_count()
        # 增量成立的前提：已持久化那段**原样未改**。
        # writer.matches() 用链式哈希校验 —— 覆盖三种"不能增量"的情况：
        #   历史被截断（/undo）、原地改写、system prompt 被替换
        if len(messages) < persisted or not writer.matches(messages):
            writer.rewrite(messages)
        elif len(messages) > persisted:
            writer.append(messages[persisted:])
        return True
    except Exception:
        pass

    # 降级路径：整份写（旧行为）
    try:
        path = Path(fpath)
        store = JsonStore(path, default=dict)
        data = store.read() if path.exists() else {}
        data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data["messages"] = messages
        store.write(data)
        return True
    except Exception:
        return False


def list_sessions():
    """列出所有会话，返回元数据列表"""
    files = _list_session_files()
    result = []
    for idx, fpath in enumerate(files, start=1):
        try:
            data = JsonStore(fpath, default=dict).read()
            created = data.get("created_at", "未知")
            updated = data.get("updated_at", "未知")
            # v2.8.7（长线-4）：v2 格式的消息分布在 snapshot + delta 里，
            # 直接 len(messages) 会少算 —— 优先读 meta 里的 total_count
            msg_count = _session_message_count(fpath, data)
            result.append({
                "index": idx,
                "filename": fpath.name,
                "created_at": created,
                "updated_at": updated,
                "msg_count": msg_count,
                "path": str(fpath),
            })
        except Exception:
            pass
    return result


def _session_message_count(fpath, data=None) -> int:
    """会话消息条数（兼容 v1 / v2 两种格式）"""
    try:
        if data is None:
            data = JsonStore(fpath, default=dict).read()
        if data.get("version") == 2:
            # meta 里是权威计数（O(1)）；没有则回落到 snapshot + delta 实际行数
            meta_path = Path(fpath).with_suffix(".meta")
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                if "total_count" in meta:
                    return int(meta["total_count"])
            except Exception:
                pass
            from fr_cli.memory.incremental import read_session_full_data
            return len(read_session_full_data(str(fpath)).get("messages", []))
        return len(data.get("messages", []))
    except Exception:
        return 0


def load_session(index, current_system_prompt=None):
    """按索引加载会话消息
    :param index: 1-based 索引
    :param current_system_prompt: 若提供，将覆盖第一条 system prompt
    :return: (success, messages, filename)
    """
    sessions = list_sessions()
    if not sessions or index < 1 or index > len(sessions):
        return False, None, None
    target = sessions[index - 1]
    try:
        # v2.8.7（长线-4）：v2 格式要合并 snapshot + delta
        from fr_cli.memory.incremental import read_session_full_data
        data = read_session_full_data(target["path"])
        msgs = data.get("messages", [])
        if current_system_prompt and msgs and msgs[0]["role"] == "system":
            msgs[0]["content"] = current_system_prompt
        elif current_system_prompt:
            msgs.insert(0, {"role": "system", "content": current_system_prompt})
        return True, msgs, target["filename"]
    except Exception:
        return False, None, None


def delete_session(index):
    """按索引删除会话文件"""
    sessions = list_sessions()
    if not sessions or index < 1 or index > len(sessions):
        return False
    target = sessions[index - 1]
    try:
        JsonStore(target["path"]).delete()
        # v2.8.7（长线-4）：增量格式的附属文件要一起删，否则留下孤儿
        base = Path(target["path"])
        for suffix in (".delta", ".meta"):
            try:
                side = base.with_suffix(suffix)
                if side.exists():
                    side.unlink()
            except Exception:
                pass
        return True
    except Exception:
        return False
