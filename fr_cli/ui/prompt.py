"""
fr-cli TUI 输入面板 —— 基于 prompt_toolkit

参考 OpenClaw / Kimi-cli 风格：
- 多行编辑（Enter 发送、Shift+Enter / Ctrl+J 换行）
- / 命令补全（带描述）
- @ Agent 补全
- 历史回溯（跨 session 持久化）
- 底部状态条（model / token / dir / mode）
- 快捷键：Ctrl+L 清屏、Ctrl+C 清空、Ctrl+D 退出、Esc 取消
- AI 流式输出时 spinner

降级策略：non-TTY（CI / HTTP 服务）自动降级到原 input()
"""
import os
import sys
import threading
from typing import Optional, List, Dict, Callable, Any

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.key_binding import KeyBindings
    # prompt_toolkit 3.x 中 basic 模块不再导出 ctrl_d/ctrl_c/ctrl_l/escape 符号
    # 这些默认行为已内建在 load_basic_bindings() 中，无需手动导入
    from prompt_toolkit.formatted_text import FormattedText, ANSI
    from prompt_toolkit.shortcuts import print_formatted_text
    from prompt_toolkit.styles import Style
    
    HAS_PT = True
except ImportError:
    HAS_PT = False

from fr_cli.conf.paths import ROOT


# ==================== 状态管理 ====================

class StatusState:
    """状态条显示用的实时状态"""
    def __init__(self):
        self.model = ""
        self.provider = ""
        self.directory = ""
        self.session = ""
        self.tokens_used = 0
        self.limit = 0
        self.mode = "direct"
        self.is_busy = False  # AI 正在生成时为 True
        self.is_mock = False  # Mock 模式
        self.spinner_frame = 0
        self.tool_name = ""  # 当前正在调用的工具
        self.tool_started = 0.0  # 工具调用开始时间戳
        # 上次 AI 回答统计
        self.last_response_time = 0.0
        self.last_input_tokens = 0
        self.last_output_tokens = 0
        self.last_total_tokens = 0

    def render(self) -> list:
        """生成状态条文本（prompt_toolkit FormattedText 列表）"""
        from datetime import datetime
        parts = []
        # 模型 / 提供商
        if self.provider == "未配置" or self.model == "未配置":
            parts.append(("class:status-red", "未配置"))
        elif self.is_mock:
            parts.append(("class:status-yellow", f"mock/{self.model}"))
        else:
            parts.append(("class:status-cyan", f"{self.provider}/{self.model}"))
        # 工作目录
        if self.directory:
            short_dir = self.directory
            if len(short_dir) > 20:
                short_dir = "..." + short_dir[-17:]
            parts.append(("class:status-green", f"{short_dir}"))
        # 当前时间
        parts.append(("class:status-gray", f"{datetime.now().strftime('%H:%M:%S')}"))
        # 上次耗时
        if self.last_response_time > 0:
            parts.append(("class:status-yellow", f"{self.last_response_time:.1f}s"))
        # Token 统计
        if self.last_total_tokens > 0:
            parts.append(("class:status-yellow", f"{self.last_input_tokens}/{self.last_output_tokens}/{self.last_total_tokens}"))
        elif self.tokens_used or self.limit:
            parts.append(("class:status-yellow", f"{self.tokens_used}/{self.limit}"))
        # 思维模式
        if self.mode and self.mode != "direct":
            parts.append(("class:status-magenta", f"{self.mode}"))
        # 工具/忙碌/就绪状态
        if self.tool_name:
            import time
            elapsed = time.time() - self.tool_started if self.tool_started else 0
            parts.append(("class:status-yellow", f"{self.tool_name} ({elapsed:.1f}s)"))
        elif self.is_busy:
            frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            spinner = frames[self.spinner_frame % len(frames)]
            parts.append(("class:status-red", f"{spinner} 思考中"))
        else:
            parts.append(("class:status-green", "就绪"))

        # 用 " │ " 连接，生成 FormattedText 列表
        result = []
        for i, (style, text) in enumerate(parts):
            if i > 0:
                result.append(("class:status-sep", " │ "))
            result.append((style, text))
        return result


# ==================== 补全器 ====================

