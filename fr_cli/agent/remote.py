"""
远程 Agent 管理 —— 配置其他用户电脑中已启用 API 的 fr-cli Agent

配置统一收敛到 ~/.fr_cli/config.json 的 remote.agents 命名空间。
旧文件 ~/.fr_cli/remote/agents.json 会在首次加载时一次性迁移。
"""
from fr_cli.conf.config import load_namespace, save_namespace
from fr_cli.conf.paths import REMOTE_AGENTS_FILE

_NS_KEY = "remote"
REMOTE_AGENTS_FILE = REMOTE_AGENTS_FILE  # 保留用于一次性迁移


def _load_remote_agents():
    ns = load_namespace(_NS_KEY, default={"agents": {}}, old_path=REMOTE_AGENTS_FILE)
    return ns.get("agents", {})


def _save_remote_agents(data):
    ns = load_namespace(_NS_KEY, default={"agents": {}})
    ns["agents"] = data
    save_namespace(_NS_KEY, ns)


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
