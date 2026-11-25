"""
动态构建系统 —— 按需生成工具

让 fr-cli 根据用户需求自主安装依赖并构建新工具，
注册到命令注册表后供用户和大模型调用。

v2.8.7：改为**惰性导入**（PEP 562）。

原因：``sandbox_worker`` 通过 ``python -m fr_cli.dynamic_builder.sandbox_worker``
拉起子进程。若本文件在导入期就拉起 ``runner``，子进程会连带导入
``command.executor`` → ``command.registry`` → ``weapon.mcp`` → ``mcp`` 整条重链
（实测约 0.79s，其中 ``mcp.types`` 一项就 174ms）—— 而子进程只需要
``sandbox`` + ``weapon.fs``。

对外接口不变：``from fr_cli.dynamic_builder import build_tool`` 照常可用
（PEP 562 的模块级 ``__getattr__`` 会在首次访问时真正导入）。
"""
from typing import Any

__all__ = [
    "build_tool",
    "list_built_tools",
    "remove_built_tool",
    "bootstrap_dynamic_tools",
]

#: 导出名 → 真正的实现模块
_LAZY_EXPORTS = {
    "build_tool": "fr_cli.dynamic_builder.runner",
    "list_built_tools": "fr_cli.dynamic_builder.runner",
    "remove_built_tool": "fr_cli.dynamic_builder.runner",
    "bootstrap_dynamic_tools": "fr_cli.dynamic_builder.runner",
}


def __getattr__(name: str) -> Any:
    """首次访问导出名时才真正导入实现模块。"""
    module_path = _LAZY_EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib
    value = getattr(importlib.import_module(module_path), name)
    globals()[name] = value          # 缓存，后续访问不再走 __getattr__
    return value


def __dir__():
    return sorted(__all__)
