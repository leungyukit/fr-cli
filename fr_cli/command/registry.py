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
from fr_cli.core.result import Result
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
        self._tools = {}      # name -> tool_info
        self._aliases = {}    # alias(without /) -> name

    def register(self, name, description="", params=None, security=None, aliases=None, needs_msgs=False, triggers=None):
        """装饰器：注册一个工具/命令"""
        def decorator(func):
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

    def _check_security(self, deps, security_key, target):
        if not security_key:
            return True
        if deps.security is None:
            return True  # 测试/非交互环境中无 security 时放行，由调用方保障安全
        return deps.security.check(security_key, target)

    def dispatch(self, deps, tool_name, msgs=None, skip_security=False, **kwargs):
        """结构化调用：tool_name + kwargs，返回 Result。"""
        tool = self._tools.get(tool_name)
        if not tool:
            return Result.fail(f"Unknown tool: {tool_name}")

        # 参数校验
        for param, ptype in tool["params"].items():
            if param not in kwargs:
                return Result.fail(f"Missing required parameter: {param}")

        # 安全确认（仅当未显式跳过且声明了安全级别时）
        if not skip_security and tool["security"]:
            target = kwargs.get("path", tool_name)
            if not self._check_security(deps, tool["security"], target):
                return Result.fail("Denied")

        try:
            if tool["needs_msgs"]:
                raw = tool["handler"](deps, msgs=msgs, **kwargs)
            else:
                raw = tool["handler"](deps, **kwargs)
            return self._normalize(raw)
        except Exception as e:
            return Result.fail(f"Error: {e}")

    def _dispatch_cmd_parts(self, deps, parts, msgs=None, skip_security=False):
        """内部：根据已分词的 parts 调度命令（复用逻辑，避免重复 split），返回 Result。

        Args:
            skip_security: 透传给 dispatch()。v2.4.4 行为变更：AI 通过【命令：...】触发
                时也走 sec_* 确认（除非显式 skip）。用户主动 /cmd 走 sec_* 确认。
        """
        if not parts:
            return Result.fail("Empty command")

        cmd = parts[0].lstrip("/")
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
        """将命令行参数解析为 kwargs"""
        arg1 = parts[1] if len(parts) > 1 else ""
        arg2 = parts[2] if len(parts) > 2 else ""
        name = tool["name"]

        # 文件操作
        if name in ("write_file", "append_file"):
            return {"path": arg1, "content": ' '.join(parts[2:]) if len(parts) > 2 else ""}
        if name == "read_file":
            return {"path": arg1}
        if name == "list_files":
            return {}
        if name == "change_dir":
            return {"path": arg1}
        if name == "delete_file":
            return {"path": arg1}

        # 图片 / OCR
        if name == "analyze_image":
            return {"path": arg1, "text": arg2}
        if name == "generate_image":
            return {"prompt": arg1}
        if name == "ocr_recognize":
            return {"path": arg1}

        # 网络
        if name == "search_web":
            return {"query": arg1}
        if name == "fetch_web":
            return {"url": arg1}

        # 邮件
        if name == "mail_inbox":
            return {}
        if name == "mail_read":
            return {"id": arg1}
        if name == "mail_send":
            body = ' '.join(parts[3:]) if len(parts) > 3 else ""
            return {"to": arg1, "subject": arg2, "body": body}
        if name == "mail_setup":
            return {}

        # 定时任务
        if name == "cron_add":
            return {"command": arg2, "interval": int(arg1) if arg1.isdigit() else 0}
        if name == "cron_list":
            return {}
        if name == "cron_del":
            return {"id": arg1}

        # 云盘
        if name == "disk_ls":
            return {}
        if name == "disk_up":
            return {"local": arg1, "remote": arg2}
        if name == "disk_down":
            return {"remote": arg1, "local": arg2}
        if name == "disk_setup":
            return {}

        # 会话
        if name == "save_session":
            return {"name": arg1}
        if name in ("list_sessions", "load_session"):
            return {}
        if name == "export_session":
            return {}
        if name == "delete_session":
            return {}

        # 配置
        if name == "set_model":
            return {"name": arg1}
        if name == "set_key":
            return {"key": arg1}
        if name == "set_limit":
            return {"limit": arg1}
        if name == "set_lang":
            return {"code": arg1}

        # 别名
        if name == "set_alias":
            return {"key": arg1, "value": arg2}

        # 撤销
        if name == "undo":
            return {}

        # 插件列表
        if name == "list_plugins":
            return {}

        # 更新
        if name == "update_check":
            return {}
        if name == "update_run":
            return {}

        # 本地应用启动
        if name == "open_file":
            return {"path": arg1}
        if name == "launch_app":
            return {"name": arg1, "target": ' '.join(parts[2:]) if len(parts) > 2 else None}
        if name == "list_apps":
            return {}

        # Agent 分身
        if name == "agent_create":
            return {"name": arg1, "description": ' '.join(parts[2:]) if len(parts) > 2 else ""}
        if name == "agent_run":
            return {"name": arg1}

        # 文件改名/替换/搜索
        if name == "rename_file":
            return {"old_path": arg1, "new_path": arg2}
        if name == "replace_text":
            return {
                "path": arg1,
                "old_text": arg2,
                "new_text": parts[3] if len(parts) > 3 else "",
                "use_regex": parts[4].lower() in ("true", "1", "yes") if len(parts) > 4 else False,
            }
        if name == "grep_text":
            return {
                "path": arg1,
                "pattern": arg2,
                "use_regex": parts[3].lower() in ("true", "1", "yes") if len(parts) > 3 else False,
            }

        # 网络探测
        if name == "ping_host":
            return {"host": arg1}
        if name == "port_scan":
            return {"host": arg1, "ports": arg2}
        if name == "ip_scan":
            return {"network": arg1}
        if name == "network_devices":
            return {"network": arg1}

        # 远程访问
        if name == "ssh_command":
            return {
                "host": arg1,
                "user": arg2,
                "command": ' '.join(parts[3:]) if len(parts) > 3 else "",
            }
        if name == "scp_transfer":
            return {
                "direction": arg1,
                "local_path": arg2,
                "remote_path": parts[3] if len(parts) > 3 else "",
                "host": parts[4] if len(parts) > 4 else "",
                "user": parts[5] if len(parts) > 5 else "",
            }

        # 图表生成
        if name == "generate_chart":
            return _parse_chart_args(parts)

        # 蜂群协作
        if name == "swarm_run":
            return _parse_swarm_args(parts)

        # 数据文件
        if name == "read_excel":
            return {"path": arg1}
        if name == "read_csv":
            return {"path": arg1}

        return {}

    def get_tools(self):
        return list(self._tools.values())

    def get_trigger_map(self):
        """获取工具触发关键词映射"""
        return {name: info["triggers"] for name, info in self._tools.items() if info.get("triggers")}

    def get_available_tools(self, plugins):
        """获取 AI 可用的工具列表（含插件）"""
        tools = []
        for t in self._tools.values():
            tools.append({
                "name": t["name"],
                "description": t["description"],
                "commands": [f"/{t['name']}"] + t["aliases"],
                "triggers": t.get("triggers", []),
            })
        for plugin_name in (plugins or {}):
            tools.append({
                "name": f"plugin_{plugin_name}",
                "description": f"自定义插件: {plugin_name}",
                "commands": [f"/{plugin_name}"],
                "triggers": [],
            })
        return tools


