"""
CommandExecutor 文本解析 mixin —— AI 响应中的调用标记解析

从 fr_cli.command.executor 拆出(原文件 509 行)。
本 mixin 只做纯文本解析,不依赖 registry / state:
- _extract_tool_calls: 提取【调用：tool_name({...})】(支持嵌套括号,忽略字符串内括号)
- _parse_tool_kwargs:  JSON / Python dict / 宽松正则三级回退解析
- _loose_parse_kwargs: 最后一级回退(正则逐 key 提取)
"""
from __future__ import annotations

import ast
import json
import re
from typing import List, Optional, Tuple


class CommandParseMixin:
    """调用标记与参数解析"""

    def _loose_parse_kwargs(self, arg_str):
        """宽松解析 JSON 参数字符串（回退方案）"""
        key_pattern = r'"(\w+)"\s*:\s*'
        keys = list(re.finditer(key_pattern, arg_str))
        if not keys:
            return None
        result = {}
        for i, m in enumerate(keys):
            key = m.group(1)
            start = m.end()
            if i + 1 < len(keys):
                end = keys[i + 1].start()
            else:
                end = len(arg_str)
                while end > 0 and arg_str[end - 1] in ' \t\n\r}':
                    end -= 1
            val_str = arg_str[start:end].strip().rstrip(',').strip()

            # 布尔值
            if val_str == 'true':
                result[key] = True
                continue
            if val_str == 'false':
                result[key] = False
                continue
            if val_str == 'null':
                result[key] = None
                continue
            # 数字
            try:
                if '.' in val_str:
                    result[key] = float(val_str)
                else:
                    result[key] = int(val_str)
                continue
            except ValueError:
                pass
            # 字符串（去掉两端引号）
            if val_str.startswith('"') and val_str.endswith('"'):
                val_str = val_str[1:-1]
            # 还原转义序列
            QUOTE_PH = '\x00Q\x00'
            val_str = val_str.replace('\\"', QUOTE_PH)
            val_str = val_str.replace('\\\\', '\\')
            val_str = val_str.replace('\\n', '\n')
            val_str = val_str.replace('\\t', '\t')
            val_str = val_str.replace('\\r', '\r')
            val_str = val_str.replace(QUOTE_PH, '"')
            result[key] = val_str
        return result

    def _parse_tool_kwargs(self, arg_str):
        """安全解析工具参数字符串（JSON 或 Python dict）"""
        arg_str = arg_str.strip()
        if not arg_str:
            return {}

        # 预处理：将 JSON 字符串值内的原始换行替换为 \n 转义序列
        fixed = ""
        in_string = False
        escape = False
        for ch in arg_str:
            if escape:
                fixed += ch
                escape = False
                continue
            if ch == '\\':
                fixed += ch
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                fixed += ch
                continue
            if ch in '\n\r' and in_string:
                fixed += '\\n'
                continue
            fixed += ch

        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            try:
                return ast.literal_eval(arg_str)
            except (ValueError, SyntaxError):
                return self._loose_parse_kwargs(arg_str)

    def _extract_tool_calls(self, text) -> List[Tuple[str, str, str]]:
        """从文本中提取所有【调用：tool_name({...})】标记（支持嵌套括号，忽略字符串内的括号）"""
        calls = []
        i = 0
        while True:
            start = text.find('【调用：', i)
            if start == -1:
                break
            paren = text.find('(', start)
            if paren == -1:
                break
            tool_name = text[start + 4:paren].strip()
            depth = 1
            j = paren + 1
            in_string = False
            escape = False
            while j < len(text) and depth > 0:
                ch = text[j]
                if escape:
                    escape = False
                elif ch == '\\':
                    escape = True
                elif ch == '"':
                    in_string = not in_string
                elif not in_string:
                    if ch == '(':
                        depth += 1
                    elif ch == ')':
                        depth -= 1
                j += 1
            if depth != 0:
                i = paren + 1
                continue
            arg_str = text[paren + 1:j - 1]
            end = text.find('】', j - 1)
            if end == -1:
                break
            marker = text[start:end + 1]
            calls.append((tool_name, arg_str, marker))
            i = end + 1
        return calls
