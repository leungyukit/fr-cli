"""
Agent API 客户端 —— 支持本地调用和远程 HTTP API 调用
MasterAgent 通过此模块调用其他独立 Agent（本地或远程）
"""
import json
import urllib.request
import urllib.error

from fr_cli.agent.executor import run_agent
from fr_cli.agent.remote import list_remote_agents, get_remote_agent, add_remote_agent
from fr_cli.agent.manager import list_agents as list_local_agents, load_agent_description
from fr_cli.core.result import Result


def discover_all_agents():
    """
    发现所有可用 Agent：本地 + 远程
    返回列表: [{"name": str, "type": "local|remote", "description": str}]
    """
    results = []

    # 本地 Agent
    for a in list_local_agents():
        desc = load_agent_description(a["name"]) or f"本地Agent (人设:{a['has_persona']}, 记忆:{a['has_memory']}, 技能:{a['has_skills']})"
        results.append({
            "name": a["name"],
            "type": "local",
            "description": desc,
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
    统一入口：调用 Agent（自动判断本地、远程或内置）
    返回 Result
    """
    # 优先检查本地 Agent
    from fr_cli.agent.manager import agent_exists
    if agent_exists(name):
        return run_agent(name, state, user_input=user_input, **kwargs)

    # 检查远程 Agent
    remote_cfg = get_remote_agent(name)
    if remote_cfg:
        return call_remote_agent(name, user_input, remote_cfg)

    # 检查内置 Agent
    from fr_cli.agent.dispatch import BUILTIN_AGENTS
    if name in BUILTIN_AGENTS:
        return call_builtin_agent(name, user_input, state)

    return Result.fail(f"Agent [{name}] 未找到（本地、远程和内置均无此Agent）")


def call_builtin_agent(name, user_input, state):
    """
    调用内置 Agent（@local / @remote / @db / @spider / @RAG / @stock 等）。
    由于内置 Agent 原实现直接打印输出，这里通过重定向 stdout/stderr 捕获结果。
    返回 Result[captured_output]
    """
    from fr_cli.agent.dispatch import BUILTIN_AGENTS
    route = BUILTIN_AGENTS.get(name)
    if not route:
        return None, f"未知内置 Agent: {name}"

    mod_path, func_name = route
    try:
        mod = __import__(mod_path, fromlist=[func_name])
        handler = getattr(mod, func_name)
    except Exception as e:
        return None, f"加载内置 Agent [{name}] 失败: {e}"

    # 构造 @name 前缀格式的输入，保持与 REPL 调用一致
    prefixed_input = f"@{name} {user_input}" if user_input else f"@{name}"

    import io
    from contextlib import redirect_stdout, redirect_stderr
    buf = io.StringIO()
    try:
        with redirect_stdout(buf), redirect_stderr(buf):
            handler(prefixed_input, state)
        return Result.ok(buf.getvalue())
    except Exception as e:
        return Result.fail(f"内置 Agent [{name}] 执行失败: {e}")


def call_remote_agent(name, user_input, cfg):
    """
    通过 HTTP API 调用远程 Agent
    cfg: {"host": str, "port": int, "token": str}
    返回 Result
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
                return Result.fail(f"远程Agent错误: {data['error']}")
            return Result.ok(data.get("result", ""))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
        return Result.fail(f"远程Agent HTTP {e.code}: {err_body}")
    except urllib.error.URLError as e:
        return Result.fail(f"远程Agent连接失败: {e.reason}")
    except Exception as e:
        return Result.fail(f"远程Agent调用异常: {e}")


def scan_remote_host(host, port, token):
    """
    扫描远程主机，获取其提供的 Agent 列表和服务能力
    返回 Result[{"service": ..., "agents": [...]}]
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
        return Result.fail(f"无法获取远程能力声明: {e}")

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
        return Result.fail(f"无法获取远程Agent列表: {e}")

    return Result.ok({
        "service": caps.get("service", "unknown"),
        "version": caps.get("version", "unknown"),
        "agents": agents_data.get("agents", []),
        "endpoints": caps.get("endpoints", {}),
        "host": host,
        "port": port,
        "token": token,
    })


def import_remote_agents(host, port, token, prefix=""):
    """
    一键导入远程主机的所有 Agent 到本地配置
    prefix: 可选前缀，避免与本地Agent重名
    返回 Result[(imported_count, errors)]
    """
    result = scan_remote_host(host, port, token)
    if result.is_fail():
        return Result.ok((0, [result.error]))

    imported = 0
    errors = []
    for agent in result.unwrap().get("agents", []):
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

    return Result.ok((imported, errors))
