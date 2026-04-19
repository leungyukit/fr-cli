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


def _agent_dir(name: str) -> Path:
    """获取指定 Agent 的洞府路径"""
    safe_name = "".join(c for c in name if c.isalnum() or c in ("_", "-"))
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
