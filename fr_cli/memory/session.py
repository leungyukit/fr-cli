"""
自动会话存档引擎 —— 按日期轮回
每次启动自动创建日期编号会话文件，实时追加对话记录。
"""
import json
import os
from datetime import datetime
from pathlib import Path

SESSION_DIR = Path.home() / ".fr_cli_sessions"


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


def create_session(messages):
    """创建新的自动会话文件，返回文件路径"""
    _ensure_dir()
    fname = _get_next_session_filename()
    fpath = SESSION_DIR / fname
    data = {
        "filename": fname,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "messages": messages,
    }
    try:
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return str(fpath)
    except Exception:
        return None


def update_session(fpath, messages):
    """更新会话文件中的消息记录"""
    if not fpath:
        return False
    try:
        path = Path(fpath)
        data = {}
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        data["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data["messages"] = messages
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def list_sessions():
    """列出所有会话，返回元数据列表"""
    files = _list_session_files()
    result = []
    for idx, fpath in enumerate(files, start=1):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            created = data.get("created_at", "未知")
            updated = data.get("updated_at", "未知")
            msg_count = len(data.get("messages", []))
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
        with open(target["path"], "r", encoding="utf-8") as f:
            data = json.load(f)
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
        os.remove(target["path"])
        return True
    except Exception:
        return False
