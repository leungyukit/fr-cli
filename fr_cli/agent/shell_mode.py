"""
Shell 模式 - 支持 Ctrl-X 切换
参考 kimi-cli 实现的 shell 命令执行功能
"""

import os
import sys
import shlex
import subprocess
import signal
from typing import Optional, Callable, Tuple
from enum import Enum


class ShellMode(Enum):
    """Shell 模式"""
    AGENT = "agent"
    SHELL = "shell"


class ShellModeManager:
    """Shell 模式管理器"""

    def __init__(self):
        self.current_mode = ShellMode.AGENT
        self.history = []
        self.last_exit_code = 0
        self._original_sigint = signal.getsignal(signal.SIGINT)

    def switch_mode(self) -> ShellMode:
        """切换模式"""
        if self.current_mode == ShellMode.AGENT:
            self.current_mode = ShellMode.SHELL
            print("\n[Shell 模式] 直接输入命令执行，Ctrl+X 切换回 Agent 模式")
        else:
            self.current_mode = ShellMode.AGENT
            print("\n[Agent 模式] 输入消息与 AI 对话，Ctrl+X 切换到 Shell 模式")
        return self.current_mode

    def execute_command(self, command: str) -> Tuple[str, int]:
        """执行 Shell 命令"""
        if not command.strip():
            return "", 0

        self.history.append(command)

        try:
            # 使用 shell 执行
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300
            )
            self.last_exit_code = result.returncode

            output = result.stdout + result.stderr
            return output, result.returncode

        except subprocess.TimeoutExpired:
            return "命令执行超时 (5分钟)", 124
        except Exception as e:
            return f"执行错误: {str(e)}", 1

    def execute_background(self, command: str, callback: Optional[Callable] = None):
        """后台执行命令"""
        try:
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            if callback:
                stdout, stderr = process.communicate()
                callback(stdout, stderr, process.returncode)
            else:
                return process

        except Exception as e:
            print(f"后台执行错误: {e}")
            return None


class InteractiveShell:
    """交互式 Shell"""

    def __init__(self, on_agent_command: Callable[[str], None] = None):
        self.shell_mgr = ShellModeManager()
        self.on_agent_command = on_agent_command
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """设置信号处理器"""
        def handler(signum, frame):
            # Ctrl+C 在 shell 模式下直接退出
            if self.shell_mgr.current_mode == ShellMode.SHELL:
                print("\n[退出 Shell 模式]")
                self.shell_mgr.current_mode = ShellMode.AGENT

        signal.signal(signal.SIGINT, handler)

    def handle_ctrl_x(self):
        """处理 Ctrl-X 切换"""
        return self.shell_mgr.switch_mode()

    def run_shell_loop(self, prompt: str = "(shell) $ "):
        """运行 Shell 循环"""
        print("Shell 模式 - 输入命令直接执行，输入 'exit' 或 Ctrl+C 返回 Agent 模式")
        print("提示: Ctrl+X 可快速切换到 Agent 模式\n")

        while self.shell_mgr.current_mode == ShellMode.SHELL:
            try:
                command = input(prompt).strip()

                if not command:
                    continue

                if command in ['exit', 'quit', 'q']:
                    print("退出 Shell 模式")
                    break

                output, code = self.shell_mgr.execute_command(command)
                print(output)
                if code != 0:
                    print(f"[exit {code}]")

            except EOFError:
                break
            except KeyboardInterrupt:
                print("\n退出 Shell 模式")
                break

        return ShellMode.AGENT

    def process_input(self, user_input: str) -> Tuple[bool, Optional[str]]:
        """
        处理用户输入
        返回: (is_shell_command, result)
        - is_shell_command=True: 已在 Shell 模式处理
        - is_shell_command=False: 需要发送给 Agent
        """
        if self.shell_mgr.current_mode == ShellMode.SHELL:
            if user_input.strip():
                output, code = self.shell_mgr.execute_command(user_input)
                return True, output
            return True, None

        return False, None


# 全局实例
_shell_manager = None

def get_shell_manager() -> ShellModeManager:
    """获取 Shell 管理器"""
    global _shell_manager
    if _shell_manager is None:
        _shell_manager = ShellModeManager()
    return _shell_manager


def is_shell_mode() -> bool:
    """检查是否在 Shell 模式"""
    mgr = get_shell_manager()
    return mgr.current_mode == ShellMode.SHELL


def switch_to_shell_mode():
    """切换到 Shell 模式"""
    mgr = get_shell_manager()
    mgr.current_mode = ShellMode.SHELL


def switch_to_agent_mode():
    """切换到 Agent 模式"""
    mgr = get_shell_manager()
    mgr.current_mode = ShellMode.AGENT