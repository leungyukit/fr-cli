"""
REPL 命令路由处理器（模块化重构版）
所有 / 命令实现按功能分组到子模块，保持单一职责。
"""

from fr_cli.repl.commands._common import _provider_has_key, _print_help
from fr_cli.repl.commands.base import (
    _cmd_exit, _cmd_shell, _cmd_help, _cmd_see,
    _cmd_update, _cmd_mode, _cmd_banner, _cmd_tutorial,
)
from fr_cli.repl.commands.config import (
    _cmd_model, _cmd_key, _cmd_providers, _cmd_limit, _cmd_lang,
)
from fr_cli.repl.commands.fs import _cmd_dir, _cmd_dirs, _cmd_rmdir
from fr_cli.repl.commands.session import (
    _cmd_save, _cmd_load, _cmd_del,
    _cmd_session_list, _cmd_session_load, _cmd_session_del,
    _cmd_new,
)
from fr_cli.repl.commands.agent import (
    _cmd_agent_create, _cmd_agent_list, _cmd_agent_delete,
    _cmd_agent_show, _cmd_agent_run, _cmd_agent_edit,
    _cmd_agent_forge, _cmd_agent_model,
)
from fr_cli.repl.commands.remote_agent import (
    _cmd_remote_agent_add, _cmd_remote_agent_list,
    _cmd_remote_agent_del, _cmd_agent_publish,
    _cmd_remote_agent_scan, _cmd_remote_agent_import,
)
from fr_cli.repl.commands.system import (
    _cmd_agent_server, _cmd_gatekeeper, _cmd_open,
    _cmd_launch, _cmd_apps, _cmd_hermes_daemon,
    _cmd_remote_setup, _cmd_db_setup,
)
from fr_cli.repl.commands.rag import _cmd_rag_dir, _cmd_rag_watch, _cmd_rag_sync
from fr_cli.repl.commands.dataframe import _cmd_read_excel, _cmd_read_csv
from fr_cli.repl.commands.mcp import (
    _cmd_mcp_list, _cmd_mcp_add, _cmd_mcp_del,
    _cmd_mcp_enable, _cmd_mcp_disable, _cmd_mcp_refresh,
)
from fr_cli.repl.commands.cron import (
    _cmd_agent_cron_add, _cmd_agent_cron_list, _cmd_agent_cron_del,
)
from fr_cli.repl.commands.dev import _cmd_master, _cmd_commit, _cmd_pr, _cmd_review
