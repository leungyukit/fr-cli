"""
Shell 模式 —— Ctrl-X 切换 Agent / Shell

仅保留 base.py 实际引用的最小接口：
- ShellMode: AGENT / SHELL 状态枚举
- ShellModeManager: 切换模式 + 执行 shell 命令（由 REPL 的 _cmd_shell 直接调用）
"""

import subprocess
from typing import Tuple


class ShellMode:
    """Shell 模式状态"""
    AGENT = "agent"
    SHELL = "shell"


class ShellModeManager:
    """Shell 模式管理器（单例，全局共享 current_mode）"""

    def __init__(self):
        self.current_mode = ShellMode.AGENT

    def execute_command(self, command: str) -> Tuple[str, int]:
        """执行一条 shell 命令，返回 (stdout+stderr, returncode)"""
        if not command.strip():
            return "", 0
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300,
            )
            return result.stdout + result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            return "命令执行超时 (5分钟)", 124
        except Exception as e:
            return f"执行错误: {e}", 1


_shell_manager = None


def get_shell_manager() -> ShellModeManager:
    """获取 Shell 管理器单例"""
    global _shell_manager
    if _shell_manager is None:
        _shell_manager = ShellModeManager()
    return _shell_manager
