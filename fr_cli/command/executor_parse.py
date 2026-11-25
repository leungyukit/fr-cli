"""
CommandExecutor 文本解析 mixin —— AI 响应中的调用标记解析

从 fr_cli.command.executor 拆出(原文件 509 行)。

v2.8.7 行为变更：解析实现已收敛到 ``fr_cli/core/tool_protocol.py``（单一真相源）。
本 mixin 保留原有方法签名作为**向后兼容的委托层**，不再自带实现 ——
此前传统路径与 ReAct 路径各有一套解析器，容错强度不一致，导致同一段
AI 文本在一条路径能解析、另一条路径被静默丢弃。

- _extract_tool_calls: 提取【调用：tool_name({...})】(支持嵌套括号,忽略字符串内括号)
- _parse_tool_kwargs:  JSON / Python dict / 宽松正则三级回退解析
- _loose_parse_kwargs: 最后一级回退(正则逐 key 提取)
"""
from __future__ import annotations

from typing import List, Tuple

from fr_cli.core.tool_protocol import (
    extract_marker_calls,
    loose_parse_kwargs,
    parse_tool_args,
)


class CommandParseMixin:
    """调用标记与参数解析（委托至 core.tool_protocol）"""

    def _loose_parse_kwargs(self, arg_str):
        """宽松解析 JSON 参数字符串（回退方案）"""
        return loose_parse_kwargs(arg_str)

    def _parse_tool_kwargs(self, arg_str):
        """安全解析工具参数字符串（JSON / Python dict / 宽松正则三级回退）"""
        parsed = parse_tool_args(arg_str)
        return {} if parsed is None else parsed

    def _extract_tool_calls(self, text) -> List[Tuple[str, str, str]]:
        """提取所有【调用：tool_name({...})】标记（支持嵌套括号，忽略字符串内的括号）"""
        return extract_marker_calls(text)
