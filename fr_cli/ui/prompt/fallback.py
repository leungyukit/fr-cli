"""
fr-cli TUI 降级方案 —— 非 TTY 环境（HTTP 服务 / CI / pipe）

行为：
- 用户输入 / → 打印分类命令列表（替代 TUI 弹窗）
- 用户输入 /xxx → 如果是已知命令，照常返回让 main 路由处理
- Y/n 确认在非交互环境下默认拒绝
"""
import os
from typing import Optional

from fr_cli.ui.prompt.status import StatusState


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
        from fr_cli.ui.prompt.completer import FanRenCompleter
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
