"""
MCPServerManagerCoreMixin —— 初始化 + 配置加载/保存

- __init__:初始化 self.cfg + self.servers
- _load:从 cfg["mcp"]["servers"] 或旧文件加载
- _load_from_cfg:从外部 cfg 强制重载
- _save_to_cfg:把 servers 写回 cfg
- _save:持久化(save_config 原子写入)
- from_config_file:从标准 MCP 配置文件加载
"""
from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from fr_cli.conf.config import save_config
from fr_cli.conf.paths import MCP_SERVERS_FILE

from fr_cli.weapon.mcp.models import MCPServer

if TYPE_CHECKING:
    from fr_cli.weapon.mcp.manager import MCPServerManager


class MCPServerManagerCoreMixin:
    """配置加载/保存 mixin"""

    def __init__(self, cfg: dict = None):
        """初始化管理器,cfg 为 ~/.fr_cli/config.json 的内容。

        未传入 cfg 时创建一个空管理器(仅用于一次性从文件加载的场景)。
        """
        self.cfg = cfg or {}
        self.servers = {}
        self._load()

    def _load(self):
        """加载配置:优先从主配置 cfg["mcp"]["servers"] 读取;
        若旧文件 ~/.fr_cli/mcp/servers.json 仍存在,则做一次迁移合并。
        """
        servers_data = []
        # 主配置优先
        mcp_cfg = self.cfg.get("mcp") if self.cfg else None
        if isinstance(mcp_cfg, dict) and "servers" in mcp_cfg:
            servers_data = mcp_cfg["servers"]
        # 旧文件兜底迁移
        elif MCP_SERVERS_FILE.exists():
            try:
                with open(MCP_SERVERS_FILE, "r", encoding="utf-8") as f:
                    legacy = json.load(f)
                if isinstance(legacy, list):
                    servers_data = legacy
            except Exception:
                pass

        for srv_data in servers_data:
            if not isinstance(srv_data, dict):
                continue
            try:
                srv = MCPServer(**srv_data)
                self.servers[srv.name] = srv
            except Exception:
                # 跳过错误项
                continue

    def _load_from_cfg(self, cfg: dict):
        """从外部 cfg 强制重载(主要供 reset_mcp_manager 后从最新 cfg 重建)"""
        self.cfg = cfg or {}
        self.servers = {}
        self._load()

    def _save_to_cfg(self):
        """把当前 servers 同步到 self.cfg["mcp"]["servers"]"""
        if not self.cfg:
            return
        mcp_cfg = self.cfg.setdefault("mcp", {})
        mcp_cfg["servers"] = [srv.to_dict() for srv in self.servers.values()]

    def _save(self):
        """持久化:更新主配置并调用 save_config 原子写入"""
        self._save_to_cfg()
        if self.cfg:
            save_config(self.cfg)

    @staticmethod
    def from_config_file(config_file: str) -> "MCPServerManager":
        """从标准 MCP 配置文件加载"""
        from fr_cli.weapon.mcp.manager import MCPServerManager

        manager = MCPServerManager()

        if os.path.exists(config_file):
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)

                servers = config.get("mcpServers", {})
                for name, cfg in servers.items():
                    if "command" in cfg:
                        manager.add_server(
                            name=name,
                            transport="stdio",
                            command=cfg["command"],
                            args=cfg.get("args", []),
                        )
                    elif "url" in cfg:
                        manager.add_server(
                            name=name,
                            transport="http",
                            url=cfg["url"],
                            headers=cfg.get("headers"),
                        )
            except Exception as e:
                print(f"加载 MCP 配置失败: {e}")

        return manager