class FanRenCompleter(Completer):
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
        "ls": "文件", "cd": "文件",
        "dir": "文件", "dirs": "文件", "rmdir": "文件",
        "read_excel": "文件", "read_csv": "文件", "open": "文件",
        # 模型/配置
        "model": "模型",
        "key": "配置",
        "limit": "模型",
        "lang": "配置",
        "alias": "配置",
        "providers": "模型", "mode": "思维", "debug": "配置",
        # 网络
        "web": "网络", "fetch": "网络",
        "see": "多模态", "generate_image": "多模态",
        # 邮件/网盘
        "mail_": "邮件", "disk_": "网盘",
        # 定时/守护
        "cron_": "定时", "agent_cron_": "定时", "agent_server": "守护",
        "gatekeeper": "守护", "hermes": "守护",
        # Agent
        "agent_": "Agent", "remote_agent_": "Agent", "remote_setup": "Agent",
        "db_setup": "Agent",
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
        "key": "/key sk-xxx",
        "limit": "/limit 4096",
        "lang": "/lang en",
        "alias": "/alias mycmd /cat README.md",
        "providers": "/providers",
        "mode": "/mode cot",
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
        "dir": "/dir /path/to/dir",
        "dirs": "/dirs",
        "rmdir": "/rmdir old_dir",
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
        "see": "/see photo.jpg",
        "generate_image": '/generate_image "一只猫"',
        # 邮件
        "mail_setup": "/mail setup",
        "mail_inbox": "/mail inbox",
        "mail_read": "/mail read 1",
        "mail_send": '/mail send a@b.com "主题" "正文"',
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
        import re
        text = document.text_before_cursor
        # / 命令补全（按分类）
        if text.startswith("/"):
            stripped = text[1:]
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

            word = text[1:]
            all_cmds = self.get_commands()
            # 正则模糊匹配：优先前缀匹配，其次子串匹配
            matched = []
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
        # @ Agent 补全
        elif text.startswith("@"):
            word = text[1:]
            for agent_name, desc in self.get_agents():
                if agent_name.startswith(word) or not word:
                    short_desc = (desc[:30] + "...") if desc and len(desc) > 30 else (desc or "")
                    yield Completion(
                        agent_name + " ",
                        start_position=-len(word) if word else 0,
                        display="@" + agent_name,
                        display_meta=short_desc,
                    )


# ==================== TUI 主类 ====================

