"""
统一工具注册表 —— 核心调度器

所有内置命令与 AI 工具通过装饰器注册，实现单一入口、自动安全确认、参数校验。

v2.4.0+：具体工具定义按类目拆分到 fr_cli/command/registered/*.py
本文件只剩：
- ToolRegistry 核心类
- 触发关键词常量
- 共享辅助函数（_ensure_mail / _ensure_disk）
- 全局注册表实例
- 触发所有 registered/*.py 让 @register 装饰器生效
"""
import threading
from typing import List

from fr_cli.core.result import Result
from fr_cli.command.schema import type_name, validate_params

# ---- 触发关键词常量（避免同类工具重复定义）----
_TRIGGERS_FILE = ["文件", "目录", "folder", "读取", "read", "保存到", "save to", "写入文件", "创建文件", "生成文件", "ls", "cat", "cd", "write", "append", "delete"]
_TRIGGERS_WEB = ["搜索", "search", "查一下", "查询", "look up", "最新新闻", "今天天气", "股价", "汇率", "查百度", "查谷歌"]
_TRIGGERS_MAIL = ["邮件", "mail", "email", "发邮件", "收件箱", "inbox", "发送邮件", "查看邮件"]
_TRIGGERS_M365 = ["m365", "microsoft 365", "outlook 365", "微软邮箱", "Office 365"]
_TRIGGERS_CRON = ["定时任务", "定时执行", "周期性执行", "cron job", "scheduled task", "定时器"]
_TRIGGERS_DISK = ["云盘", "上传文件", "下载文件", "cloud disk", "upload file", "download file", "云端"]
_TRIGGERS_SESSION = ["保存会话", "加载会话", "导出会话", "save session", "load session", "export session"]
_TRIGGERS_CONFIG = ["切换模型", "换模型", "改模型", "set model", "api key", "api密钥", "切换语言", "设置上限"]


