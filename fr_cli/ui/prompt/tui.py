"""
fr-cli TUI 主面板 —— 基于 prompt_toolkit

特性：
- 多行编辑（Enter 发送、Shift+Enter / Ctrl+J 换行）
- / 命令补全（带描述）
- @ Agent 补全
- 历史回溯（跨 session 持久化）
- 底部状态条（model / token / dir / mode / 队列深度 / 待生效转向指令）
- 快捷键：Ctrl+L 清屏、Ctrl+C 清空（生成中只打断）、Ctrl+S 转向注入、
  Ctrl+D 退出、Esc 取消
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
from fr_cli.ui.ui import CYAN, DIM, YELLOW, RESET
from fr_cli.conf.paths import ROOT

# 输入态指示符: 蓝色小箭头(样式见 _PROMPT_STYLE 的 "indicator"), 与输入区上方
# 的蓝色分隔线组成"输入区"视觉; Enter 提交后分隔线变浅灰表示退出输入态。
# 3 字符宽度(" ❯ ")与旧指示符(" ▍ ")一致, placeholder 的前导对齐不用改。
INPUT_INDICATOR = ("class:indicator", " ❯ ")

# prompt_toolkit 样式表(模块级常量, 便于测试锁定"蓝色箭头"不回退)
_PROMPT_STYLE = {
    "indicator": "ansibrightblue bold",
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
    "scrollbar": "bg:#444444",
}


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
            print(f"{YELLOW}[!] prompt_toolkit 未安装，使用基础 input(){RESET}", file=sys.stderr)
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
            get_files=self._get_file_completions,
        )

        # 快捷键
        self._kb = self._build_keybindings()

        # 在 PromptSession 初始化时设置 bottom_toolbar，确保 Layout 正确计算高度
        self._prefix_hint = ""

        def _toolbar():
            # v2.8.7(UX)：状态栏实时反映队列深度 / 待生效转向指令
            self._sync_dynamic_status()
            result = []
            if self._prefix_hint:
                result.append(("class:hint", f"{self._prefix_hint}  "))
            result.extend(self.status.render(self._terminal_width()))
            return result

        self._session = PromptSession(
            history=FileHistory(str(history_file)),
            completer=self._completer,
            complete_while_typing=True,   # 输入 / / @ 时自动弹出补全菜单
            key_bindings=self._kb,
            mouse_support=False,
            bottom_toolbar=_toolbar,
            style=Style.from_dict(_PROMPT_STYLE),
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
            """Ctrl+C —— 空闲时清空输入；AI 生成中只中断流式输出、**保留草稿**

            v2.8.7(UX) 语义拆分（对齐 kimi-cli）：
            - AI 正在回答：用户多半是"等太久了"，按 Ctrl+C 只想让它停下，
              这时把已经敲好的草稿一起清掉是误伤 —— 故只打断，不清草稿；
            - 空闲：保持传统 Unix 语义，Ctrl+C 清空当前行。
            """
            queue_mgr = getattr(self.state, "_queue_mgr", None)
            if queue_mgr is not None and queue_mgr.is_processing:
                # 生成中：只请求中断（stream_cnt 会显示 [已中断]），草稿原样留着
                self._request_interrupt()
                return

            # 空闲：使用 reset() 替代 text="" 以彻底清除 buffer 的 IME/preedit 状态
            event.current_buffer.reset()
            # 强制清除终端渲染状态，防止残留字符
            event.app.renderer.erase()

        @kb.add("c-s")
        def _(event):
            """Ctrl+S —— 把当前输入作为**转向指令**注入正在运行的这一轮

            v2.8.7(UX)：流式期间可交互。
            与 Enter 的区别：
            - Enter：排进对话队列，**下一轮**独立处理；
            - Ctrl+S：注入**当前轮**，模型带着新指令在同一轮里继续推理。

            空闲时按 Ctrl+S 无意义（此时应直接 Enter），故不暂存。
            """
            buffer = event.current_buffer
            text = (buffer.text or "").strip()
            if not text:
                return

            queue_mgr = getattr(self.state, "_queue_mgr", None)
            if queue_mgr is None or not queue_mgr.is_processing:
                # 没有正在跑的对话 —— 无处可注入，提示用户改用 Enter
                self._notify(f"{DIM}当前没有进行中的对话，直接按 Enter 提交即可{RESET}")
                return

            from fr_cli.core.steering import push_steer
            count = push_steer(self.state, text)

            # 取走输入框内容，避免和 Enter 语义混淆（重复提交）
            buffer.reset()
            event.app.renderer.erase()
            self._notify(f"{CYAN}↯ 转向指令已注入（{count} 条待生效）{RESET}")
            self._invalidate()

        @kb.add("c-o")
        def _(event):
            """Ctrl+O —— 展开最近一次被折叠的内容

            v2.8.7(UX)：超长回答与超长命令输出都会被折叠（省略号 + 尾部），
            折叠掉的内容存在 ``fr_cli/core/collapse.py`` 里，这里原样打印回来。
            """
            from fr_cli.core.collapse import take

            item = take()
            if item is None:
                self._notify(f"{DIM}没有可展开的折叠内容{RESET}")
                return

            def _run():
                print(f"\n{DIM}──── 展开：{item.meta or '折叠内容'} ────{RESET}")
                print(item.text)

            self._run_in_terminal(_run)
            self._invalidate()

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
            self._request_interrupt()
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

    def _get_file_completions(self, prefix: str = "") -> List[tuple]:
        """获取可补全的文件路径（@ 补全用）

        v2.8.7(UX)：只列**一层**不递归 —— 递归扫描大目录会让补全卡住。
        根目录取用户配置的 allowed_dirs（VFS 可写范围）+ 当前工作目录。

        Args:
            prefix: 已输入的路径片段（前缀匹配，大小写不敏感）

        Returns:
            list[tuple[str, str]]: (路径, 说明) 列表，最多 30 条
        """
        import os
        from pathlib import Path

        roots = []
        try:
            allowed = (getattr(self.state, "cfg", None) or {}).get("allowed_dirs") or []
        except Exception:
            allowed = []
        for d in allowed:
            try:
                p = Path(d).expanduser()
                if p.is_dir():
                    roots.append(p)
            except Exception:
                continue
        try:
            roots.append(Path(os.getcwd()))
        except Exception:
            pass

        needle = (prefix or "").lower()
        results = []
        seen = set()
        for root in roots:
            try:
                entries = sorted(root.iterdir(), key=lambda x: x.name.lower())
            except Exception:
                continue
            for entry in entries:
                name = entry.name
                if needle and needle not in name.lower():
                    continue
                if name.startswith("."):
                    continue
                key = str(entry)
                if key in seen:
                    continue
                seen.add(key)
                suffix = "/" if entry.is_dir() else ""
                results.append((name + suffix, "目录" if entry.is_dir() else "文件"))
                if len(results) >= 30:
                    return results
        return results

    def _invalidate(self):
        """触发 prompt_toolkit 重绘底部状态栏"""
        if self._session and hasattr(self._session, 'app'):
            try:
                self._session.app.invalidate()
            except Exception:
                pass

    @staticmethod
    def _request_interrupt():
        """请求中断当前流式输出（Esc / Ctrl+C 共用）"""
        try:
            from fr_cli.core.stream import request_interrupt
            request_interrupt()
        except Exception:
            pass

    @staticmethod
    def _run_in_terminal(func):
        """在 prompt_toolkit 的终端层执行一个打印动作。

        prompt_toolkit 下裸 print 会和渲染打架，用 run_in_terminal 把输出
        挪到提示符上方；没有运行中的事件循环时（无 TTY 的测试环境）
        退回普通调用。
        """
        def _safe():
            try:
                func()
            except Exception:
                pass

        try:
            import asyncio
            asyncio.get_running_loop()
        except Exception:
            # 不在事件循环里 —— run_in_terminal 不可用
            _safe()
            return

        try:
            from prompt_toolkit.application import run_in_terminal
            run_in_terminal(_safe)
        except Exception:
            _safe()

    @staticmethod
    def _notify(message: str):
        """在输入框上方打印一行提示，不破坏当前输入行"""
        FanRenPrompt._run_in_terminal(lambda: print(message))

    def _terminal_width(self) -> int:
        """当前终端宽度（用于状态栏按宽度裁剪）"""
        try:
            from prompt_toolkit.application import get_app
            return int(get_app().output.get_size().columns)
        except Exception:
            pass
        try:
            import shutil
            return shutil.get_terminal_size(fallback=(80, 24)).columns
        except Exception:
            return 80

    def _sync_dynamic_status(self):
        """把队列深度 / 待生效转向指令数同步到状态条

        由底部状态栏的 toolbar 回调驱动 —— 生成期间 spinner 每 0.1s 触发
        一次 invalidate，状态条因此能实时反映这两个数字。
        """
        try:
            queue_mgr = getattr(self.state, "_queue_mgr", None)
            self.status.queue_depth = queue_mgr.depth() if queue_mgr is not None else 0
        except Exception:
            self.status.queue_depth = 0
        try:
            from fr_cli.core.steering import steer_count
            self.status.steer_pending = steer_count(self.state)
        except Exception:
            self.status.steer_pending = 0
        try:
            # v2.8.7：待确认的高危操作（后台线程在等主线程代读输入）
            from fr_cli.security.interactive import BROKER
            self.status.confirm_pending = BROKER.pending_desc() if BROKER.has_pending() else ""
        except Exception:
            self.status.confirm_pending = ""

    def update_last_stats(self, response_time: float = 0, input_tokens: int = 0,
                          output_tokens: int = 0, total_tokens: int = 0):
        """更新上次 AI 回答的统计信息并触发重绘"""
        self.status.last_response_time = response_time
        self.status.last_input_tokens = input_tokens
        self.status.last_output_tokens = output_tokens
        self.status.last_total_tokens = total_tokens
        self._sync_context_usage()
        self._invalidate()

    def _sync_context_usage(self):
        """同步上下文占用（接近压缩阈值时状态栏预警）

        每轮回答结束后算一次（不是每次状态栏刷新都算 —— 状态栏每 0.1s
        刷新一次，重算整个 messages 的 token 会拖慢输入响应）。
        """
        try:
            from fr_cli.memory.compress import estimate_tokens
            messages = self.state.get_messages()
            if not messages:
                return
            self.status.context_tokens = estimate_tokens(messages)
            self.status.context_limit = int(
                getattr(self.state, "context_compress_threshold", 0) or 0
            )
        except Exception:
            pass

    def set_busy(self, busy: bool):
        """设置 AI 是否正在生成（控制 spinner）"""
        self.status.is_busy = busy
        if busy:
            self._start_spinner()
        else:
            self._stop_spinner()
            # 本轮结束 —— 清掉工具字段。
            # 失败原因保留到本轮结束为止：工具结果本身不回显给用户，
            # 状态栏是失败现场唯一可见的地方。
            self.status.tool_name = ""
            self.status.tool_args = ""
            self.status.tool_source = ""
            self.status.tool_error = ""
            self.status.tool_started = 0.0
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
            prefix_hint: 在 prompt 前打印的提示（如 "试试 /help"）
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
            indicator = FormattedText([INPUT_INDICATOR])
            # v2.8.7(UX)：占位符精简
            # 此前是一行 40+ 字符的固定提示（把所有快捷键都塞进去），
            # 窄终端会溢出，而且 placeholder 一输入就消失 —— 没人读得到。
            # 现在只留"怎么用"的四种输入形态；快捷键交给 /help 与启动卡片。
            placeholder = FormattedText([
                ("class:placeholder", "  输消息 · /命令 · @Agent或文件 · !shell")
            ])

            result = self._session.prompt(
                indicator,
                placeholder=placeholder,
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