class FanRenPrompt:
    """基于 prompt_toolkit 的 TUI 输入面板

    用法：
        prompt = FanRenPrompt(state)
        text = prompt.get_input()  # None 表示退出
        if text is None:
            break
    """

    def __init__(self, state):
        self.state = state
        self.status = StatusState()
        # 记录真实 TTY 状态，用于某些需要 TTY 的操作
        self._is_tty = sys.stdin.isatty() and sys.stdout.isatty()
        self._session: Optional[PromptSession] = None
        self._completer: Optional[FanRenCompleter] = None
        self._kb: Optional[KeyBindings] = None
        self._spinner_thread: Optional[threading.Thread] = None
        self._spinner_stop = threading.Event()
        self._exit_requested = False

        # 只要 prompt_toolkit 可用就初始化 TUI
        # 某些终端（VS Code 集成终端、tmux、Windows Terminal）isatty() 可能误判
        if HAS_PT:
            self._init_tty()
        else:
            print(f"\033[93m⚠️ prompt_toolkit 未安装，使用基础 input()\033[0m", file=sys.stderr)
            print(f"  安装: pip install prompt_toolkit>=3.0.0", file=sys.stderr)

    def _init_tty(self):
        """初始化 prompt_toolkit session"""
        # 历史文件
        history_file = ROOT / "history" / "input_history"
        history_file.parent.mkdir(parents=True, exist_ok=True)

        # 补全器
        self._completer = FanRenCompleter(
            get_commands=self._get_command_completions,
            get_agents=self._get_agent_completions,
        )

        # 快捷键
        self._kb = self._build_keybindings()

        # 在 PromptSession 初始化时设置 bottom_toolbar，确保 Layout 正确计算高度
        self._prefix_hint = ""

        def _toolbar():
            result = []
            if self._prefix_hint:
                result.append(("class:hint", f"{self._prefix_hint}  "))
            result.extend(self.status.render())
            return result

        self._session = PromptSession(
            history=FileHistory(str(history_file)),
            completer=self._completer,
            complete_while_typing=False,  # 禁用自动补全，避免唯一匹配时自动提交
            key_bindings=self._kb,
            mouse_support=False,
            bottom_toolbar=_toolbar,
            style=Style.from_dict({
                "indicator": "ansicyan bold",
                "placeholder": "ansibrightblack",
                "separator": "ansibrightblack",
                "input-label": "bg:ansicyan ansiblack bold",
                "hint": "ansiyellow",
                "status-yellow": "ansiyellow",
                "status-cyan": "ansibrightcyan",
                "status-green": "ansigreen",
                "status-gray": "ansibrightblack",
                "status-magenta": "ansimagenta",
                "status-red": "ansired",
                "status-sep": "ansibrightblack",
                "completion-menu": "bg:#1e1e1e #ffffff",
                "completion-menu.completion": "bg:#1e1e1e #cccccc",
                "completion-menu.completion.current": "bg:#094771 #ffffff bold",
                "completion-menu.meta": "bg:#1e1e1e #888888",
                "completion-menu.meta.current": "bg:#094771 #ffffff",
                "scrollbar.arrow": "bg:#1e1e1e #888888",
                "scrollbar": "bg:#1e1e1e #444444",
            }),
        )

    def _build_keybindings(self) -> KeyBindings:
        """构建快捷键绑定"""
        kb = KeyBindings()

        @kb.add("/")
        def _(event):
            """输入 / 时自动触发补全菜单"""
            event.current_buffer.insert_text("/")
            event.current_buffer.start_completion(select_first=False)

        @kb.add("enter")
        def _(event):
            """Enter = 提交（默认单行模式）"""
            event.current_buffer.validate_and_handle()

        @kb.add("escape", "enter")
        def _(event):
            """Esc+Enter = 换行（多行输入）"""
            event.current_buffer.insert_text("\n")

        @kb.add("c-j")
        def _(event):
            """Ctrl+J = 换行（多行输入）"""
            event.current_buffer.insert_text("\n")

        @kb.add("c-l")
        def _(event):
            """Ctrl+L = 清屏"""
            event.app.renderer.erase()

        @kb.add("c-c")
        def _(event):
            """Ctrl+C = 清空当前输入（不退出）"""
            # 使用 reset() 替代 text="" 以彻底清除 buffer 的 IME/preedit 状态
            event.current_buffer.reset()
            # 强制清除终端渲染状态，防止残留字符
            event.app.renderer.erase()

        @kb.add("c-d")
        def _(event):
            """Ctrl+D = 退出"""
            self._exit_requested = True
            event.app.exit(result=None)

        # 编辑/重试/撤销 快捷键：返回特殊标记让 main.py 处理
        # 使用 Ctrl+字母 避免干扰普通文本输入（用户可能输入含 e/r/u 的消息）
        @kb.add("c-e")
        def _(event):
            """Ctrl+E = 编辑上一条 AI 回答"""
            event.app.exit(result="__ACTION__:edit")

        @kb.add("c-r")
        def _(event):
            """Ctrl+R = 重试上一条 user prompt"""
            event.app.exit(result="__ACTION__:retry")

        @kb.add("c-u")
        def _(event):
            """Ctrl+U = 撤销最后一条对话"""
            event.app.exit(result="__ACTION__:undo")

        # Esc：流式输出中按下立即中断（让 stream_cnt 检测到）
        @kb.add("escape")
        def _(event):
            """Esc = 立即中断当前流式输出"""
            try:
                from fr_cli.core.stream import request_interrupt
                request_interrupt()
            except Exception:
                pass
            # 不退出 prompt（用户可能还要再发）

        return kb

    def _get_command_completions(self) -> List[tuple]:
        """获取所有 / 命令的 (name, description) 列表（优先使用别名，方便用户按实际输入过滤）"""
        try:
            from fr_cli.command.registry import get_registry
            reg = get_registry()
            cmds = []
            seen = set()
            for name, tool in reg._tools.items():
                desc = tool.get("description", "")
                aliases = [a.lstrip("/") for a in tool.get("aliases", []) if a.lstrip("/")]
                # 优先使用短别名作为展示名（用户实际输入的命令）
                display_name = aliases[0] if aliases else name
                if display_name in seen:
                    continue
                seen.add(display_name)
                cmds.append((display_name, desc))
            # 按名称排序
            return sorted(cmds, key=lambda x: x[0])
        except Exception:
            return []

    def _get_agent_completions(self) -> List[tuple]:
        """获取所有 @ Agent 名称（含内置和用户）"""
        agents = []
        # 内置 Agent
        builtin = [
            ("local", "本地系统命令生成与执行"),
            ("remote", "远程 SSH 命令"),
            ("spider", "网页爬虫"),
            ("db", "数据库智能助手"),
            ("RAG", "本地知识库问答"),
        ]
        agents.extend(builtin)
        # 用户 Agent
        try:
            from fr_cli.agent.manager import list_agents
            for a in list_agents():
                agents.append((a.get("name", ""), "用户 Agent"))
        except Exception:
            pass
        return agents

    def _invalidate(self):
        """触发 prompt_toolkit 重绘底部状态栏"""
        if self._session and hasattr(self._session, 'app'):
            try:
                self._session.app.invalidate()
            except Exception:
                pass

    def update_last_stats(self, response_time: float = 0, input_tokens: int = 0,
                          output_tokens: int = 0, total_tokens: int = 0):
        """更新上次 AI 回答的统计信息并触发重绘"""
        self.status.last_response_time = response_time
        self.status.last_input_tokens = input_tokens
        self.status.last_output_tokens = output_tokens
        self.status.last_total_tokens = total_tokens
        self._invalidate()

    def set_busy(self, busy: bool):
        """设置 AI 是否正在生成（控制 spinner）"""
        self.status.is_busy = busy
        if busy:
            self._start_spinner()
        else:
            self._stop_spinner()
        self._invalidate()

    def set_tool(self, tool_name: str):
        """设置当前正在调用的工具（状态条显示）"""
        import time
        self.status.tool_name = tool_name
        self.status.tool_started = time.time() if tool_name else 0.0
        self._invalidate()

    def set_mock(self, is_mock: bool):
        """切换 mock 模式显示"""
        self.status.is_mock = is_mock
        self._invalidate()

    def _start_spinner(self):
        """启动 spinner 线程（仅更新 frame，不直接写 stdout）"""
        if self._spinner_thread and self._spinner_thread.is_alive():
            return
        self._spinner_stop.clear()
        self._spinner_thread = threading.Thread(target=self._spin_loop, daemon=True)
        self._spinner_thread.start()

    def _stop_spinner(self):
        """停止 spinner"""
        self._spinner_stop.set()
        if self._spinner_thread:
            self._spinner_thread.join(timeout=0.5)

    def _spin_loop(self):
        """spinner 循环：只更新 frame 并触发 prompt_toolkit 重绘"""
        while not self._spinner_stop.is_set():
            self.status.spinner_frame += 1
            self._invalidate()
            self._spinner_stop.wait(0.1)

    def get_input(self, prefix_hint: str = "") -> Optional[str]:
        """获取用户输入

        Args:
            prefix_hint: 在 prompt 前打印的提示（如 "💡 试试 /help"）
        Returns:
            str: 用户输入（已 strip）
            "" : 用户按 Ctrl+C 清空
            None: 用户按 Ctrl+D 退出
        """
        if self._session is None:
            try:
                if prefix_hint:
                    print(prefix_hint)
                line = input()
                return line.strip() if line else ""
            except EOFError:
                return None
            except KeyboardInterrupt:
                return ""

        try:
            self._prefix_hint = prefix_hint
            indicator = FormattedText([("class:indicator", " ▍ ")])
            placeholder = FormattedText([
                ("class:placeholder", "  输消息 · / 命令 · @ Agent · ! shell · Ctrl+E/R/U 编辑")
            ])

            result = self._session.prompt(
                indicator,
                placeholder=placeholder,
                complete_style="READLINE_LIKE",
                complete_in_thread=True,
            )
            self._exit_requested = False
            return result.strip() if result else ""
        except EOFError:
            return None
        except KeyboardInterrupt:
            return ""
        finally:
            self._prefix_hint = ""

    def confirm(self, prompt_text: str, default: bool = True) -> bool:
        """Y/n 确认提示

        Args:
            prompt_text: 提示文字
            default: 默认值（True=Enter 接受，False=Enter 拒绝）
        """
        suffix = " [Y/n]: " if default else " [y/N]: "
        if self._session is None:
            try:
                ans = input(prompt_text + suffix).strip().lower()
                if not ans:
                    return default
                return ans in ("y", "yes")
            except (EOFError, KeyboardInterrupt):
                return False

        # TTY 模式：用 prompt_toolkit 直接读
        try:
            result = self._session.prompt(prompt_text + suffix)
            ans = result.strip().lower()
            if not ans:
                return default
            return ans in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

    def update_status(self, **kwargs):
        """更新状态条信息"""
        for k, v in kwargs.items():
            if hasattr(self.status, k):
                setattr(self.status, k, v)


