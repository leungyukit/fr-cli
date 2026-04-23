"""
MCP (Model Context Protocol) 法宝接口
连接外部 MCP 服务器，将其工具纳入统一注册表。
支持 stdio 与 sse 两种传输方式。
"""
import asyncio
import json
from typing import Dict, List, Any, Optional

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False


class MCPManager:
    """MCP 法宝管理器 —— 统御外部神通"""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._servers = cfg.get("mcp", {}).get("servers", [])

    def _get_server_cfg(self, name: str) -> Optional[dict]:
        for s in self._servers:
            if s.get("name") == name:
                return s
        return None

    def _save(self):
        """持久化到本命配置"""
        self.cfg["mcp"] = {"servers": self._servers}
        from fr_cli.conf.config import save_config
        save_config(self.cfg)

    # ── 异步核心 ──

    async def _list_tools_async(self, server_cfg: dict) -> List[dict]:
        """异步列出单个服务器的法宝"""
        transport = server_cfg.get("transport", "stdio")
        tools = []

        if transport == "stdio":
            params = StdioServerParameters(
                command=server_cfg["command"],
                args=server_cfg.get("args", []),
                env=server_cfg.get("env") or None,
                cwd=server_cfg.get("cwd") or None,
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    for tool in result.tools:
                        tools.append({
                            "name": tool.name,
                            "description": tool.description or "",
                            "input_schema": tool.inputSchema,
                            "server": server_cfg["name"],
                        })
        elif transport == "sse":
            # SSE 传输待后续扩展
            pass
        return tools

    async def _call_tool_async(self, server_cfg: dict, tool_name: str, arguments: dict) -> Any:
        """异步调用法宝"""
        transport = server_cfg.get("transport", "stdio")

        if transport == "stdio":
            params = StdioServerParameters(
                command=server_cfg["command"],
                args=server_cfg.get("args", []),
                env=server_cfg.get("env") or None,
                cwd=server_cfg.get("cwd") or None,
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments=arguments)
                    return result
        elif transport == "sse":
            raise NotImplementedError("SSE 传输尚未实现")
        return None

    # ── 同步入口 ──

    def list_servers(self) -> List[dict]:
        """列出所有已配置的服务器"""
        return [s.copy() for s in self._servers]

    def _run_with_timeout(self, coro, timeout=10):
        """带超时的异步执行包装"""
        async def wrapper():
            return await asyncio.wait_for(coro, timeout=timeout)
        try:
            return asyncio.run(wrapper())
        except asyncio.TimeoutError:
            raise TimeoutError("MCP 服务器连接超时")

    def list_all_tools(self) -> List[dict]:
        """汇聚所有可用服务器的法宝列表"""
        if not _MCP_AVAILABLE:
            return []
        all_tools = []
        for s in self._servers:
            if not s.get("enabled", True):
                continue
            try:
                tools = self._run_with_timeout(self._list_tools_async(s), timeout=15)
                all_tools.extend(tools)
            except Exception as e:
                # 单个服务器失败不影响其他
                pass
        return all_tools

    def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> tuple:
        """同步入口：调用 MCP 法宝
        返回 (result, error)
        """
        if not _MCP_AVAILABLE:
            return None, "MCP SDK 未安装，请执行: pip install mcp"

        server_cfg = self._get_server_cfg(server_name)
        if not server_cfg:
            return None, f"MCP 服务器未找到: {server_name}"
        if not server_cfg.get("enabled", True):
            return None, f"MCP 服务器已禁用: {server_name}"

        try:
            result = self._run_with_timeout(self._call_tool_async(server_cfg, tool_name, arguments), timeout=60)
            if result is None:
                return None, "MCP 返回空结果"

            if result.isError:
                content = []
                for item in result.content:
                    if hasattr(item, "text"):
                        content.append(item.text)
                    else:
                        content.append(str(item))
                return None, "MCP 工具执行错误:\n" + "\n".join(content)

            content = []
            for item in result.content:
                if hasattr(item, "text"):
                    content.append(item.text)
                else:
                    content.append(str(item))
            return "\n".join(content), None
        except Exception as e:
            return None, f"MCP 调用失败: {e}"

    def add_server(self, name: str, command: str, args: list = None,
                   env: dict = None, transport: str = "stdio", cwd: str = None) -> tuple:
        """添加服务器配置"""
        if self._get_server_cfg(name):
            return False, f"服务器 {name} 已存在"
        self._servers.append({
            "name": name,
            "transport": transport,
            "command": command,
            "args": args or [],
            "env": env or {},
            "cwd": cwd,
            "enabled": True,
        })
        self._save()
        return True, None

    def remove_server(self, name: str) -> tuple:
        """删除服务器配置"""
        for i, s in enumerate(self._servers):
            if s.get("name") == name:
                self._servers.pop(i)
                self._save()
                return True, None
        return False, f"服务器 {name} 未找到"

    def toggle_server(self, name: str, enabled: bool) -> tuple:
        """启用/禁用服务器"""
        s = self._get_server_cfg(name)
        if not s:
            return False, f"服务器 {name} 未找到"
        s["enabled"] = enabled
        self._save()
        return True, None

    def get_server_tools_desc(self) -> str:
        """生成所有 MCP 法宝的描述文本，用于注入 system prompt"""
        tools = self.list_all_tools()
        if not tools:
            return ""
        lines = ["\n【外部神通 (MCP)】"]
        for t in tools:
            lines.append(f"  - {t['name']}: {t['description']}")
            lines.append(f"    所属服务器: {t['server']}")
            schema = t.get("input_schema", {})
            if schema and schema.get("properties"):
                lines.append(f"    参数: {json.dumps(schema['properties'], ensure_ascii=False)}")
        return "\n".join(lines)
