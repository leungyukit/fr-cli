"""
MCP 工具管理器

基于官方 `mcp` SDK 实现 JSON-RPC over stdio，支持：
- 启动/停止 MCP 子进程服务器
- tools/list 获取真实工具列表
- tools/call 同步调用工具

配置统一收敛到 ~/.fr_cli/config.json 的 mcp.servers 字段，
旧独立配置文件 ~/.fr_cli/mcp/servers.json 会在加载时一次性迁移。
"""

import os
import json
import threading
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

from fr_cli.conf.paths import MCP_SERVERS_FILE
from fr_cli.conf.config import save_config


try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.types import TextContent
    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False


@dataclass
class MCPServer:
    """MCP 服务器配置"""
    name: str
    transport: str  # stdio, http, sse
    command: Optional[str] = None
    args: Optional[List[str]] = None
    url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    auth_type: Optional[str] = None  # oauth, api_key
    enabled: bool = True

    def to_dict(self) -> Dict:
        return asdict(self)


class MCPServerManager:
    """MCP 服务器管理器（基于 mcp SDK）"""

    def __init__(self, cfg: dict = None):
        """初始化管理器，cfg 为 ~/.fr_cli/config.json 的内容。

        未传入 cfg 时创建一个空管理器（仅用于一次性从文件加载的场景）。
        """
        self.cfg = cfg or {}
        self.servers: Dict[str, MCPServer] = {}
        self._load()

    def _load(self):
        """加载配置：优先从主配置 cfg["mcp"]["servers"] 读取；
        若旧文件 ~/.fr_cli/mcp/servers.json 仍存在，则做一次迁移合并。
        """
        # 1. 主配置为真相源
        self._load_from_cfg(self.cfg)

        # 2. 一次性迁移旧独立配置文件
        old_path = str(MCP_SERVERS_FILE)
        if os.path.exists(old_path):
            try:
                with open(old_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for name, cfg in data.items():
                    if name not in self.servers:
                        self.servers[name] = MCPServer(name=name, **cfg)
                # 把旧文件内容合并到主配置并落盘
                self._save_to_cfg()
                try:
                    os.rename(old_path, old_path + ".migrated")
                except Exception:
                    pass
            except Exception:
                pass

    def _load_from_cfg(self, cfg: dict):
        """从主配置字典加载 MCP 服务器列表"""
        mcp_cfg = (cfg or {}).get("mcp") or {}
        servers = mcp_cfg.get("servers") or []
        if not isinstance(servers, list):
            return
        for srv in servers:
            if not isinstance(srv, dict):
                continue
            name = srv.get("name")
            if not name:
                continue
            try:
                self.servers[name] = MCPServer(
                    name=name,
                    transport=srv.get("transport", "stdio"),
                    command=srv.get("command"),
                    args=srv.get("args"),
                    url=srv.get("url"),
                    headers=srv.get("headers"),
                    auth_type=srv.get("auth_type"),
                    enabled=srv.get("enabled", True),
                )
            except Exception:
                pass

    def _save_to_cfg(self):
        """把当前 servers 写回主配置的 mcp.servers 字段"""
        if not self.cfg:
            return
        mcp_cfg = self.cfg.setdefault("mcp", {})
        mcp_cfg["servers"] = [srv.to_dict() for srv in self.servers.values()]

    def _save(self):
        """持久化：更新主配置并调用 save_config 原子写入"""
        self._save_to_cfg()
        if self.cfg:
            save_config(self.cfg)

    def add_server(self, name: str, transport: str,
                   command: str = None, args: List[str] = None,
                   url: str = None, headers: Dict = None, auth_type: str = None):
        """添加 MCP 服务器"""
        server = MCPServer(
            name=name,
            transport=transport,
            command=command,
            args=args or [],
            url=url,
            headers=headers,
            auth_type=auth_type,
        )
        self.servers[name] = server
        self._save()
        return True

    def del_server(self, name: str):
        """删除 MCP 服务器"""
        if name not in self.servers:
            return False
        self.servers.pop(name)
        self._save()
        return True

    def enable_server(self, name: str):
        """启用 MCP 服务器"""
        if name not in self.servers:
            return False
        self.servers[name].enabled = True
        self._save()
        return True

    def disable_server(self, name: str):
        """禁用 MCP 服务器"""
        if name not in self.servers:
            return False
        self.servers[name].enabled = False
        self._save()
        return True

    def list_servers(self) -> List[Dict]:
        """列出所有 MCP 服务器"""
        return [srv.to_dict() for srv in self.servers.values()]

    def get_server(self, name: str) -> Optional[MCPServer]:
        """获取指定服务器配置"""
        return self.servers.get(name)

    def _server_to_params(self, srv: MCPServer) -> Optional[StdioServerParameters]:
        """将内部 MCPServer 转换为 mcp SDK 的 StdioServerParameters"""
        if not srv.command:
            return None
        env = os.environ.copy()
        return StdioServerParameters(
            command=srv.command,
            args=srv.args or [],
            env=env,
        )

    async def _get_tools_async(self, srv: MCPServer) -> List[Dict]:
        """异步获取某服务器的工具列表"""
        params = self._server_to_params(srv)
        if params is None:
            return []
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                tools = []
                for tool in result.tools:
                    tools.append({
                        "name": tool.name,
                        "description": tool.description or "",
                        "inputSchema": tool.inputSchema,
                        "server": srv.name,
                    })
                return tools

    def get_tools(self, name: str) -> List[Dict]:
        """获取 MCP 工具列表（真实调用 tools/list）"""
        if not _MCP_AVAILABLE:
            return []
        if name not in self.servers:
            return []
        srv = self.servers[name]
        if not srv.enabled:
            return []
        if srv.transport != "stdio":
            return []
        try:
            import asyncio
            return asyncio.run(self._get_tools_async(srv))
        except Exception as e:
            return [{
                "name": f"{name}_error",
                "description": f"获取工具列表失败: {e}",
                "inputSchema": {"type": "object", "properties": {}},
                "server": name,
                "_error": True,
            }]

    def list_all_tools(self) -> List[Dict]:
        """列出所有已启用服务器的工具"""
        all_tools = []
        for name in self.servers:
            all_tools.extend(self.get_tools(name))
        return all_tools

    def get_server_tools_desc(self) -> str:
        """生成所有 MCP 服务器的描述文本（注入到 system prompt）"""
        if not self.servers:
            return ""
        lines = ["[MCP servers]"]
        for name, srv in self.servers.items():
            enabled = "enabled" if srv.enabled else "DISABLED"
            lines.append(f"- {name} ({enabled}, transport={srv.transport})")
            if srv.transport == "stdio" and srv.command:
                args_repr = ", ".join(repr(a) for a in (srv.args or []))
                lines.append(f"  command: {srv.command}({args_repr})")
            elif srv.transport in ("http", "sse") and srv.url:
                lines.append(f"  url: {srv.url}")
        return "\n".join(lines)

    async def _call_tool_async(self, srv: MCPServer, tool_name: str, arguments: Dict) -> Any:
        """异步调用 MCP 工具"""
        params = self._server_to_params(srv)
        if params is None:
            return None, f"MCP server [{srv.name}] 缺少启动命令"
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments=arguments or {})
                texts = []
                for content in result.content:
                    if isinstance(content, TextContent):
                        texts.append(content.text)
                    else:
                        texts.append(str(content))
                return "\n".join(texts), None

    def call_tool_sync(self, server_name: str, tool_name: str, arguments: Dict) -> Any:
        """同步调用 MCP 工具"""
        if not _MCP_AVAILABLE:
            return None, "MCP SDK 未安装，请执行: pip install mcp"
        if server_name not in self.servers:
            return None, f"Unknown MCP server: {server_name}"
        srv = self.servers[server_name]
        if not srv.enabled:
            return None, f"MCP server [{server_name}] 已禁用"
        if srv.transport != "stdio":
            return None, (
                f"MCP server [{server_name}] 传输类型 '{srv.transport}' 暂不支持同步调用。"
                "当前仅支持 stdio 传输。"
            )
        try:
            import asyncio
            return asyncio.run(self._call_tool_async(srv, tool_name, arguments))
        except Exception as e:
            return None, f"MCP 调用失败: {e}"

    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict) -> Any:
        """异步调用 MCP 工具"""
        if not _MCP_AVAILABLE:
            raise NotImplementedError("MCP SDK 未安装")
        if server_name not in self.servers:
            raise ValueError(f"Unknown MCP server: {server_name}")
        srv = self.servers[server_name]
        return await self._call_tool_async(srv, tool_name, arguments)

    @staticmethod
    def from_config_file(config_file: str) -> 'MCPServerManager':
        """从标准 MCP 配置文件加载"""
        manager = MCPServerManager()

        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)

                servers = config.get("mcpServers", {})
                for name, cfg in servers.items():
                    if "command" in cfg:
                        manager.add_server(
                            name=name,
                            transport="stdio",
                            command=cfg["command"],
                            args=cfg.get("args", [])
                        )
                    elif "url" in cfg:
                        manager.add_server(
                            name=name,
                            transport="http",
                            url=cfg["url"],
                            headers=cfg.get("headers")
                        )
            except Exception as e:
                print(f"加载 MCP 配置失败: {e}")

        return manager


# 全局实例（线程安全单例）
_mcp_manager: Optional[MCPServerManager] = None
_mcp_manager_lock = threading.Lock()


def get_mcp_manager(cfg: dict = None) -> MCPServerManager:
    """获取 MCP 管理器（线程安全单例）"""
    global _mcp_manager
    # 双重检查：避免每次调用都加锁
    if _mcp_manager is None:
        with _mcp_manager_lock:
            if _mcp_manager is None:
                _mcp_manager = MCPServerManager(cfg=cfg)
    return _mcp_manager


def reset_mcp_manager():
    """重置全局单例（仅用于测试或热加载新配置）"""
    global _mcp_manager
    with _mcp_manager_lock:
        _mcp_manager = None


def load_from_config_file(config_file: str) -> MCPServerManager:
    """从配置文件加载 MCP 服务器"""
    return MCPServerManager.from_config_file(config_file)


MCPManager = MCPServerManager
