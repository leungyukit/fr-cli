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

# v2.8+:Streamable HTTP + SSE 支持
try:
    from mcp.client.streamable_http import streamablehttp_client
    _STREAMABLE_HTTP_AVAILABLE = True
except ImportError:
    _STREAMABLE_HTTP_AVAILABLE = False

try:
    from mcp.client.sse import sse_client
    _SSE_AVAILABLE = True
except ImportError:
    _SSE_AVAILABLE = False


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
        """异步获取某服务器的工具列表(支持 stdio / streamable_http / sse)"""
        if srv.transport == "stdio":
            params = self._server_to_params(srv)
            if params is None:
                return []
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await self._list_tools(session, srv.name)
        elif srv.transport in ("streamable_http", "http"):
            if not _STREAMABLE_HTTP_AVAILABLE:
                return [{"name": f"{srv.name}_error",
                         "description": "streamable_http 不可用,请升级 mcp SDK",
                         "inputSchema": {"type": "object"},
                         "server": srv.name, "_error": True}]
            headers = srv.headers or {}
            async with streamablehttp_client(srv.url, headers=headers) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await self._list_tools(session, srv.name)
        elif srv.transport == "sse":
            if not _SSE_AVAILABLE:
                return [{"name": f"{srv.name}_error",
                         "description": "SSE 不可用,请升级 mcp SDK",
                         "inputSchema": {"type": "object"},
                         "server": srv.name, "_error": True}]
            headers = srv.headers or {}
            async with sse_client(srv.url, headers=headers) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await self._list_tools(session, srv.name)
        return []

    @staticmethod
    async def _list_tools(session, server_name: str) -> List[Dict]:
        """内部工具:从 session 拿 tools"""
        result = await session.list_tools()
        tools = []
        for tool in result.tools:
            tools.append({
                "name": tool.name,
                "description": tool.description or "",
                "inputSchema": tool.inputSchema,
                "server": server_name,
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
        # v2.8+:支持所有传输类型
        if srv.transport not in ("stdio", "streamable_http", "http", "sse"):
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
        """异步调用 MCP 工具(支持 stdio / streamable_http / sse)"""
        if srv.transport == "stdio":
            params = self._server_to_params(srv)
            if params is None:
                return None, f"MCP server [{srv.name}] 缺少启动命令"
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await self._do_call(session, tool_name, arguments)
        elif srv.transport in ("streamable_http", "http"):
            if not _STREAMABLE_HTTP_AVAILABLE:
                return None, "streamable_http 不可用,请升级 mcp SDK (pip install --upgrade mcp)"
            headers = srv.headers or {}
            async with streamablehttp_client(srv.url, headers=headers) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await self._do_call(session, tool_name, arguments)
        elif srv.transport == "sse":
            if not _SSE_AVAILABLE:
                return None, "SSE 不可用,请升级 mcp SDK"
            headers = srv.headers or {}
            async with sse_client(srv.url, headers=headers) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await self._do_call(session, tool_name, arguments)
        return None, f"MCP server [{srv.name}] 传输类型 '{srv.transport}' 不支持"

    @staticmethod
    async def _do_call(session, tool_name: str, arguments: Dict) -> Any:
        """内部:实际调用 tool"""
        result = await session.call_tool(tool_name, arguments=arguments or {})
        texts = []
        for content in result.content:
            if isinstance(content, TextContent):
                texts.append(content.text)
            else:
                texts.append(str(content))
        return "\n".join(texts), None

    # ==================== v2.8+:Resources 支持 ====================

    async def _list_resources_async(self, srv: MCPServer) -> List[Dict]:
        """异步获取某服务器的资源列表"""
        if srv.transport == "stdio":
            params = self._server_to_params(srv)
            if params is None:
                return []
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await self._do_list_resources(session, srv.name)
        elif srv.transport in ("streamable_http", "http"):
            if not _STREAMABLE_HTTP_AVAILABLE:
                return [{"uri": "_error", "name": f"{srv.name}_error",
                         "description": "streamable_http 不可用",
                         "server": srv.name, "_error": True}]
            headers = srv.headers or {}
            async with streamablehttp_client(srv.url, headers=headers) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await self._do_list_resources(session, srv.name)
        elif srv.transport == "sse":
            if not _SSE_AVAILABLE:
                return [{"uri": "_error", "name": f"{srv.name}_error",
                         "description": "SSE 不可用",
                         "server": srv.name, "_error": True}]
            headers = srv.headers or {}
            async with sse_client(srv.url, headers=headers) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await self._do_list_resources(session, srv.name)
        return []

    @staticmethod
    async def _do_list_resources(session, server_name: str) -> List[Dict]:
        """内部:从 session 拿 resources"""
        try:
            result = await session.list_resources()
        except Exception as e:
            return [{"uri": "_error", "name": "_error",
                     "description": f"list_resources 失败: {e}",
                     "server": server_name, "_error": True}]
        resources = []
        for r in result.resources:
            resources.append({
                "uri": getattr(r, "uri", ""),
                "name": getattr(r, "name", ""),
                "description": getattr(r, "description", ""),
                "mimeType": getattr(r, "mimeType", ""),
                "server": server_name,
            })
        return resources

    def list_resources(self, server_name: str) -> List[Dict]:
        """同步列出某服务器的资源"""
        if not _MCP_AVAILABLE:
            return []
        if server_name not in self.servers:
            return []
        srv = self.servers[server_name]
        if not srv.enabled:
            return []
        if srv.transport not in ("stdio", "streamable_http", "http", "sse"):
            return []
        try:
            import asyncio
            return asyncio.run(self._list_resources_async(srv))
        except Exception as e:
            return [{"uri": "_error", "name": f"{server_name}_error",
                     "description": f"获取资源失败: {e}",
                     "server": server_name, "_error": True}]

    def list_all_resources(self) -> List[Dict]:
        """列出所有已启用服务器的资源"""
        all_resources = []
        for name in self.servers:
            all_resources.extend(self.list_resources(name))
        return all_resources

    async def _read_resource_async(self, srv: MCPServer, uri: str) -> Any:
        """异步读取资源"""
        session_cm = None
        if srv.transport == "stdio":
            params = self._server_to_params(srv)
            if params is None:
                return None, f"MCP server [{srv.name}] 缺少启动命令"
            session_cm = stdio_client(params)
        elif srv.transport in ("streamable_http", "http"):
            if not _STREAMABLE_HTTP_AVAILABLE:
                return None, "streamable_http 不可用"
            headers = srv.headers or {}
            session_cm = streamablehttp_client(srv.url, headers=headers)
        elif srv.transport == "sse":
            if not _SSE_AVAILABLE:
                return None, "SSE 不可用"
            headers = srv.headers or {}
            session_cm = sse_client(srv.url, headers=headers)
        else:
            return None, f"MCP server [{srv.name}] 传输类型 '{srv.transport}' 不支持"

        async with session_cm as conn_args:
            if srv.transport == "stdio":
                read, write = conn_args
            elif srv.transport in ("streamable_http", "http"):
                read, write, _ = conn_args
            else:  # sse
                read, write = conn_args

            async with ClientSession(read, write) as session:
                await session.initialize()
                try:
                    result = await session.read_resource(uri)
                except Exception as e:
                    return None, f"read_resource({uri}) 失败: {e}"
                # 提取文本内容
                texts = []
                for content in result.contents:
                    if hasattr(content, "text") and content.text:
                        texts.append(content.text)
                    elif hasattr(content, "blob"):
                        texts.append(f"[blob: {len(content.blob)} bytes]")
                    else:
                        texts.append(str(content))
                return "\n".join(texts), None

    def read_resource_sync(self, server_name: str, uri: str) -> Any:
        """同步读取资源"""
        if not _MCP_AVAILABLE:
            return None, "MCP SDK 未安装"
        if server_name not in self.servers:
            return None, f"Unknown MCP server: {server_name}"
        srv = self.servers[server_name]
        if not srv.enabled:
            return None, f"MCP server [{server_name}] 已禁用"
        if srv.transport not in ("stdio", "streamable_http", "http", "sse"):
            return None, f"MCP server [{server_name}] 传输类型不支持"
        try:
            import asyncio
            return asyncio.run(self._read_resource_async(srv, uri))
        except Exception as e:
            return None, f"MCP read_resource 失败: {e}"

    # ==================== v2.8+:Prompts 支持 ====================

    async def _list_prompts_async(self, srv: MCPServer) -> List[Dict]:
        """异步获取某服务器的 prompts 列表"""
        if srv.transport == "stdio":
            params = self._server_to_params(srv)
            if params is None:
                return []
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await self._do_list_prompts(session, srv.name)
        elif srv.transport in ("streamable_http", "http"):
            if not _STREAMABLE_HTTP_AVAILABLE:
                return [{"name": f"{srv.name}_error",
                         "description": "streamable_http 不可用",
                         "server": srv.name, "_error": True}]
            headers = srv.headers or {}
            async with streamablehttp_client(srv.url, headers=headers) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await self._do_list_prompts(session, srv.name)
        elif srv.transport == "sse":
            if not _SSE_AVAILABLE:
                return [{"name": f"{srv.name}_error",
                         "description": "SSE 不可用",
                         "server": srv.name, "_error": True}]
            headers = srv.headers or {}
            async with sse_client(srv.url, headers=headers) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await self._do_list_prompts(session, srv.name)
        return []

    @staticmethod
    async def _do_list_prompts(session, server_name: str) -> List[Dict]:
        """内部:从 session 拿 prompts"""
        try:
            result = await session.list_prompts()
        except Exception as e:
            return [{"name": "_error",
                     "description": f"list_prompts 失败: {e}",
                     "server": server_name, "_error": True}]
        prompts = []
        for p in result.prompts:
            prompts.append({
                "name": getattr(p, "name", ""),
                "description": getattr(p, "description", ""),
                "arguments": [
                    {
                        "name": getattr(a, "name", ""),
                        "description": getattr(a, "description", ""),
                        "required": getattr(a, "required", False),
                    }
                    for a in (getattr(p, "arguments", []) or [])
                ],
                "server": server_name,
            })
        return prompts

    def list_prompts(self, server_name: str) -> List[Dict]:
        """同步列出某服务器的 prompts"""
        if not _MCP_AVAILABLE:
            return []
        if server_name not in self.servers:
            return []
        srv = self.servers[server_name]
        if not srv.enabled:
            return []
        if srv.transport not in ("stdio", "streamable_http", "http", "sse"):
            return []
        try:
            import asyncio
            return asyncio.run(self._list_prompts_async(srv))
        except Exception as e:
            return [{"name": f"{server_name}_error",
                     "description": f"获取 prompts 失败: {e}",
                     "server": server_name, "_error": True}]

    def list_all_prompts(self) -> List[Dict]:
        """列出所有已启用服务器的 prompts"""
        all_prompts = []
        for name in self.servers:
            all_prompts.extend(self.list_prompts(name))
        return all_prompts

    async def _get_prompt_async(self, srv: MCPServer, name: str,
                                 arguments: Optional[Dict] = None) -> Any:
        """异步获取 prompt"""
        session_cm = None
        if srv.transport == "stdio":
            params = self._server_to_params(srv)
            if params is None:
                return None, f"MCP server [{srv.name}] 缺少启动命令"
            session_cm = stdio_client(params)
        elif srv.transport in ("streamable_http", "http"):
            if not _STREAMABLE_HTTP_AVAILABLE:
                return None, "streamable_http 不可用"
            headers = srv.headers or {}
            session_cm = streamablehttp_client(srv.url, headers=headers)
        elif srv.transport == "sse":
            if not _SSE_AVAILABLE:
                return None, "SSE 不可用"
            headers = srv.headers or {}
            session_cm = sse_client(srv.url, headers=headers)
        else:
            return None, f"MCP server [{srv.name}] 传输类型不支持"

        async with session_cm as conn_args:
            if srv.transport == "stdio":
                read, write = conn_args
            elif srv.transport in ("streamable_http", "http"):
                read, write, _ = conn_args
            else:  # sse
                read, write = conn_args

            async with ClientSession(read, write) as session:
                await session.initialize()
                try:
                    result = await session.get_prompt(name, arguments=arguments or {})
                except Exception as e:
                    return None, f"get_prompt({name}) 失败: {e}"
                # 提取 messages
                messages = []
                for msg in result.messages:
                    messages.append({
                        "role": getattr(msg, "role", ""),
                        "content": getattr(msg, "content", ""),
                    })
                return {
                    "description": getattr(result, "description", ""),
                    "messages": messages,
                }, None

    def get_prompt_sync(self, server_name: str, name: str,
                        arguments: Optional[Dict] = None) -> Any:
        """同步获取 prompt 内容"""
        if not _MCP_AVAILABLE:
            return None, "MCP SDK 未安装"
        if server_name not in self.servers:
            return None, f"Unknown MCP server: {server_name}"
        srv = self.servers[server_name]
        if not srv.enabled:
            return None, f"MCP server [{server_name}] 已禁用"
        if srv.transport not in ("stdio", "streamable_http", "http", "sse"):
            return None, f"MCP server [{server_name}] 传输类型不支持"
        try:
            import asyncio
            return asyncio.run(self._get_prompt_async(srv, name, arguments))
        except Exception as e:
            return None, f"MCP get_prompt 失败: {e}"

    def call_tool_sync(self, server_name: str, tool_name: str, arguments: Dict) -> Any:
        """同步调用 MCP 工具"""
        if not _MCP_AVAILABLE:
            return None, "MCP SDK 未安装，请执行: pip install mcp"
        if server_name not in self.servers:
            return None, f"Unknown MCP server: {server_name}"
        srv = self.servers[server_name]
        if not srv.enabled:
            return None, f"MCP server [{server_name}] 已禁用"
        # v2.8+:支持 stdio / streamable_http / http / sse
        if srv.transport not in ("stdio", "streamable_http", "http", "sse"):
            return None, f"MCP server [{server_name}] 传输类型 '{srv.transport}' 不支持"
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
