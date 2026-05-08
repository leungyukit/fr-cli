"""
远程 Agent 管理 —— 配置其他用户电脑中已启用 API 的 fr-cli Agent

配置文件: ~/.fr_cli_remote_agents.json
格式:
{
    "agent_name": {
        "host": "192.168.1.100",
        "port": 8080,
        "token": "xxx",
        "description": "远程数据分析助手"
    }
}
"""
import json
from pathlib import Path

REMOTE_AGENTS_FILE = Path.home() / ".fr_cli_remote_agents.json"


def _load_remote_agents():
    if not REMOTE_AGENTS_FILE.exists():
        return {}
    try:
        with open(REMOTE_AGENTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_remote_agents(data):
    try:
        with open(REMOTE_AGENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def add_remote_agent(name, host, port, token, description=""):
    """添加远程 Agent 配置"""
    data = _load_remote_agents()
    data[name] = {
        "host": host,
        "port": int(port),
        "token": token,
        "description": description,
    }
    _save_remote_agents(data)
    return True


def remove_remote_agent(name):
    """删除远程 Agent 配置"""
    data = _load_remote_agents()
    if name in data:
        del data[name]
        _save_remote_agents(data)
        return True
    return False


def list_remote_agents():
    """列出所有远程 Agent"""
    return _load_remote_agents()


def get_remote_agent(name):
    """获取单个远程 Agent 配置"""
    data = _load_remote_agents()
    return data.get(name)
