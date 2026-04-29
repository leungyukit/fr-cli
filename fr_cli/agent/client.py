"""
Agent API 客户端 —— 支持本地调用和远程 HTTP API 调用
MasterAgent 通过此模块调用其他独立 Agent（本地或远程）
"""
import json
import urllib.request
import urllib.error

from fr_cli.agent.executor import run_agent
from fr_cli.agent.remote import list_remote_agents, get_remote_agent, add_remote_agent
from fr_cli.agent.manager import list_agents as list_local_agents


def discover_all_agents():
    """
    发现所有可用 Agent：本地 + 远程
    返回列表: [{"name": str, "type": "local|remote", "description": str}]
    """
    results = []

    # 本地 Agent
    for a in list_local_agents():
        results.append({
            "name": a["name"],
            "type": "local",
            "description": f"本地Agent (persona:{a['has_persona']}, memory:{a['has_memory']}, skills:{a['has_skills']})",
        })

    # 远程 Agent
    for name, cfg in list_remote_agents().items():
        results.append({
            "name": name,
            "type": "remote",
            "description": cfg.get("description", f"远程Agent @ {cfg['host']}:{cfg['port']}"),
        })

    return results


def call_agent(name, state, user_input="", **kwargs):
    """
    统一入口：调用 Agent（自动判断本地或远程）
    返回 (result, error)
    """
    # 优先检查本地 Agent
    from fr_cli.agent.manager import agent_exists
    if agent_exists(name):
        return run_agent(name, state, user_input=user_input, **kwargs)

    # 检查远程 Agent
    remote_cfg = get_remote_agent(name)
    if remote_cfg:
        return call_remote_agent(name, user_input, remote_cfg)

    return None, f"Agent [{name}] 未找到（本地和远程均无此Agent）"


def call_remote_agent(name, user_input, cfg):
    """
    通过 HTTP API 调用远程 Agent
    cfg: {"host": str, "port": int, "token": str}
    返回 (result, error)
    """
    host = cfg.get("host", "127.0.0.1")
    port = cfg.get("port", 17890)
    token = cfg.get("token", "")

    url = f"http://{host}:{port}/agents/{name}/run"
    payload = json.dumps({"input": user_input, "kwargs": {}}).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("error"):
                return None, f"远程Agent错误: {data['error']}"
            return data.get("result", ""), None
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
        return None, f"远程Agent HTTP {e.code}: {err_body}"
    except urllib.error.URLError as e:
        return None, f"远程Agent连接失败: {e.reason}"
    except Exception as e:
        return None, f"远程Agent调用异常: {e}"


def scan_remote_host(host, port, token):
    """
    扫描远程主机，获取其提供的 Agent 列表和服务能力
    返回 ({"service": ..., "agents": [...]}, error)
    """
    # 1. 获取能力声明
    cap_url = f"http://{host}:{port}/capabilities"
    req = urllib.request.Request(
        cap_url,
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            caps = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return None, f"无法获取远程能力声明: {e}"

    # 2. 获取 Agent 列表
    agents_url = f"http://{host}:{port}/agents"
    req = urllib.request.Request(
        agents_url,
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            agents_data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return None, f"无法获取远程Agent列表: {e}"

    return {
        "service": caps.get("service", "unknown"),
        "version": caps.get("version", "unknown"),
        "agents": agents_data.get("agents", []),
        "endpoints": caps.get("endpoints", {}),
        "host": host,
        "port": port,
        "token": token,
    }, None


def import_remote_agents(host, port, token, prefix=""):
    """
    一键导入远程主机的所有 Agent 到本地配置
    prefix: 可选前缀，避免与本地Agent重名
    返回 (imported_count, errors)
    """
    info, err = scan_remote_host(host, port, token)
    if err:
        return 0, [err]

    imported = 0
    errors = []
    for agent in info.get("agents", []):
        name = agent["name"]
        if prefix:
            name = f"{prefix}_{name}"
        try:
            add_remote_agent(
                name,
                host,
                port,
                token,
                description=f"远程Agent [{agent['name']}] @ {host}:{port}",
            )
            imported += 1
        except Exception as e:
            errors.append(f"导入 {name} 失败: {e}")

    return imported, errors