# ==================== 降级兼容 ====================

class FallbackPrompt:
    """非 TTY 环境的 fallback（HTTP 服务 / CI）

    在 fallback 模式下：
    - 用户输入 `/` → 打印分类命令列表（替代 TUI 弹窗）
    - 用户输入 `/xxx` → 如果是已知命令，照常返回让 main 路由处理
    """

    def __init__(self, state):
        self.state = state
        self.status = StatusState()

    def get_input(self, prefix_hint: str = "") -> Optional[str]:
        try:
            if prefix_hint:
                print(prefix_hint)
            line = input().strip()
            # 用户只输入 `/` → 触发分类命令列表
            if line == "/":
                self._print_command_categories()
                # 让用户重新输入
                return self.get_input()
            return line
        except (EOFError, KeyboardInterrupt):
            return None

    def _print_command_categories(self):
        """打印分类命令列表（fallback 模式专属）"""
        from fr_cli.command.registry import get_registry
        from fr_cli.ui.prompt import FanRenCompleter
        tools = get_registry().get_tools()
        completer = FanRenCompleter(lambda: [], lambda: [])
        # 按 cat 分组：每个工具的主名 + aliases 都展示
        categorized = {}
        seen = set()
        for t in tools:
            cat = completer._categorize(t["name"])
            for alias in [t["name"]] + t["aliases"]:
                # 去掉前缀 /，加 / 显示
                cmd = alias.lstrip("/")
                key = (cat, cmd)
                if key in seen:
                    continue
                seen.add(key)
                categorized.setdefault(cat, []).append((cmd, t.get("description", "")))
        print()
        print("命令列表")
        for cat in sorted(categorized.keys()):
            print(f"\n[{cat}]")
            for cmd, desc in sorted(categorized[cat]):
                example = FanRenCompleter.COMMAND_EXAMPLES.get(cmd, "")
                print(f"  /{cmd} | {desc} | {example}")
        print()
        print("提示: 直接输入 /xxx 回车执行  |  输入 /exit 退出")

    def confirm(self, prompt_text: str, default: bool = True) -> bool:
        # 非交互环境默认拒绝
        import os
        if os.environ.get("FR_CLI_NON_INTERACTIVE"):
            return False
        try:
            suffix = " [Y/n]: " if default else " [y/N]: "
            ans = input(prompt_text + suffix).strip().lower()
            if not ans:
                return default
            return ans in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

    def set_busy(self, busy: bool):
        pass

    def update_status(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self.status, k):
                setattr(self.status, k, v)


def create_prompt(state):
    """工厂函数：自动选择 TUI 或 fallback

    - 真 TTY 终端 + prompt_toolkit 可用 → FanRenPrompt（TUI 多列补全）
    - non-TTY / CI / HTTP / pipe → FallbackPrompt（纯 input + 命令列表打印）
    """
    if HAS_PT and sys.stdin.isatty() and sys.stdout.isatty():
        return FanRenPrompt(state)
    return FallbackPrompt(state)
