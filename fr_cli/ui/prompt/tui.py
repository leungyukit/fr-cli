"""
fr-cli TUI 主面板 —— 基于 prompt_toolkit

特性：
- 多行编辑（Enter 发送、Shift+Enter / Ctrl+J 换行）
- / 命令补全（带描述）
- @ Agent 补全
- 历史回溯（跨 session 持久化）
- 底部状态条（model / token / dir / mode）
- 快捷键：Ctrl+L 清屏、Ctrl+C 清空、Ctrl+D 退出、Esc 取消
- AI 流式输出时 spinner
"""
import sys
import threading
from typing import List, Optional

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.formatted_text import FormattedText
    from prompt_toolkit.styles import Style

    HAS_PT = True
except ImportError:
    HAS_PT = False

from fr_cli.ui.prompt.completer import FanRenCompleter
from fr_cli.ui.prompt.status import StatusState
from fr_cli.ui.ui import YELLOW, RESET
from fr_cli.conf.paths import ROOT


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
            print(f"{YELLOW}⚠️ prompt_toolkit 未安装，使用基础 input(){RESET}", file=sys.stderr)
            print("  安装: pip install prompt_toolkit>=3.0.0", file=sys.stderr)

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
            complete_while_typing=True,   # 输入 / / @ 时自动弹出补全菜单
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

        @kb.add("/", eager=True)
        def _(event):
            """输入 / 时自动触发补全菜单

            eager=True 确保在 prompt_toolkit 默认可打印字符绑定之前处理，
            从而可靠地触发补全菜单。
            """
            event.current_buffer.insert_text("/")
            event.current_buffer.start_completion(select_first=False)

        @kb.add("tab", eager=True)
        @kb.add("c-i", eager=True)
        def _(event):
            """Tab / Ctrl+I 触发或切换补全"""
            b = event.current_buffer
            if b.complete_state:
                b.complete_next()
            else:
                b.start_completion(select_first=False)

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
            ("stock", "股票/量化交易助手"),
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
