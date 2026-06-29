"""
MCPServerManagerServersMixin —— 服务器 CRUD

- add_server    注册新 MCP server
- del_server    删除
- enable_server / disable_server  启用/禁用
- list_servers  列表
- get_server    按名获取
"""
from __future__ import annotations

from typing import Dict, List, Optional

from fr_cli.weapon.mcp.models import MCPServer


class MCPServerManagerServersMixin:
    """服务器 CRUD mixin"""

    def add_server(self, name: str, transport: str,
                   command: str = None, args: List[str] = None,
                   url: str = None, headers: Optional[Dict[str, str]] = None,
                   auth_type: Optional[str] = None, enabled: bool = True) -> bool:
        """添加一个 MCP 服务器"""
        if name in self.servers:
            return False
        srv = MCPServer(
            name=name,
            transport=transport,
            command=command,
            args=args,
            url=url,
            headers=headers,
            auth_type=auth_type,
            enabled=enabled,
        )
        self.servers[name] = srv
        self._save()
        return True

    def del_server(self, name: str) -> bool:
        """删除一个 MCP 服务器"""
        if name not in self.servers:
            return False
        del self.servers[name]
        self._save()
        return True

    def enable_server(self, name: str) -> bool:
        if name not in self.servers:
            return False
        self.servers[name].enabled = True
        self._save()
        return True

    def disable_server(self, name: str) -> bool:
        if name not in self.servers:
            return False
        self.servers[name].enabled = False
        self._save()
        return True

    def list_servers(self) -> List[Dict]:
        return [srv.to_dict() for srv in self.servers.values()]

    def get_server(self, name: str) -> Optional[MCPServer]:
        return self.servers.get(name)