# ------------------------------------------------------------------
# 辅助函数：解析 /chart 命令行参数
# ------------------------------------------------------------------
def _parse_chart_args(parts):
    """
    解析 /chart bar --labels A,B,C --values 10,20,30 --title 销售
    返回 generate_chart 所需的 kwargs。
    """
    if len(parts) < 2:
        return {"type": "bar", "labels": [], "values": []}

    chart_type = parts[1].lower()
    labels = []
    values = []
    title = None
    width = None
    height = None

    i = 2
    while i < len(parts):
        token = parts[i]
        if token in ("--labels", "-l"):
            i += 1
            if i < len(parts):
                labels = [s.strip() for s in parts[i].split(",") if s.strip()]
        elif token in ("--values", "-v"):
            i += 1
            if i < len(parts):
                values = parts[i].split(",")
        elif token in ("--title", "-t"):
            i += 1
            if i < len(parts):
                title = parts[i]
        elif token in ("--width", "-w"):
            i += 1
            if i < len(parts):
                try:
                    width = int(parts[i])
                except ValueError:
                    pass
        elif token in ("--height", "-h"):
            i += 1
            if i < len(parts):
                try:
                    height = int(parts[i])
                except ValueError:
                    pass
        i += 1

    result = {"type": chart_type, "labels": labels, "values": values}
    if title is not None:
        result["title"] = title
    if width is not None:
        result["width"] = width
    if height is not None:
        result["height"] = height
    return result


def _parse_swarm_args(parts):
    """
    解析 /swarm parallel agent1,agent2,agent3 任务描述
    返回 swarm_run 所需的 kwargs。
    """
    if len(parts) < 3:
        return {"mode": "parallel", "names": [], "user_input": ""}

    mode = parts[1].lower()
    names = [n.strip() for n in parts[2].split(",") if n.strip()]
    user_input = " ".join(parts[3:]) if len(parts) > 3 else ""
    return {"mode": mode, "names": names, "user_input": user_input}


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
