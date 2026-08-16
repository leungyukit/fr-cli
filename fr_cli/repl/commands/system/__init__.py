"""
REPL 系统级命令子模块：
- server.py    Agent HTTP / Gatekeeper 守护
- launcher.py  本地应用启动
- hermes_cmd.py  Hermes 守护进程与任务管理
- context.py   上下文压缩管理
- setup.py     远程/数据库初始化向导
- autostart.py 一键启动所有后台服务
- status.py    全局状态面板
"""
from fr_cli.repl.commands.system.server import _cmd_agent_server, _cmd_gatekeeper
from fr_cli.repl.commands.system.launcher import _cmd_apps, _cmd_launch, _cmd_open
from fr_cli.repl.commands.system.hermes_cmd import _cmd_hermes_daemon
from fr_cli.repl.commands.system.context import _cmd_context
from fr_cli.repl.commands.system.setup import _cmd_db_setup, _cmd_remote_setup
from fr_cli.repl.commands.system.autostart import _cmd_autostart
from fr_cli.repl.commands.system.status import _cmd_status
from fr_cli.repl.commands.system.start import _cmd_start

# 旧式兼容：保留旧模块顶层引用（_cmd_context 依赖的 maybe_compress / estimate_tokens）
from fr_cli.memory.compress import estimate_tokens, maybe_compress

# 修复测试 patch 路径不命中：让 context 子模块中的 maybe_compress / estimate_tokens
# 指向本模块（即 system 包）的同名对象，从而 `patch("fr_cli.repl.commands.system.maybe_compress")`
# 能替换 _cmd_context 实际调用的对象。
from fr_cli.repl.commands.system import context as _context_mod
_context_mod.maybe_compress = maybe_compress
_context_mod.estimate_tokens = estimate_tokens
del _context_mod

__all__ = [
    "_cmd_agent_server",
    "_cmd_apps",
    "_cmd_autostart",
    "_cmd_context",
    "_cmd_db_setup",
    "_cmd_gatekeeper",
    "_cmd_hermes_daemon",
    "_cmd_launch",
    "_cmd_open",
    "_cmd_remote_setup",
    "_cmd_status",
]
