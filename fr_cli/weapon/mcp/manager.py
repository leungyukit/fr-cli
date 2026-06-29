"""
MCP Server Manager —— 单例 + 配置管理 + tools/resources/prompts 统一调度

模块拆分:
- fr_cli.weapon.mcp.models        MCPServer dataclass + SDK 可用性
- fr_cli.weapon.mcp.manager       本文件(MCPServerManager 主类 + 全局单例)
- fr_cli.weapon.mcp.manager_core  初始化 + 配置加载/保存 mixin
- fr_cli.weapon.mcp.manager_servers  服务器 CRUD mixin
- fr_cli.weapon.mcp.manager_tools 工具发现 mixin
- fr_cli.weapon.mcp.manager_resources 资源 mixin
- fr_cli.weapon.mcp.manager_prompts 提示 mixin
- fr_cli.weapon.mcp.manager_invocation 工具调用 mixin
- fr_cli.weapon.mcp               re-export(向后兼容)
"""
from __future__ import annotations

import threading
from typing import Optional

from fr_cli.weapon.mcp.manager_core import MCPServerManagerCoreMixin
from fr_cli.weapon.mcp.manager_invocation import MCPServerManagerInvocationMixin
from fr_cli.weapon.mcp.manager_prompts import MCPServerManagerPromptsMixin
from fr_cli.weapon.mcp.manager_resources import MCPServerManagerResourcesMixin
from fr_cli.weapon.mcp.manager_servers import MCPServerManagerServersMixin
from fr_cli.weapon.mcp.manager_tools import MCPServerManagerToolsMixin


class MCPServerManager(
    MCPServerManagerCoreMixin,
    MCPServerManagerServersMixin,
    MCPServerManagerToolsMixin,
    MCPServerManagerResourcesMixin,
    MCPServerManagerPromptsMixin,
    MCPServerManagerInvocationMixin,
):
    """MCP 服务器管理器(基于 mcp SDK)

    6 个 mixin 组合:
      - CoreMixin         __init__ + 配置 load/save + from_config_file
      - ServersMixin      add/del/enable/disable/list/get server
      - ToolsMixin        tools/list + 描述注入
      - ResourcesMixin    resources/list + read_resource_sync
      - PromptsMixin      prompts/list + get_prompt_sync
      - InvocationMixin   call_tool_sync / call_tool

    全局单例通过 get_mcp_manager() 获取;测试可用 reset_mcp_manager() 重置。
    """

    pass


# ==================== 全局单例 ====================

_mcp_manager: Optional[MCPServerManager] = None
_mcp_manager_lock = threading.Lock()


def get_mcp_manager(cfg: dict = None) -> MCPServerManager:
    """获取 MCP 管理器(线程安全单例)"""
    global _mcp_manager
    # 双重检查:避免每次调用都加锁
    if _mcp_manager is None:
        with _mcp_manager_lock:
            if _mcp_manager is None:
                _mcp_manager = MCPServerManager(cfg=cfg)
    return _mcp_manager


def reset_mcp_manager():
    """重置全局单例(仅用于测试或热加载新配置)"""
    global _mcp_manager
    with _mcp_manager_lock:
        _mcp_manager = None


def load_from_config_file(config_file: str) -> MCPServerManager:
    """从配置文件加载 MCP 服务器"""
    return MCPServerManager.from_config_file(config_file)


# 向后兼容别名
MCPManager = MCPServerManager
