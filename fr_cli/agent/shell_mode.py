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
        """执行一条 shell 命令，返回 (stdout+stderr, returncode)

        v2.8.7(P1-13)：此处**刻意保留** ``shell=True``，与
        ``weapon/launcher.py``（拼接应用名 + 目标，已改 ``shell=False``）
        的情况不同 —— 理由：

        1. **命令来源是用户自己**。调用方只有两处：
           ``repl/bang.py``（用户手输 ``!cmd``）与
           ``repl/commands/base.py``（shell 模式下的 ``input()``）。
           两者都直接来自终端输入，**没有任何 LLM 输出路径能到达这里**
           （注册表里的 ``shell`` 工具只是个桩，不执行命令）。
           因此不存在"模型把恶意字符串拼进命令"这条注入链。
        2. **shell=True 正是这个功能本身**。``!ls | grep x``、``!a > b``、
           ``!cmd && cmd2`` 都要靠 shell 解析；改成 ``shlex.split`` +
           ``shell=False`` 会让管道与重定向直接失效 —— 那不是修安全，
           是砍功能。

        真正的加固点在于"谁能把命令送进来"，而不是"用不用 shell"：
        如果将来要支持"AI 建议命令 → 用户确认后执行"，
        应走 ``security/`` 的确认流程 + 命令白名单，而不是在这里换解析方式。
        """
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
