"""
Gatekeeper 守护进程系统 —— 后台结界主宰
负责在主进程退出后继续维持定时任务与 Agent HTTP 等核心服务运转。
"""
from fr_cli.gatekeeper.manager import GatekeeperManager, get_manager

__all__ = ["GatekeeperManager", "get_manager"]
