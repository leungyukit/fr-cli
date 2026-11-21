"""
REPL 命令公共工具

原文件(420 行)已按职责拆分:
- _help_data.py:   /help 静态数据(新功能列表 / 命令简报 / 主题映射 / 分组命令表)
- _help_views.py:  /help 渲染(_print_new_commands / _print_command_detail / _print_help)
- _common.py:      本文件——跨命令模块共用的小工具 + 上述符号的 re-export

注意:registry 只扫描 registered/ 目录,_ 前缀文件不会被当命令注册;
本目录下的 _help_* 模块同理(不会被误注册)。
"""
from __future__ import annotations

from fr_cli.repl.commands._help_data import (  # noqa: F401 (re-export,旧导入路径兼容)
    _COMMAND_BRIEF,
    _NEW_COMMANDS,
    HELP_ALL_TOPICS,
    HELP_GROUPS_EN,
    HELP_GROUPS_ZH,
    HELP_TOPIC_MAP,
)
from fr_cli.repl.commands._help_views import (  # noqa: F401 (re-export,旧导入路径兼容)
    _print_command_detail,
    _print_help,
    _print_new_commands,
)


def _provider_has_key(state, provider_id):
    """检查指定提供商是否已配置 API Key（zhipu 向后兼容顶层 key）"""
    providers_cfg = state.cfg.get("providers", {})
    pcfg = providers_cfg.get(provider_id, {})
    has_key = bool(pcfg.get("key"))
    if not has_key and provider_id == "zhipu":
        has_key = bool(state.cfg.get("key", ""))
    return has_key
