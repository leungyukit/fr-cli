"""
动态构建系统 —— 按需生成工具

让 fr-cli 根据用户需求自主安装依赖并构建新工具，
注册到命令注册表后供用户和大模型调用。
"""
from fr_cli.dynamic_builder.runner import (
    build_tool,
    list_built_tools,
    remove_built_tool,
    bootstrap_dynamic_tools,
)

__all__ = [
    "build_tool",
    "list_built_tools",
    "remove_built_tool",
    "bootstrap_dynamic_tools",
]
