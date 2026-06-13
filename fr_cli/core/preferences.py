"""
个人偏好学习 —— 记录用户习惯，下次启动自动应用

记录在 ~/.fr_cli/preferences.json
"""
import json
import time
from pathlib import Path
from typing import Dict

from fr_cli.conf.paths import ROOT

_PREF_FILE = ROOT / "preferences.json"

_DEFAULT_PREF = {
    "model": "",                  # 偏好的模型
    "provider": "",               # 偏好的 provider
    "lang": "zh",                 # 偏好的语言
    "command_usage": {},          # {cmd_name: count}
    "agent_usage": {},            # {agent_name: count}
    "last_used": 0,               # 上次使用时间戳
    "preferred_thinking_mode": "direct",
    "common_directories": [],     # 常用的工作目录
}


def _load_pref() -> Dict:
    """读取偏好（不存在返回默认）"""
    if not _PREF_FILE.exists():
        return _DEFAULT_PREF.copy()
    try:
        data = json.loads(_PREF_FILE.read_text(encoding="utf-8"))
        # 合并默认（避免缺字段）
        for k, v in _DEFAULT_PREF.items():
            data.setdefault(k, v)
        return data
    except Exception:
        return _DEFAULT_PREF.copy()


def _save_pref(data: Dict):
    """保存偏好（原子写入）"""
    import os
    import tempfile
    _PREF_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=_PREF_FILE.parent, suffix=".tmp")
    try:
        os.chmod(tmp, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        Path(tmp).replace(_PREF_FILE)
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass


def record_command(cmd_name: str):
    """记录一次命令使用"""
    p = _load_pref()
    p["command_usage"][cmd_name] = p["command_usage"].get(cmd_name, 0) + 1
    p["last_used"] = int(time.time())
    _save_pref(p)


def record_agent(agent_name: str):
    """记录一次 Agent 使用"""
    p = _load_pref()
    p["agent_usage"][agent_name] = p["agent_usage"].get(agent_name, 0) + 1
    p["last_used"] = int(time.time())
    _save_pref(p)


def set_preferred_model(provider: str, model: str):
    p = _load_pref()
    p["provider"] = provider
    p["model"] = model
    _save_pref(p)


def get_top_commands(n: int = 5) -> list:
    """获取最常用的 N 个命令（按频率排序）"""
    p = _load_pref()
    sorted_cmds = sorted(p["command_usage"].items(), key=lambda x: x[1], reverse=True)
    return sorted_cmds[:n]


def render_preference_hints() -> str:
    """渲染偏好提示（注入 system prompt）"""
    p = _load_pref()
    lines = []
    if p.get("model"):
        lines.append(f"- 用户最常用模型: {p['provider']}/{p['model']}")
    top = get_top_commands(3)
    if top:
        cmd_list = ", ".join(f"{cmd}({count})" for cmd, count in top)
        lines.append(f"- 用户常用命令: {cmd_list}")
    if p.get("common_directories"):
        lines.append(f"- 常用目录: {', '.join(p['common_directories'][:3])}")
    if not lines:
        return ""
    return "\n[用户偏好]\n" + "\n".join(lines)
