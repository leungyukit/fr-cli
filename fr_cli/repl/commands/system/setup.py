"""
远程/数据库初始化向导命令：/remote_setup, /db_setup
"""


def _cmd_remote_setup(state, parts):
    from fr_cli.agent.builtins.remote import _setup_wizard
    _setup_wizard(state.lang)
    return False


def _cmd_db_setup(state, parts):
    from fr_cli.agent.builtins.db import _setup_wizard as db_setup
    db_setup(state.lang)
    return False
