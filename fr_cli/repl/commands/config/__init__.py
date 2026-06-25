"""
REPL 配置类命令（模块化重构版）
- /model, /model config
- /key, /providers
- /limit, /lang, /usage, /autonomous

按职责拆分为 model.py / key.py / misc.py 三个子模块，保持单一职责。
"""
from fr_cli.repl.commands.config.model import _cmd_model, _cmd_model_config
from fr_cli.repl.commands.config.key import _cmd_key, _cmd_providers
from fr_cli.repl.commands.config.misc import _cmd_autonomous, _cmd_lang, _cmd_limit, _cmd_usage

__all__ = [
    "_cmd_autonomous",
    "_cmd_key",
    "_cmd_lang",
    "_cmd_limit",
    "_cmd_model",
    "_cmd_model_config",
    "_cmd_providers",
    "_cmd_usage",
]
