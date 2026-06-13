"""
蜂群任务统一解析器 —— 万法归一

让 Swarm 不仅可以调用 Agent，还可以调用：
- 内置 Agent（@local / @db / @stock 等）
- 注册表工具（search_web / read_file / ocr_recognize 等）
- 任意 / 命令
- MCP 外部工具
- 自定义插件

任务名称支持显式前缀：
  agent:myagent     自定义/远程 Agent
  @local 或 builtin:local  内置 Agent
  tool:search_web   注册表工具
  cmd:/web 搜索词   命令字符串（/ 开头也可自动识别）
  mcp:fs/read_file {"path":"/tmp/a.txt"}  MCP 工具
  plugin:myplugin   自定义插件

无显式前缀时按以下优先级自动推断：
  Agent（本地/远程）> 内置 Agent > 插件 > 注册表工具 > 命令字符串
"""
import io
import json
import shlex
from contextlib import redirect_stdout, redirect_stderr

from fr_cli.command.registry import get_registry
from fr_cli.agent.client import call_agent


class SwarmTaskResolver:
    """蜂群任务解析与执行器"""

    KIND_AGENT = "agent"
    KIND_BUILTIN = "builtin"
    KIND_TOOL = "tool"
    KIND_CMD = "cmd"
    KIND_MCP = "mcp"
    KIND_PLUGIN = "plugin"

    def __init__(self, state):
        self.state = state
        self._reg = get_registry()

    # ------------------------------------------------------------------
    # 解析
    # ------------------------------------------------------------------
    def resolve(self, name: str):
        """解析任务名称，返回 (kind, target, original)"""
        name = name.strip()
        if not name:
            return self.KIND_CMD, "", name

        # 显式前缀
        if name.startswith("@"):
            return self.KIND_BUILTIN, name[1:].strip(), name
        if name.lower().startswith("builtin:"):
            return self.KIND_BUILTIN, name[8:].strip(), name
        if name.lower().startswith("agent:"):
            return self.KIND_AGENT, name[6:].strip(), name
        if name.lower().startswith("tool:"):
            return self.KIND_TOOL, name[5:].strip(), name
        if name.lower().startswith("cmd:"):
            return self.KIND_CMD, name[4:].strip(), name
        if name.lower().startswith("mcp:"):
            return self.KIND_MCP, name[4:].strip(), name
        if name.lower().startswith("plugin:"):
            return self.KIND_PLUGIN, name[7:].strip(), name

        # 命令字符串：以 / 或 ! 开头
        if name.startswith("/") or name.startswith("!"):
            return self.KIND_CMD, name, name

        # 自动推断
        if self._is_agent(name):
            return self.KIND_AGENT, name, name
        if self._is_builtin(name):
            return self.KIND_BUILTIN, name, name
        if self._is_plugin(name):
            return self.KIND_PLUGIN, name, name
        if self._is_tool(name):
            return self.KIND_TOOL, name, name

        # 兜底：当作命令字符串
        return self.KIND_CMD, name, name

    def _is_agent(self, name: str) -> bool:
        """检查名称是否为本地或远程 Agent"""
        from fr_cli.agent.manager import agent_exists
        from fr_cli.agent.remote import get_remote_agent
        try:
            if agent_exists(name):
                return True
        except Exception:
            pass
        try:
            if get_remote_agent(name):
                return True
        except Exception:
            pass
        return False

    def _is_builtin(self, name: str) -> bool:
        """检查名称是否为内置 Agent"""
        from fr_cli.agent.dispatch import BUILTIN_AGENTS
        return name in BUILTIN_AGENTS

    def _is_plugin(self, name: str) -> bool:
        """检查名称是否为自定义插件"""
        plugins = getattr(self.state, "plugins", {}) or {}
        return name in plugins

    def _is_tool(self, name: str) -> bool:
        """检查名称是否为注册表工具（name 或 alias）"""
        if name in self._reg._tools:
            return True
        alias_name = self._reg._aliases.get(name.lstrip("/"))
        if alias_name and alias_name in self._reg._tools:
            return True
        return False

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------
    def call(self, name: str, user_input: str = ""):
        """
        执行单个蜂群任务。

        Returns:
            (result, error)
        """
        kind, target, original = self.resolve(name)

        if kind == self.KIND_AGENT:
            return call_agent(target, self.state, user_input=user_input)

        if kind == self.KIND_BUILTIN:
            return self._call_builtin(target, user_input)

        if kind == self.KIND_TOOL:
            return self._call_tool(target, user_input)

        if kind == self.KIND_CMD:
            return self._call_cmd(original, user_input)

        if kind == self.KIND_MCP:
            return self._call_mcp(target, user_input)

        if kind == self.KIND_PLUGIN:
            return self._call_plugin(target, user_input)

        return None, f"未知蜂群任务类型: {kind}"

    def _call_builtin(self, name: str, user_input: str):
        """调用内置 Agent，捕获 stdout/stderr 作为结果"""
        from fr_cli.agent.client import call_builtin_agent
        return call_builtin_agent(name, user_input, self.state)

    def _call_tool(self, tool_name: str, user_input: str):
        """调用注册表工具，自动将 user_input 映射到合适参数"""
        real_name = self._reg._aliases.get(tool_name.lstrip("/")) or tool_name
        tool = self._reg._tools.get(real_name)
        if not tool:
            return None, f"未找到工具: {tool_name}"

        params = tool.get("params", {})
        kwargs = self._build_tool_kwargs(params, user_input)

        deps = self._build_deps()
        try:
            result, error = self._reg.dispatch(deps, real_name, skip_security=False, **kwargs)
            return result, error
        except Exception as e:
            return None, f"工具调用失败: {e}"

    def _build_tool_kwargs(self, params: dict, user_input: str) -> dict:
        """启发式将 user_input 映射为工具参数"""
        kwargs = {}
        param_names = list(params.keys())

        # 常见语义映射
        if "query" in params:
            kwargs["query"] = user_input
        elif "path" in params:
            kwargs["path"] = user_input
        elif "url" in params:
            kwargs["url"] = user_input
        elif "prompt" in params:
            kwargs["prompt"] = user_input
        elif "command" in params:
            kwargs["command"] = user_input
        elif "to" in params and "subject" in params:
            # 邮件：简单按空格分主题/正文
            parts = user_input.split(None, 1)
            kwargs["to"] = parts[0] if parts else ""
            kwargs["subject"] = parts[1] if len(parts) > 1 else ""
        elif param_names:
            # 第一个参数接收 user_input
            kwargs[param_names[0]] = user_input

        # 为剩余必填参数补默认值
        for param, ptype in params.items():
            if param not in kwargs:
                if ptype is str:
                    kwargs[param] = ""
                elif ptype is int:
                    kwargs[param] = 0
                elif ptype is list:
                    kwargs[param] = []
                elif ptype is bool:
                    kwargs[param] = False
                else:
                    kwargs[param] = ""
        return kwargs

    def _call_cmd(self, cmd: str, user_input: str):
        """执行命令字符串"""
        if not hasattr(self.state, "executor") or not self.state.executor:
            return None, "State 缺少 executor，无法执行命令"

        full_cmd = cmd
        if user_input:
            full_cmd = f"{cmd} {user_input}" if not cmd.endswith(user_input) else cmd
        try:
            result = self.state.executor.execute(full_cmd)
            return result.to_tuple()
        except Exception as e:
            return None, f"命令执行失败: {e}"

    def _call_mcp(self, target: str, user_input: str):
        """调用 MCP 工具。target 格式: server/tool/arguments_json"""
        mcp_manager = getattr(self.state, "mcp", None)
        if not mcp_manager:
            return None, "MCP 管理器未初始化"

        # 解析 target：server/tool/{...} 或 server/tool/args
        parts = target.split("/", 2)
        if len(parts) < 2:
            return None, "MCP 任务格式错误，应为 mcp:server/tool/{arguments}"

        server = parts[0]
        tool = parts[1]
        arguments = {}
        if len(parts) == 3 and parts[2]:
            try:
                arguments = json.loads(parts[2])
            except json.JSONDecodeError:
                # 尝试解析为 key=value 列表
                arguments = {}
                for item in shlex.split(parts[2]):
                    if "=" in item:
                        k, v = item.split("=", 1)
                        arguments[k] = v

        # 若有 user_input，尝试作为 arguments 补充
        if user_input and not arguments:
            try:
                arguments = json.loads(user_input)
            except json.JSONDecodeError:
                if "=" in user_input:
                    for item in shlex.split(user_input):
                        if "=" in item:
                            k, v = item.split("=", 1)
                            arguments[k] = v

        try:
            result = mcp_manager.call_tool(server, tool, arguments)
            return result, None
        except Exception as e:
            return None, f"MCP 调用失败: {e}"

    def _call_plugin(self, plugin_name: str, user_input: str):
        """执行自定义插件"""
        from fr_cli.addon.plugin import exec_plugin
        plugins = getattr(self.state, "plugins", {}) or {}
        if plugin_name not in plugins:
            return None, f"未找到插件: {plugin_name}"

        try:
            # 捕获插件输出
            buf = io.StringIO()
            with redirect_stdout(buf), redirect_stderr(buf):
                exec_plugin(plugin_name, plugins[plugin_name], user_input, getattr(self.state, "lang", "zh"))
            output = buf.getvalue()
            return output or "[插件执行完成，无输出]", None
        except Exception as e:
            return None, f"插件执行失败: {e}"

    def _build_deps(self):
        """构建注册表所需的 deps 命名空间"""
        from types import SimpleNamespace
        return SimpleNamespace(
            vfs=self.state.vfs,
            mail_c=getattr(self.state, "mail_c", None),
            web_c=getattr(self.state, "web_c", None),
            disk_c=getattr(self.state, "disk_c", None),
            plugins=getattr(self.state, "plugins", {}),
            lang=getattr(self.state, "lang", "zh"),
            security=getattr(self.state, "security", None),
            cfg=getattr(self.state, "cfg", {}),
            client=getattr(self.state, "client", None),
            model_name=getattr(self.state, "model_name", None),
            mcp=getattr(self.state, "mcp", None),
        )


def resolve_swarm_task(state, name: str, user_input: str = ""):
    """便捷函数：解析并执行单个蜂群任务"""
    resolver = SwarmTaskResolver(state)
    return resolver.call(name, user_input)
