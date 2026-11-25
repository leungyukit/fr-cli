"""
无头模式判定 —— 单一判定入口

v2.8.7 新增。

fr-cli 的无头模式（bot / 服务端进程 / 批处理）会关闭所有面向终端的
副作用：流式输出、统计行、功能推荐、交互式产物检测。

判定必须**严格**：
    getattr(state, "headless", False) is True

而不是 ``bool(getattr(state, "headless", False))`` —— 后者在测试里
用 MagicMock 充当 state 时会拿到一个 truthy 的 Mock，导致无头分支被
意外触发（真实场景无碍，但会让既有测试莫名其妙地挂掉）。

统一放在这里，避免各处重复写判断、也避免写法不一致。
"""
from __future__ import annotations

__all__ = ["is_headless"]


def is_headless(state) -> bool:
    """判断给定的 state 是否处于无头模式。"""
    return getattr(state, "headless", False) is True
