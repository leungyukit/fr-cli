"""
Agent @ 前缀调度器 —— 让用户在 REPL 中通过 @agent_name 直接调用分身

用法：
    >>> @coder 帮我写一个 Python 快速排序
    >>> @local 查看当前目录下最大的10个文件
    >>> @stock 查询茅台股价
"""
from fr_cli.ui.ui import CYAN, RED, RESET, DIM
from fr_cli.agent.manager import agent_exists
from fr_cli.agent.executor import run_agent


# 内置 Agent 路由表：name -> (module_path, function_name)
# 内置 Agent 优先于用户 Agent，避免用户创建同名 Agent 覆盖系统功能
BUILTIN_AGENTS = {
    "local": ("fr_cli.agent.builtins.local", "handle_local"),
    "remote": ("fr_cli.agent.builtins.remote", "handle_remote"),
    "spider": ("fr_cli.agent.builtins.spider", "handle_spider"),
    "db": ("fr_cli.agent.builtins.db", "handle_db"),
    "RAG": ("fr_cli.agent.builtins.rag", "handle_rag"),
    "stock": ("fr_cli.agent.builtins.stock", "handle_stock"),
}


def _parse_at_command(text: str):
    """
    解析 @agent_name 任务内容
    返回 (agent_name, user_input)
    """
    text = text.strip()
    if not text.startswith("@"):
        return None, None
    parts = text[1:].split(None, 1)
    if not parts:
        return None, None
    agent_name = parts[0].strip()
    user_input = parts[1].strip() if len(parts) > 1 else ""
    return agent_name, user_input


def _invoke_builtin_agent(agent_name: str, text: str, state) -> bool:
    """调用内置 Agent，返回是否成功"""
    route = BUILTIN_AGENTS.get(agent_name)
    if not route:
        return False
    mod_path, func_name = route
    try:
        mod = __import__(mod_path, fromlist=[func_name])
        handler = getattr(mod, func_name)
        handler(text, state)
        return True
    except Exception as e:
        print(f"{RED}❌ 内置 Agent [{agent_name}] 执行失败: {e}{RESET}")
        return True


def dispatch_agent_call(state, text: str) -> bool:
    """
    调度 @agent_name 调用。

    Args:
        state: AppState 实例
        text: 用户原始输入（如 "@coder 写代码"）

    Returns:
        bool: True 表示已成功处理并执行；False 表示未命中或 Agent 不存在，
              调用方应继续原有流程。
    """
    agent_name, user_input = _parse_at_command(text)
    if agent_name is None:
        return False

    # 1) 内置 Agent 优先路由
    if _invoke_builtin_agent(agent_name, text, state):
        return True

    # 2) 用户自定义 Agent
    if not agent_exists(agent_name):
        print(f"{RED}❌ Agent [{agent_name}] 不存在。{RESET}")
        print(f"{DIM}   使用 /agent_create {agent_name} <描述> 创建，或 /agent_list 查看已有分身。{RESET}")
        return True

    print(f"{CYAN}🧙 正在召唤 Agent [{agent_name}]...{RESET}")
    result = run_agent(agent_name, state, user_input=user_input)
    if result.is_fail():
        print(f"{RED}❌ Agent [{agent_name}] 执行失败: {result.error}{RESET}")
    else:
        print(f"{result.unwrap()}")
    return True
