"""
MCP 工具管理器
参考 kimi-cli 实现的 MCP 支持
"""

import os
import json
import subprocess
import sys
import threading
import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from fr_cli.conf.paths import MCP_SERVERS_FILE


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
            config_path = str(MCP_SERVERS_FILE)
        self.config_path = config_path
        self.servers: Dict[str, MCPServer] = {}
        self._processes: Dict[str, subprocess.Popen] = {}
        self._load()

    def _load(self):
        """加载配置（兼容两套来源：mcp_servers.json + cfg["mcp"]["servers"]）"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    data = json.load(f)
                    for name, cfg in data.items():
                        self.servers[name] = MCPServer(name=name, **cfg)
            except Exception:
                pass

    def sync_from_cfg(self, cfg: dict):
        """从主配置文件 `cfg["mcp"]["servers"]` 同步服务器列表。

        这一步让 ~/.fr_cli/config.json 和 ~/.fr_cli/mcp/servers.json
        至少有一处被读到。两边配置会并集，已存在的不覆盖（避免重置用户已启用的项）。
        """
        mcp_cfg = (cfg or {}).get("mcp") or {}
        servers = mcp_cfg.get("servers") or []
        if not isinstance(servers, list):
            return
        for srv in servers:
            if not isinstance(srv, dict):
                continue
            name = srv.get("name")
            if not name or name in self.servers:
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

    def toggle_server(self, name: str, enabled: bool):
        """启用/禁用服务器，返回 (ok, err) 元组"""
        if name not in self.servers:
            return False, f"Unknown server: {name}"
        self.servers[name].enabled = bool(enabled)
        self._save()
        return True, None

    def quick_add(self, name: str, command: str, args: List[str]):
        """便捷添加：直接用 stdio + command + args，避免命令路径写错。

        对应 CLI 调用 `/mcp_add <name> <cmd> [args...]`。
        """
        return self.add_server(name=name, transport="stdio", command=command, args=args)

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
            # 已启动则先确认进程还活着
            proc = self._processes[name]
            if proc.poll() is None:
                return True
            # 进程已死，清理后重启
            del self._processes[name]

        server = self.servers[name]

        try:
            if server.transport == "stdio" and server.command:
                # start_new_session=True 隔离进程组，避免父进程 SIGINT 影响子进程
                # 不使用 PIPE stdin/stdout（避免缓冲区满阻塞）；stderr 仍捕获以便排错
                popen_kwargs = {
                    "stdin": subprocess.DEVNULL,
                    "stdout": subprocess.DEVNULL,
                    "stderr": subprocess.PIPE,
                }
                if os.name == "posix":
                    popen_kwargs["start_new_session"] = True
                else:
                    # Windows 下用 CREATE_NEW_PROCESS_GROUP
                    popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
                proc = subprocess.Popen(
                    [server.command] + (server.args or []),
                    **popen_kwargs,
                )
                self._processes[name] = proc
                return True

        except Exception as e:
            print(f"启动 MCP 服务器 {name} 失败: {e}")

        return False

    def stop_server(self, name: str):
        """停止 MCP 服务器"""
        if name not in self._processes:
            return
        proc = self._processes[name]
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    try:
                        proc.wait(timeout=2)
                    except Exception:
                        pass
        except Exception as e:
            print(f"停止 MCP 服务器 {name} 时出错: {e}")
        finally:
            # 无论 terminate/kill 成功与否都从字典里移除，避免泄漏
            self._processes.pop(name, None)

    def stop_all(self):
        """停止所有服务器"""
        for name in list(self._processes.keys()):
            self.stop_server(name)

    def __del__(self):
        """析构时尽量清理子进程"""
        try:
            self.stop_all()
        except Exception:
            pass

    def get_tools(self, name: str) -> List[Dict]:
        """获取 MCP 工具列表（基于本地配置 —— 完整协议未实现）

        返回值是从配置派生的占位描述。完整 MCP 协议（stdin/stdout JSON-RPC
        握手 + tools/list 响应）尚未实现，因此这里不能返回 server 真正声明的
        工具集合。如需启用真实协议，需在 start_server 后用 json-rpc 与
        子进程 stdin/stdout 通信。
        """
        if name not in self.servers:
            return []
        # 占位实现：返回一个示例工具，提示用户这是配置派生
        return [
            {
                "name": f"{name}_placeholder",
                "description": f"MCP server '{name}' is registered but the JSON-RPC handshake "
                               f"is not yet implemented. Tools will appear here after the "
                               f"server handshake is added.",
                "inputSchema": {"type": "object", "properties": {}},
                "server": name,
                "_stub": True,
            }
        ]

    def list_all_tools(self) -> List[Dict]:
        """列出所有已注册服务器的工具（占位实现）"""
        all_tools = []
        for name in self.servers:
            all_tools.extend(self.get_tools(name))
        return all_tools

    def get_server_tools_desc(self) -> str:
        """生成所有 MCP 服务器的描述文本（注入到 system prompt）

        格式：
            [MCP server: filesystem]
              transport: stdio
              command: npx
              args: ['-y', '@modelcontextprotocol/server-filesystem', '/tmp']
            [MCP server: github]
              ...
        """
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

    def call_tool_sync(self, server_name: str, tool_name: str, arguments: Dict) -> Any:
        """同步调用 MCP 工具（当前为简化占位实现）

        调用方应当先 list_all_tools() 检查是否有 stub 工具，
        或者根据 get_server_tools_desc() 决定是否要调起真实 MCP server。
        """
        if server_name not in self.servers:
            return None, f"Unknown MCP server: {server_name}"
        srv = self.servers[server_name]
        if not srv.enabled:
            return None, f"MCP server [{server_name}] 已禁用"
        # 当前仅支持 stdio 传输方式的简化调用
        if srv.transport == "stdio" and srv.command:
            try:
                payload = json.dumps({
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": arguments or {}}
                })
                proc = subprocess.Popen(
                    [srv.command] + (srv.args or []),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                stdout, stderr = proc.communicate(input=payload + "\n", timeout=30)
                if stderr:
                    return None, f"MCP server error: {stderr[:500]}"
                try:
                    resp = json.loads(stdout.strip().splitlines()[-1])
                    if "error" in resp:
                        return None, f"MCP tool error: {resp['error']}"
                    return resp.get("result", stdout), None
                except Exception:
                    return stdout, None
            except subprocess.TimeoutExpired:
                return None, "MCP 调用超时（30秒）"
            except Exception as e:
                return None, f"MCP 调用失败: {e}"
        return None, (
            f"MCP server [{server_name}] 传输类型 '{srv.transport}' 暂不支持同步调用。"
            "当前仅支持 stdio 传输。"
        )

    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict) -> Any:
        """异步调用 MCP 工具（当前为未实现）"""
        raise NotImplementedError(
            "MCP JSON-RPC 协议握手尚未实现。请使用 mcp_call 注册的占位工具，"
            "或自行实现 JSON-RPC 与已启动子进程的 stdin/stdout 通信。"
        )

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


# 全局实例（线程安全单例）
_mcp_manager: Optional[MCPServerManager] = None
_mcp_manager_lock = threading.Lock()


def get_mcp_manager() -> MCPServerManager:
    """获取 MCP 管理器（线程安全单例）"""
    global _mcp_manager
    # 双重检查：避免每次调用都加锁
    if _mcp_manager is None:
        with _mcp_manager_lock:
            if _mcp_manager is None:
                _mcp_manager = MCPServerManager()
    return _mcp_manager


def reset_mcp_manager():
    """重置全局单例（仅用于测试或热加载新配置）"""
    global _mcp_manager
    with _mcp_manager_lock:
        if _mcp_manager is not None:
            try:
                _mcp_manager.stop_all()
            except Exception:
                pass
        _mcp_manager = None


def load_from_config_file(config_file: str) -> MCPServerManager:
    """从配置文件加载 MCP 服务器"""
    return MCPServerManager.from_config_file(config_file)

MCPManager = MCPServerManager