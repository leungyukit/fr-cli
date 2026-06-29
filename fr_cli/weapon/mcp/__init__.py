"""
MCP 工具管理器

基于官方 `mcp` SDK 实现 JSON-RPC over stdio / streamable_http / sse,支持:
- 启动/停止 MCP 子进程服务器
- tools/list 获取真实工具列表
- tools/call 同步调用工具
- resources/list + read_resource
- prompts/list + get_prompt

模块拆分:
- fr_cli.weapon.mcp.models  MCPServer dataclass + SDK 可用性
- fr_cli.weapon.mcp.manager  MCPServerManager 类 + 全局单例
- fr_cli.weapon.mcp        本文件(re-export, 向后兼容)

配置统一收敛到 ~/.fr_cli/config.json 的 mcp.servers 字段,
旧独立配置文件 ~/.fr_cli/mcp/servers.json 会在加载时一次性迁移。
"""
from fr_cli.weapon.mcp.manager import (
    MCPServerManager,
    MCPManager,
    _mcp_manager,
    _mcp_manager_lock,
    get_mcp_manager,
    load_from_config_file,
    reset_mcp_manager,
)
from fr_cli.weapon.mcp.models import (
    MCPServer,
    _MCP_AVAILABLE,
    _SSE_AVAILABLE,
    _STREAMABLE_HTTP_AVAILABLE,
)

__all__ = [
    "MCPServer",
    "MCPServerManager",
    "MCPManager",  # 向后兼容别名
    "_MCP_AVAILABLE",
    "_STREAMABLE_HTTP_AVAILABLE",
    "_SSE_AVAILABLE",
    "get_mcp_manager",
    "reset_mcp_manager",
    "load_from_config_file",
    "_mcp_manager",
    "_mcp_manager_lock",
]
