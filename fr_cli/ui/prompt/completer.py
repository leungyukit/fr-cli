"""
TUI 自动补全器 —— / 命令分类补全 + @ Agent 补全

补全逻辑（按 prompt_toolkit Completer 协议 yield Completion）：
- 输入 / 时：分类补全所有命令，带描述与示例
- 输入 @ 时：补全所有 Agent（本地 + 内置）
- 其他文本：不补全
"""
import re
from typing import Callable, List, Tuple

try:
    from prompt_toolkit.completion import Completer, Completion
    HAS_PT = True
except ImportError:
    HAS_PT = False
    Completer = object  # 占位，避免继承失败


class FanRenCompleter(Completer if HAS_PT else object):
    """TUI 自动补全器：

    - 输入 / 时补全所有命令（按分类分组，带描述）
    - 输入 @ 时补全所有 Agent（本地 + 内置）
    - 任意文本时不补全

    多列分类展示：命令按 [文件] [会话] [模型] [Agent] [网络] [工具] 分组
    """

    # 命令分类映射（按工具名前缀/类型分）
    CATEGORY_HINTS = {
        # 会话（必须放前面，因为 delete_session 也含 'delete' 会被错误归类到文件）
        "list_sessions": "会话", "delete_session": "会话",
        "session_list": "会话", "session_load": "会话", "session_del": "会话",
        "save": "会话", "load": "会话", "del": "会话", "export": "会话",
        "undo": "会话", "new": "会话",
        # 文件/工作区
        "cat": "文件", "write": "文件",
        "append": "文件", "delete": "文件",
        "rename": "文件", "replace": "文件", "grep": "文件",
        "ls": "文件", "cd": "文件",
        "dir": "文件", "dirs": "文件", "rmdir": "文件",
        "read_excel": "文件", "read_csv": "文件", "open": "文件",
        "generate_chart": "图表", "chart": "图表",
        # 模型/配置
        "model": "模型",
        "key": "配置",
        "limit": "模型",
        "lang": "配置",
        "alias": "配置",
        "providers": "模型", "mode": "思维", "debug": "配置",
        # 网络/远程
        "web": "网络", "fetch": "网络",
        "ping": "网络", "port_scan": "网络", "ip_scan": "网络", "network_devices": "网络",
        "ssh": "远程", "scp": "远程",
        "see": "多模态", "generate_image": "多模态",
        "ocr_recognize": "多模态", "ocr_config": "多模态",
        "stock_config": "量化",
        "build_cmd": "构建", "dynamic_build": "构建",
        # 邮件/网盘
        "mail_": "邮件", "m365_": "邮件", "disk_": "网盘",
        # 定时/守护
        "cron_": "定时", "agent_cron_": "定时", "agent_server": "守护",
        "gatekeeper": "守护", "hermes": "守护",
        "autostart": "守护", "status": "系统",
        # Agent/蜂群
        "agent_": "Agent", "remote_agent_": "Agent", "remote_setup": "Agent",
        "db_setup": "Agent",
        "swarm": "Agent", "swarm_run": "Agent",
        # RAG/MCP
        "rag_": "RAG", "mcp_": "MCP", "mcp_call": "MCP", "mcp_list": "MCP",
        # 启动/退出
        "exit": "退出", "quit": "退出", "help": "帮助", "shell": "Shell",
        "update": "更新", "apps": "启动", "launch": "启动",
        "master": "Master", "skills": "插件", "list_plugins": "插件",
        # 快捷场景（高 ROI）
        "commit": "快捷", "pr": "快捷", "review": "快捷",
        "daily": "快捷", "init_project": "项目", "pref": "偏好",
        "voice": "语音", "screenshot": "截屏", "drag": "拖文件", "ide": "IDE",
        "why": "帮助",
    }

    # 命令使用样例（供补全列表与帮助展示）
    COMMAND_EXAMPLES = {
        # 模型/配置
        "model": "/model 3 或 /model deepseek:deepseek-chat",
        "model config": "/model config",
        "key": "/key sk-xxx",
        "limit": "/limit 4096",
        "lang": "/lang en",
        "alias": "/alias mycmd /cat README.md",
        "providers": "/providers",
        "mode": "/mode plan",
        "debug": "/debug",
        "local_llm": "/local_llm",
        # 文件
        "cat": "/cat README.md",
        "write": '/write a.md "内容"',
        "append": '/append a.md "追加"',
        "delete": "/delete tmp.txt",
        "ls": "/ls",
        "cd": "/cd src",
        "open": "/open README.md",
        "read_excel": "/read_excel data.xlsx",
        "read_csv": "/read_csv data.csv",
        "generate_chart": '/chart bar --labels A,B,C --values 10,20,30 --title 销售',
        "dir": "/dir /path/to/dir",
        "dirs": "/dirs",
        "rmdir": "/rmdir old_dir",
        "rename_file": "/rename old.txt new.txt",
        "replace_text": '/replace file.txt "old" "new"',
        "grep_text": '/grep file.txt "pattern"',
        # 会话
        "save": "/save proj_v1",
        "load": "/load proj_v1",
        "del": "/del proj_v1",
        "delete_session": "/session del 2",
        "list_sessions": "/session list",
        "session_list": "/session list",
        "session_load": "/session load 2",
        "session_del": "/session del 2",
        "undo": "/undo 2",
        "export": "/export",
        "recent": "/recent",
        "new": "/new",
        # 网络/多模态
        "web": "/web Python 异步",
        "fetch": "/fetch https://example.com",
        "ping_host": "/ping example.com",
        "port_scan": "/port_scan 192.168.1.1 22,80,443",
        "ip_scan": "/ip_scan 192.168.1.0/24",
        "network_devices": "/network_devices 192.168.1.0/24",
        "ssh_command": '/ssh myhost user "uname -a"',
        "scp_transfer": "/scp up local.txt /remote.txt myhost user",
        "see": "/see photo.jpg",
        "generate_image": '/generate_image "一只猫"',
        "ocr_recognize": "/ocr screenshot.png",
        "ocr_config": "/ocr_config setup",
        "stock_config": "/stock_config setup",
        "build_cmd": "/build 生成二维码识别工具",
        # 邮件
        "mail_setup": "/mail setup",
        "mail_inbox": "/mail inbox",
        "mail_read": "/mail read 1",
        "mail_send": '/mail send a@b.com "主题" "正文"',
        "m365_config": "/m365_config setup",
        "m365_inbox": "/m365_inbox",
        "m365_read": "/m365_read <message_id>",
        "m365_send": '/m365_send a@b.com "主题" "正文"',
        "m365_status": "/m365_status",
        "m365_logout": "/m365_logout",
        # 网盘
        "disk_setup": "/disk setup",
        "disk_ls": "/disk ls",
        "disk_cd": "/disk cd /",
        "disk_up": "/disk up local.txt /remote.txt",
        "disk_down": "/disk down /remote.txt local.txt",
        # 定时
        "cron_add": '/cron add "/ls" 60',
        "cron_list": "/cron list",
        "cron_del": "/cron del 1",
        # Agent
        "agent_create": "/agent create coder",
        "swarm_run": "/swarm parallel agent1,agent2 任务描述",
        "agent_list": "/agent list",
        "agent_delete": "/agent delete coder",
        "agent_show": "/agent show coder",
        "agent_edit": "/agent edit coder",
        "agent_forge": "/agent forge",
        "agent_run": "/agent run coder",
        "agent_model": "/agent_model coder deepseek:deepseek-chat",
        "agent_server": "/agent_server start 8080",
        "agent_publish": "/agent_publish coder",
        "agent_call": "/agent_call my_agent 输入内容",
        "agent_cron_add": '/agent cron add "/ls" 60',
        "agent_cron_list": "/agent cron list",
        "agent_cron_del": "/agent cron del 1",
        "remote_setup": "/remote setup",
        "remote_agent_add": "/remote agent add myserver",
        "remote_agent_list": "/remote agent list",
        "remote_agent_del": "/remote agent del myserver",
        "remote_agent_scan": "/remote agent scan",
        "remote_agent_import": "/remote agent import myserver",
        "db_setup": "/db setup",
        "master": "/master on",
        # RAG/MCP
        "rag_dir": "/rag_dir ./docs",
        "rag_sync": "/rag sync",
        "rag_watch": "/rag watch start",
        "mcp_list": "/mcp list",
        "mcp_call": '/mcp_call fs read_file {"path": "/tmp/a.txt"}',
        "mcp_add": "/mcp add",
        "mcp_del": "/mcp del fs",
        "mcp_enable": "/mcp enable fs",
        "mcp_disable": "/mcp disable fs",
        "mcp_refresh": "/mcp refresh",
        # 系统/快捷
        "exit": "/exit",
        "shell": "/shell",
        "update_check": "/update check",
        "update_run": "/update run",
        "launch": "/launch chrome",
        "apps": "/apps",
        "gatekeeper": "/gatekeeper",
        "hermes": "/hermes",
        "autostart": "/autostart",
        "status": "/status",
        "queue": "/queue",
        "tutorial": "/tutorial",
        "commit": "/commit",
        "pr": "/pr",
        "review": "/review",
        "daily": "/daily",
        "init_project": "/init_project",
        "pref": "/pref",
        "voice": "/voice",
        "screenshot": "/screenshot",
        "drag": "/drag",
        "ide": "/ide",
        "why": "/why",
        "cache": "/cache",
        "help": "/help agent",
        "list_plugins": "/list_plugins",
    }

    # Namespace 子命令补全映射
    NAMESPACE_SUBCOMMANDS = {
        "agent": ["create", "list", "delete", "show", "edit", "forge", "run", "model", "server", "publish"],
        "session": ["list", "load", "delete"],
        "rag": ["dir", "sync", "watch"],
        "mcp": ["list", "add", "delete", "enable", "disable", "refresh"],
        "mail": ["setup", "inbox", "read", "send"],
        "disk": ["setup", "ls", "cd", "up", "down"],
        "cron": ["add", "list", "delete"],
        "db": ["setup"],
        "data": ["excel", "csv"],
        "remote": ["setup"],
        "ocr": ["config"],
        "stock": ["config"],
    }

    TWO_LEVEL_NAMESPACES = {
        "agent cron": ["add", "list", "delete"],
        "remote agent": ["add", "list", "delete", "scan", "import"],
    }

    def __init__(self, get_commands: Callable, get_agents: Callable):
        self.get_commands = get_commands
        self.get_agents = get_agents

    def _categorize(self, cmd: str) -> str:
        """给命令分类"""
        for prefix, cat in self.CATEGORY_HINTS.items():
            if cmd == prefix or cmd.startswith(prefix):
                return cat
        return "其他"

    def get_completions(self, document, complete_event):
        if not HAS_PT:
            return
        text = document.text_before_cursor
        # / 命令补全（按分类）
        if text.startswith("/"):
            yield from self._complete_commands(text[1:])
        # @ Agent 补全
        elif text.startswith("@"):
            yield from self._complete_agents(text[1:])

    def _complete_commands(self, stripped: str):
        """处理 / 命令补全"""
        parts = stripped.split()

        # namespace 子命令补全
        if len(parts) >= 1:
            ns = parts[0]
            # 两级 namespace，如 /agent cron add
            if len(parts) >= 2:
                two_level = f"{ns} {parts[1]}"
                if two_level in self.TWO_LEVEL_NAMESPACES:
                    prefix = parts[2] if len(parts) > 2 else ""
                    matched = False
                    for sub in self.TWO_LEVEL_NAMESPACES[two_level]:
                        if sub.startswith(prefix):
                            matched = True
                            yield Completion(
                                sub + " ",
                                start_position=-len(prefix) if prefix else 0,
                                display=sub,
                                display_meta="",
                            )
                    if matched:
                        return
            # 一级 namespace，如 /agent create
            if ns in self.NAMESPACE_SUBCOMMANDS and len(parts) <= 2:
                prefix = parts[1] if len(parts) > 1 else ""
                matched = False
                for sub in self.NAMESPACE_SUBCOMMANDS[ns]:
                    if sub.startswith(prefix):
                        matched = True
                        yield Completion(
                            sub + " ",
                            start_position=-len(prefix) if prefix else 0,
                            display=sub,
                            display_meta="",
                        )
                if matched:
                    return

        word = stripped
        all_cmds = self.get_commands()
        # 正则模糊匹配：优先前缀匹配，其次子串匹配
        matched: List[Tuple[str, str, int]] = []
        if not word:
            for cmd, desc in all_cmds:
                matched.append((cmd, desc, 0))
        else:
            pattern = re.compile(re.escape(word), re.IGNORECASE)
            for cmd, desc in all_cmds:
                if cmd.startswith(word):
                    matched.append((cmd, desc, 1))  # 前缀匹配优先级最高
                elif pattern.search(cmd):
                    matched.append((cmd, desc, 2))  # 子串匹配次之
        # 去重并按优先级排序
        seen = set()
        unique = []
        for cmd, desc, prio in matched:
            if cmd not in seen:
                seen.add(cmd)
                unique.append((cmd, desc, prio))
        matched = sorted(unique, key=lambda x: (x[2], x[0]))
        # 先按分类排
        categorized = {}
        for cmd, desc, _ in matched:
            cat = self._categorize(cmd)
            categorized.setdefault(cat, []).append((cmd, desc))
        # 按分类字母序输出
        for cat in sorted(categorized.keys()):
            for cmd, desc in categorized[cat]:
                short_desc = (desc[:30] + "...") if desc and len(desc) > 30 else (desc or "")
                example = self.COMMAND_EXAMPLES.get(cmd, "")
                ex_display = (example[:35] + "...") if len(example) > 35 else example
                yield Completion(
                    cmd + " ",
                    start_position=-len(word) if word else 0,
                    display=f"{cmd} | {short_desc} | {ex_display}",
                    display_meta="",
                )

    def _complete_agents(self, word: str):
        """处理 @ Agent 补全"""
        for agent_name, desc in self.get_agents():
            if agent_name.startswith(word) or not word:
                short_desc = (desc[:30] + "...") if desc and len(desc) > 30 else (desc or "")
                yield Completion(
                    agent_name + " ",
                    start_position=-len(word) if word else 0,
                    display="@" + agent_name,
                    display_meta=short_desc,
                )