class ToolRegistry:
    """工具注册表 —— 单一真相源"""

    def __init__(self):
        # 动态构建工具会在运行时注册(动态构建/动态工具管理器)，
        # 与并发 dispatch 存在竞态 —— 用可重入锁保护 _tools / _aliases。
        self._lock = threading.RLock()
        self._tools = {}      # name -> tool_info
        self._aliases = {}    # alias(without /) -> name

    def register(self, name, description="", params=None, security=None, aliases=None, needs_msgs=False, triggers=None):
        """装饰器：注册一个工具/命令"""
        def decorator(func):
            with self._lock:
                self._tools[name] = {
                    "name": name,
                    "description": description,
                    "params": params or {},
                    "security": security,
                    "aliases": aliases or [],
                    "needs_msgs": needs_msgs,
                    "triggers": triggers or [],
                    "handler": func,
                }
                for alias in (aliases or []):
                    key = alias.lstrip("/")
                    self._aliases[key] = name
            return func
        return decorator

    @staticmethod
    def _normalize(value):
        """将 handler 返回的 Result 或 (data, error) 元组统一为 Result。"""
        if isinstance(value, Result):
            return value
        if isinstance(value, tuple) and len(value) == 2:
            return Result.from_tuple(value[0], value[1])
        return Result.ok(value)

    def _permission_decision(self, deps, tool_name, kwargs):
        """查询 tool 级权限决策（config.permissions）。

        Returns:
            "allow" / "deny" / "ask" / "fallthrough"
            - allow: always_allow 或 path_rules 命中 —— 免确认直接执行
            - deny: always_deny 或 path_rules 拒绝 —— 直接拒绝
            - ask: ask_each_time —— 强制走确认流程
            - fallthrough: 未命中 tool 级规则 —— 走正常 sec_* 流程
        """
        security = getattr(deps, "security", None)
        if security is None:
            return "fallthrough"

        # 优先使用四态决策（能区分 ask 与 fallthrough）
        raw = getattr(security, "permission_decision", None)
        if callable(raw):
            try:
                return raw(tool_name, kwargs) or "fallthrough"
            except Exception:
                return "fallthrough"

        # 兼容只提供三态接口（True/False/None）的实现
        checker = getattr(security, "check_tool_permission", None)
        if callable(checker):
            try:
                decision = checker(tool_name, kwargs)
            except Exception:
                return "fallthrough"
            if decision is True:
                return "allow"
            if decision is False:
                return "deny"
        return "fallthrough"

    def _check_security(self, deps, security_key, target, tool_name="", args=None):
        if not security_key:
            return True
        security = getattr(deps, "security", None)
        if security is None:
            return True  # 测试/非交互环境中无 security 时放行，由调用方保障安全
        try:
            return bool(security.check(security_key, target, tool_name=tool_name, args=args))
        except TypeError:
            # 兼容旧签名 check(k, d)
            return bool(security.check(security_key, target))

    def dispatch(self, deps, tool_name, msgs=None, skip_security=False, **kwargs):
        """结构化调用：tool_name + kwargs，返回 Result。"""
        with self._lock:
            tool = self._tools.get(tool_name)
        if not tool:
            return Result.fail(f"Unknown tool: {tool_name}")

        # 参数校验（存在性 + 类型；strict_containers=False 兼容历史 /cmd 通道）
        param_error = validate_params(tool, kwargs, strict_containers=False)
        if param_error:
            return Result.fail(param_error)

        # ---- per-tool 权限层（config.permissions）----
        decision = self._permission_decision(deps, tool_name, kwargs)
        if decision == "deny":
            return Result.fail("Denied")

        # 安全确认（仅当未显式跳过且声明了安全级别时）
        if not skip_security:
            target = kwargs.get("path", tool_name)
            if decision == "allow":
                # always_allow / path_rules 命中 —— 免确认
                pass
            elif decision == "ask":
                # ask_each_time —— 强制确认（无 sec_* 类别时用 sec_write 兜底）
                key = tool["security"] or "sec_write"
                if not self._check_security(deps, key, target, tool_name, kwargs):
                    return Result.fail("Denied")
            elif tool["security"]:
                if not self._check_security(deps, tool["security"], target, tool_name, kwargs):
                    return Result.fail("Denied")

        try:
            if tool["needs_msgs"]:
                raw = tool["handler"](deps, msgs=msgs, **kwargs)
            else:
                raw = tool["handler"](deps, **kwargs)
            return self._normalize(raw)
        except Exception as e:
            # v2.8.7(P2-6)：保留异常类型，别只留 str(e) ——
            # 错误账本此前只能靠事后字符串匹配来分类，等于没有分类。
            return Result.fail(f"Error: {e}", error_type=type(e).__name__)

    def _dispatch_cmd_parts(self, deps, parts, msgs=None, skip_security=False):
        """内部：根据已分词的 parts 调度命令（复用逻辑，避免重复 split），返回 Result。

        Args:
            skip_security: 透传给 dispatch()。v2.4.4 行为变更：AI 通过【命令：...】触发
                时也走 sec_* 确认（除非显式 skip）。用户主动 /cmd 走 sec_* 确认。
        """
        if not parts:
            return Result.fail("Empty command")

        cmd = parts[0].lstrip("/")
        with self._lock:
            tool_name = self._aliases.get(cmd, cmd)
            tool = self._tools.get(tool_name)

        if not tool:
            return Result.fail(f"Unknown command: {cmd}")

        kwargs = self._parse_cmd_args(parts, tool, deps)
        if isinstance(kwargs, Result) and kwargs.is_fail():
            return kwargs
        if isinstance(kwargs, tuple) and len(kwargs) == 2 and kwargs[0] is None:
            return Result.from_tuple(kwargs[0], kwargs[1])
        return self.dispatch(deps, tool_name, msgs=msgs, skip_security=skip_security, **kwargs)

    def dispatch_cmd(self, deps, cmd_str, msgs=None, skip_security=False):
        """命令字符串调用：/cmd args

        Args:
            skip_security: 透传给 dispatch()。默认 False——REPL 用户主动输入 /cmd
                也会走 sec_* 确认。
        """
        parts = cmd_str.strip().split()
        return self._dispatch_cmd_parts(deps, parts, msgs=msgs, skip_security=skip_security)

    def _parse_cmd_args(self, parts, tool, deps):
        """将命令行参数解析为 kwargs(委托给 fr_cli.command.cmd_parser)"""
        from fr_cli.command.cmd_parser import parse_cmd_args
        return parse_cmd_args(parts, tool, deps)

    def get_tools(self):
        with self._lock:
            return list(self._tools.values())

    def unregister_prefix(self, prefix: str, exclude=None) -> List[str]:
        """注销所有以 prefix 开头的工具(返回被移除的工具名列表)。

        用于动态注册的场景(如 MCP 工具):重新注册前先清理旧条目,
        避免每次刷新都累积一份重复工具。

        Args:
            prefix: 工具名前缀(如 "mcp_")
            exclude: 需要保留的工具名集合(可选)—— 例如静态注册、
                与动态注册同前缀但不应被清理的工具

        Returns:
            被移除的工具名列表
        """
        if not prefix:
            return []
        keep = set(exclude or ())
        removed: List[str] = []
        with self._lock:
            for name in list(self._tools.keys()):
                if not name.startswith(prefix) or name in keep:
                    continue
                tool = self._tools.pop(name, None)
                if tool is None:
                    continue
                for alias in tool.get("aliases") or []:
                    self._aliases.pop(alias.lstrip("/"), None)
                removed.append(name)
        return removed

    def get_trigger_map(self):
        """获取工具触发关键词映射"""
        with self._lock:
            return {name: info["triggers"] for name, info in self._tools.items() if info.get("triggers")}

    def get_available_tools(self, plugins):
        """获取 AI 可用的工具列表（含插件），附带参数模式，便于 AI 生成准确的调用标记。"""
        # 先取快照再遍历 —— 避免遍历期间动态注册导致 dict 变更抛 RuntimeError
        with self._lock:
            tools_snapshot = list(self._tools.values())

        tools = []
        for t in tools_snapshot:
            params = t.get("params") or {}
            tools.append({
                "name": t["name"],
                "description": t["description"],
                "commands": [f"/{t['name']}"] + t["aliases"],
                "triggers": t.get("triggers", []),
                "params": {k: type_name(v) for k, v in params.items()},
            })
        for plugin_name in (plugins or {}):
            tools.append({
                "name": f"plugin_{plugin_name}",
                "description": f"自定义插件: {plugin_name}",
                "commands": [f"/{plugin_name}"],
                "triggers": [],
                "params": {"args": "str"},
            })
        return tools


# ------------------------------------------------------------------
# 辅助函数：解析 /chart 命令行参数
# ------------------------------------------------------------------
# ------------------------------------------------------------------
# 全局注册表实例
# ------------------------------------------------------------------
_registry = ToolRegistry()
register = _registry.register


def get_registry():
    return _registry


# ------------------------------------------------------------------
# 触发所有 @register 调用（按类目）
# 顺序不重要，但保持加载顺序稳定便于调试
# ------------------------------------------------------------------
def _bootstrap_registry():
    """扫描 registered/ 目录，触发所有 @register 装饰器"""
    import os
    import importlib

    pkg_dir = os.path.join(os.path.dirname(__file__), "registered")
    if not os.path.isdir(pkg_dir):
        return
    for fname in sorted(os.listdir(pkg_dir)):
        if not fname.endswith(".py") or fname.startswith("_"):
            continue
        mod_name = f"fr_cli.command.registered.{fname[:-3]}"
        importlib.import_module(mod_name)


_bootstrap_registry()
