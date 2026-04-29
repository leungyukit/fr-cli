"""
Agent 管理器 —— 分身掌管者
负责 Agent 目录的创建、删除、列出，以及设定的读写
"""
import shutil
from pathlib import Path
from fr_cli.agent import AGENTS_DIR


PERSONA_FILE = "persona.md"
MEMORY_FILE = "memory.md"
SKILLS_FILE = "skills.md"
AGENT_CODE_FILE = "agent.py"
PROGRESS_FILE = "progress.json"
AGENT_CONFIG_FILE = "config.json"


def _agent_dir(name: str) -> Path:
    """获取指定 Agent 的洞府路径"""
    safe_name = "".join(c for c in name if c.isalnum() or c in ("_", "-"))
    if not safe_name:
        safe_name = "unnamed"
    return AGENTS_DIR / safe_name


def ensure_agents_dir():
    """确保 Agents 总洞府存在"""
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)


def agent_exists(name: str) -> bool:
    """检查分身是否已存在"""
    return _agent_dir(name).exists()


def create_agent_dir(name: str) -> Path:
    """为新的 Agent 开辟独立洞府"""
    ensure_agents_dir()
    d = _agent_dir(name)
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_agents() -> list:
    """列出所有已创建的分身"""
    if not AGENTS_DIR.exists():
        return []
    agents = []
    for d in AGENTS_DIR.iterdir():
        if d.is_dir() and (d / AGENT_CODE_FILE).exists():
            agents.append({
                "name": d.name,
                "path": str(d),
                "has_persona": (d / PERSONA_FILE).exists(),
                "has_memory": (d / MEMORY_FILE).exists(),
                "has_skills": (d / SKILLS_FILE).exists(),
                "has_config": (d / AGENT_CONFIG_FILE).exists(),
            })
    return agents


def delete_agent(name: str) -> bool:
    """彻底抹除一个分身及其所有记忆"""
    d = _agent_dir(name)
    if not d.exists():
        return False
    shutil.rmtree(d)
    return True


# ---------- 设定读写 ----------

def _read_md(agent_dir: Path, filename: str, default: str = "") -> str:
    f = agent_dir / filename
    if f.exists():
        return f.read_text(encoding="utf-8")
    return default


def _write_md(agent_dir: Path, filename: str, content: str):
    f = agent_dir / filename
    f.write_text(content, encoding="utf-8")


def load_persona(name: str) -> str:
    return _read_md(_agent_dir(name), PERSONA_FILE, "")


def save_persona(name: str, content: str):
    _write_md(_agent_dir(name), PERSONA_FILE, content)


def load_memory(name: str) -> str:
    return _read_md(_agent_dir(name), MEMORY_FILE, "")


def save_memory(name: str, content: str):
    _write_md(_agent_dir(name), MEMORY_FILE, content)


def load_skills(name: str) -> str:
    return _read_md(_agent_dir(name), SKILLS_FILE, "")


def save_skills(name: str, content: str):
    _write_md(_agent_dir(name), SKILLS_FILE, content)


def load_agent_code(name: str) -> str:
    return _read_md(_agent_dir(name), AGENT_CODE_FILE, "")


def save_agent_code(name: str, content: str):
    _write_md(_agent_dir(name), AGENT_CODE_FILE, content)


# ---------- 代码动态加载 ----------

def load_agent_module(name: str):
    """动态加载 Agent 的 Python 模块，返回模块对象"""
    import importlib.util
    agent_dir = _agent_dir(name)
    code_path = agent_dir / AGENT_CODE_FILE
    if not code_path.exists():
        return None
    spec = importlib.util.spec_from_file_location(f"fr_cli_agent_{name}", str(code_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------- 定时任务进度读写 ----------

import json
from datetime import datetime


def load_progress(name: str) -> dict:
    """读取 Agent 的定时任务执行进度"""
    f = _agent_dir(name) / PROGRESS_FILE
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_progress(name: str, data: dict):
    """保存 Agent 的定时任务执行进度"""
    f = _agent_dir(name) / PROGRESS_FILE
    try:
        f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def append_progress(name: str, result: str, user_input: str = "", status: str = "success", max_history: int = 50):
    """追加一条执行记录到 Agent 进度文件
    
    Args:
        result: 执行结果摘要
        user_input: 触发此次执行的输入（定时任务的 input 或用户输入）
        status: success / error
        max_history: 保留的最大历史记录数
    """
    progress = load_progress(name)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "input": user_input,
        "result": result,
        "status": status,
    }
    history = progress.get("history", [])
    history.append(entry)
    # 保留最近 max_history 条
    if len(history) > max_history:
        history = history[-max_history:]
    progress["history"] = history
    progress["latest"] = entry
    progress["counter"] = progress.get("counter", 0) + 1
    save_progress(name, progress)


def get_latest_progress(name: str) -> dict:
    """获取 Agent 最近一次执行进度"""
    progress = load_progress(name)
    return progress.get("latest", {})


def get_progress_history(name: str, limit: int = 10) -> list:
    """获取 Agent 执行历史记录"""
    progress = load_progress(name)
    history = progress.get("history", [])
    return history[-limit:] if history else []


# ---------- Agent 专属配置读写 ----------

def load_agent_config(name: str) -> dict:
    """读取 Agent 的专属模型配置（config.json）"""
    f = _agent_dir(name) / AGENT_CONFIG_FILE
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_agent_config(name: str, data: dict):
    """保存 Agent 的专属模型配置到 config.json"""
    d = _agent_dir(name)
    # 确保 Agent 洞府存在，避免在无效目录创建孤立文件
    d.mkdir(parents=True, exist_ok=True)
    f = d / AGENT_CONFIG_FILE
    try:
        f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
