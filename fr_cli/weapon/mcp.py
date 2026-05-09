"""
MCP 工具管理器
参考 kimi-cli 实现的 MCP 支持
"""

import os
import json
import subprocess
import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict


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
    """MCP 服务器管理器"""

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.expanduser("~/.fr_cli/mcp_servers.json")
        self.config_path = config_path
        self.servers: Dict[str, MCPServer] = {}
        self._processes: Dict[str, subprocess.Popen] = {}
        self._load()

    def _load(self):
        """加载配置"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    data = json.load(f)
                    for name, cfg in data.items():
                        self.servers[name] = MCPServer(name=name, **cfg)
            except Exception:
                pass

    def _save(self):
        """保存配置"""
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        data = {name: srv.to_dict() for name, srv in self.servers.items()}
        with open(self.config_path, 'w') as f:
            json.dump(data, f, indent=2)

    def add_server(self, name: str, transport: str, 
                   command: str = None, args: List[str] = None,
                   url: str = None, headers: Dict = None, auth_type: str = None):
        """添加 MCP 服务器"""
        server = MCPServer(
            name=name,
            transport=transport,
            command=command,
            args=args,
            url=url,
            headers=headers,
            auth_type=auth_type
        )
        self.servers[name] = server
        self._save()
        return server

    def remove_server(self, name: str) -> bool:
        """移除 MCP 服务器"""
        if name in self.servers:
            self.stop_server(name)
            del self.servers[name]
            self._save()
            return True
        return False

    def list_servers(self) -> List[MCPServer]:
        """列出所有服务器"""
        return list(self.servers.values())

    def start_server(self, name: str) -> bool:
        """启动 MCP 服务器"""
        if name not in self.servers:
            return False

        if name in self._processes:
            return True

        server = self.servers[name]
        
        try:
            if server.transport == "stdio" and server.command:
                proc = subprocess.Popen(
                    [server.command] + (server.args or []),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                self._processes[name] = proc
                return True

        except Exception as e:
            print(f"启动 MCP 服务器 {name} 失败: {e}")

        return False

    def stop_server(self, name: str):
        """停止 MCP 服务器"""
        if name in self._processes:
            try:
                self._processes[name].terminate()
                self._processes[name].wait(timeout=5)
            except:
                self._processes[name].kill()
            del self._processes[name]

    def stop_all(self):
        """停止所有服务器"""
        for name in list(self._processes.keys()):
            self.stop_server(name)

    def get_tools(self, name: str) -> List[Dict]:
        """获取 MCP 工具列表"""
        # 这里需要实现 MCP 协议来获取工具
        # 简化版本：返回配置的工具列表
        return []

    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict) -> Any:
        """调用 MCP 工具"""
        # 实现 MCP 协议调用
        pass

    @staticmethod
    def from_config_file(config_file: str) -> 'MCPServerManager':
        """从标准 MCP 配置文件加载"""
        manager = MCPServerManager()
        
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
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


# 全局实例
_mcp_manager = None

def get_mcp_manager() -> MCPServerManager:
    """获取 MCP 管理器"""
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPServerManager()
    return _mcp_manager


def load_from_config_file(config_file: str) -> MCPServerManager:
    """从配置文件加载 MCP 服务器"""
    return MCPServerManager.from_config_file(config_file)

MCPManager = MCPServerManager