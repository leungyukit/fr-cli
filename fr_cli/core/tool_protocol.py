"""
统一工具调用协议层 —— 单一真相源

背景（v2.8.7 改造）：
历史上 AI 工具调用有**两套独立实现**，行为不一致：

  路径 A（传统流式对话）``fr_cli/command/executor_parse.py``
      【调用：tool({...})】+ 三级参数回退（JSON → ast.literal_eval → 正则宽松解析）
  路径 B（ReAct / MasterAgent）``fr_cli/agent/master_loop.py``
      tool_call XML / 代码围栏 / 裸 JSON  + 【调用：tool({...})】**只走 json.loads**

后果（live 实测）：同一段 AI 文本，在传统路径能被宽松回退救回来，
在 ReAct 路径被**静默丢弃** —— 用户看到"AI 好像想调工具但什么都没发生"。

本模块把两套实现收敛为唯一入口：
  - ``parse_tool_args()``   —— 参数解析（三级回退，唯一实现）
  - ``extract_calls()``     —— 从文本提取工具调用（全格式，唯一实现）
  - ``ToolCall``            —— 统一结果结构

两条旧路径都改为委托本模块，行为从此一致。

本模块是**纯函数层**：不依赖 registry / state / 终端，可安全在 bot 与
子进程隔离环境中使用。
"""
from __future__ import annotations

import ast
import json
import re
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "ToolCall",
    "loose_parse_kwargs",
    "parse_tool_args",
    "normalize_tool_call",
    "extract_marker_calls",
    "extract_calls",
]


class ToolCall:
    """统一的工具调用结构。

    Attributes:
        tool:      工具名
        params:    参数字典
        marker:    原始标记文本（用于从 AI 回复中剔除该标记）
        raw_args:  原始参数字符串（调试用）
        fmt:       来源格式 —— marker / fence / json / xml
        error:     参数解析失败时的错误描述（成功为 None）
    """

    __slots__ = ("tool", "params", "marker", "raw_args", "fmt", "error")

    def __init__(self, tool: str, params: Optional[Dict[str, Any]] = None,
                 marker: str = "", raw_args: str = "", fmt: str = "",
                 error: Optional[str] = None):
        self.tool = tool
        self.params = params if params is not None else {}
        self.marker = marker
        self.raw_args = raw_args
        self.fmt = fmt
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {"tool": self.tool, "params": self.params}

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"ToolCall(tool={self.tool!r}, params={self.params!r}, fmt={self.fmt!r})"

    def __eq__(self, other) -> bool:
        if isinstance(other, ToolCall):
            return self.tool == other.tool and self.params == other.params
        if isinstance(other, dict):
            return self.to_dict() == other
        return NotImplemented


# ------------------------------------------------------------------
# 参数解析（三级回退）
# ------------------------------------------------------------------

# key 可以带引号("key" / 'key')，也可以不带(key) —— 模型两种都吐过
_KEY_RE = re.compile(r"""["']?(\w+)["']?\s*:\s*""")
_QUOTE_PLACEHOLDER = "\x00Q\x00"


def _coerce_scalar(val_str: str) -> Any:
    """把一个裸值文本猜成 Python 标量（bool / None / 数字 / 字符串）。"""
    if val_str in ("true", "True"):
        return True
    if val_str in ("false", "False"):
        return False
    if val_str in ("null", "None"):
        return None
    try:
        return float(val_str) if "." in val_str else int(val_str)
    except ValueError:
        pass
    # 字符串（去掉两端引号，支持单引号）
    if len(val_str) >= 2 and val_str[0] == val_str[-1] and val_str[0] in "\"'":
        val_str = val_str[1:-1]
    elif val_str.startswith('"') and val_str.endswith('"'):
        val_str = val_str[1:-1]
    # 还原转义序列
    val_str = val_str.replace('\\"', _QUOTE_PLACEHOLDER)
    val_str = val_str.replace("\\\\", "\\")
    val_str = val_str.replace("\\n", "\n")
    val_str = val_str.replace("\\t", "\t")
    val_str = val_str.replace("\\r", "\r")
    return val_str.replace(_QUOTE_PLACEHOLDER, '"')


def loose_parse_kwargs(arg_str: str) -> Optional[Dict[str, Any]]:
    """宽松解析参数字符串（最后一级回退）。

    按 ``key:`` 逐个切分值域，再按字面量猜类型（bool / null / 数字 / 字符串）。
    key 支持带引号与不带引号两种写法。只在严格 JSON 与 Python 字面量都失败时使用。
    """
    if not arg_str:
        return None
    keys = list(_KEY_RE.finditer(arg_str))
    if not keys:
        return None
    result: Dict[str, Any] = {}
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
        result[key] = _coerce_scalar(val_str)
    return result


def _escape_raw_newlines(arg_str: str) -> str:
    """把 JSON 字符串字面量内部的裸换行转义成 \\n。

    模型偶尔会在 JSON 字符串里直接换行，严格 JSON 会解析失败。
    """
    fixed = []
    in_string = False
    escape = False
    for ch in arg_str:
        if escape:
            fixed.append(ch)
            escape = False
            continue
        if ch == "\\":
            fixed.append(ch)
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            fixed.append(ch)
            continue
        if ch in "\n\r" and in_string:
            fixed.append("\\n")
            continue
        fixed.append(ch)
    return "".join(fixed)


def parse_tool_args(arg_str: str) -> Optional[Dict[str, Any]]:
    """解析工具参数字符串 —— 三级回退（唯一实现）。

    1. ``json.loads``（标准 JSON）
    2. ``ast.literal_eval``（Python dict 字面量，单引号 / True / False）
    3. ``loose_parse_kwargs``（正则逐 key 提取）

    Returns:
        参数字典；完全无法解析时返回 None。
    """
    if arg_str is None:
        return None
    arg_str = arg_str.strip()
    if not arg_str:
        return {}

    fixed = _escape_raw_newlines(arg_str)
    try:
        parsed = json.loads(fixed)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass

    try:
        parsed = ast.literal_eval(arg_str)
        if isinstance(parsed, dict):
            return parsed
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        pass

    return loose_parse_kwargs(arg_str)


# ------------------------------------------------------------------
# 归一化（兼容各种键位写法）
# ------------------------------------------------------------------

def normalize_tool_call(obj: Any) -> Optional[Dict[str, Any]]:
    """把一个 dict 归一化成 ``{"tool": name, "params": {...}}``。

    接受的键位（live 实测模型会混用）：
      ``{"tool", "params"}`` / ``{"tool", "arguments"}`` / ``{"name", "arguments"}``
      ``{"tool"}`` / ``{"function": {"name", "arguments"}}``（OpenAI 风格）

    Returns:
        归一化后的 dict；不是工具调用则 None。
    """
    if not isinstance(obj, dict):
        return None
    if "steps" in obj:
        # 计划 JSON（goal/steps/summary）不是工具调用
        return None
    fn = obj.get("function")
    if isinstance(fn, dict):
        obj = fn
    name = obj.get("tool") or obj.get("name") or obj.get("tool_name")
    if not isinstance(name, str) or not name.strip():
        return None
    params: Optional[Dict[str, Any]] = None
    for key in ("params", "arguments", "parameters"):
        val = obj.get(key)
        if isinstance(val, dict):
            params = val
            break
        if isinstance(val, str):
            # arguments 可能是 JSON 字符串
            parsed = parse_tool_args(val)
            if isinstance(parsed, dict):
                params = parsed
                break
    return {"tool": name.strip(), "params": params or {}}


# ------------------------------------------------------------------
# 文本提取
# ------------------------------------------------------------------

def extract_marker_calls(text: str) -> List[Tuple[str, str, str]]:
    """提取 ``【调用：tool_name({...})】`` 标记。

    支持嵌套括号、忽略字符串字面量内部的括号。

    Returns:
        ``[(tool_name, arg_str, 完整标记文本), ...]``
    """
    if not text:
        return []
    calls: List[Tuple[str, str, str]] = []
    i = 0
    while True:
        start = text.find("【调用：", i)
        if start == -1:
            break
        paren = text.find("(", start)
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
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = not in_string
            elif not in_string:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
            j += 1
        if depth != 0:
            # 括号未闭合 —— 跳到下一个可能的起点，避免死循环
            i = paren + 1
            continue
        arg_str = text[paren + 1:j - 1]
        end = text.find("】", j - 1)
        if end == -1:
            break
        calls.append((tool_name, arg_str, text[start:end + 1]))
        i = end + 1
    return calls


def _iter_json_objects(text: str):
    """按出现顺序 yield 每个字符串感知匹配的顶层 ``{...}`` 候选子串。

    复用 ``fr_cli.core.plan.generator._iter_json_objects``（保持行为一致），
    失败时降级为本地实现，避免循环 import。
    """
    try:
        from fr_cli.core.plan.generator import _iter_json_objects as _impl
        yield from _impl(text)
        return
    except Exception:
        pass
    if not text:
        return
    t = text.strip()
    n = len(t)
    for start in range(n):
        if t[start] != "{":
            continue
        depth = 0
        in_str = False
        esc = False
        for i in range(start, n):
            ch = t[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    yield t[start:i + 1]
                    break


_FENCE_RE = re.compile(r"```(?:\w+)?\s*\n(.*?)\n```", re.DOTALL)
_XML_TOOL_RE = re.compile(
    r"<\s*tool[^>]*>(.*?)<\s*/\s*tool[^>]*>", re.DOTALL | re.IGNORECASE
)


def extract_calls(text: str, dedup: bool = True) -> List[ToolCall]:
    """从 AI 回复文本中提取全部工具调用 —— 唯一实现（v2.8.7）。

    支持格式：

    ============================  ==========================================
    格式                          来源
    ============================  ==========================================
    ``【调用：tool({...})】``     marker（传统流式对话）
    ``【并行调用：...】``         由上层 ``remove_parallel_markers`` 处理
    ``【命令：/cmd args】``       由上层 ``process_ai_commands`` 处理
    `` ```tool {...} ``` ``      fence（代码围栏）
    ``{"tool": ..., "params": {}}``  json（裸 JSON / 对象数组）
    ``<tool_call>{...}</tool_call>``  xml（XML 标签）
    ============================  ==========================================

    参数一律走 :func:`parse_tool_args` 三级回退；解析失败时返回带 ``error``
    的 ToolCall（而不是静默丢弃），让上层有机会把错误反馈给模型自纠正。

    Args:
        text:    AI 回复原文
        dedup:   是否按 (tool, params) 去重

    Returns:
        ``[ToolCall, ...]``
    """
    if not text:
        return []

    calls: List[ToolCall] = []
    seen = set()

    def _add(call: ToolCall) -> None:
        if not call.tool:
            return
        if dedup:
            try:
                key = (call.tool, json.dumps(call.params, sort_keys=True, ensure_ascii=False))
            except (TypeError, ValueError):
                key = (call.tool, str(call.params))
            if key in seen:
                return
            seen.add(key)
        calls.append(call)

    # ---- 格式 1：【调用：tool({...})】 ----
    for tool_name, arg_str, marker in extract_marker_calls(text):
        params = parse_tool_args(arg_str)
        if params is None:
            _add(ToolCall(tool_name, {}, marker=marker, raw_args=arg_str,
                          fmt="marker", error=f"参数解析失败: {arg_str[:120]}"))
        else:
            _add(ToolCall(tool_name, params, marker=marker, raw_args=arg_str, fmt="marker"))

    # ---- 格式 2：代码围栏 / 裸 JSON / XML 标签 ----
    def _scan_json_obj(obj: Any, fmt: str, marker: str = "") -> None:
        norm = normalize_tool_call(obj)
        if norm:
            _add(ToolCall(norm["tool"], norm["params"], marker=marker, fmt=fmt))
            return
        if isinstance(obj, list):
            for it in obj:
                _scan_json_obj(it, fmt, marker)
            return
        # 参数可能是字符串形式的 JSON
        if isinstance(obj, dict) and isinstance(obj.get("arguments"), str):
            parsed = parse_tool_args(obj["arguments"])
            name = obj.get("tool") or obj.get("name") or obj.get("tool_name")
            if isinstance(name, str) and name.strip() and isinstance(parsed, dict):
                _add(ToolCall(name.strip(), parsed, marker=marker, fmt=fmt))

    def _scan_chunk(chunk: str, fmt: str) -> None:
        stripped = chunk.strip()
        # 整段裸 JSON（对象或对象数组）
        try:
            obj = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            obj = None
        if obj is not None:
            _scan_json_obj(obj, fmt)
        # 括号匹配兜底（挖 XML 标签 / 前后散文里的 JSON）
        for cand in _iter_json_objects(chunk):
            try:
                _scan_json_obj(json.loads(cand), fmt, marker=cand)
            except (json.JSONDecodeError, ValueError):
                continue

    # 代码围栏
    for m in _FENCE_RE.finditer(text):
        inner = m.group(1).strip()
        if not inner.startswith(("{", "[")):
            continue
        try:
            _scan_json_obj(json.loads(inner), "fence", marker=m.group(0))
            continue
        except (json.JSONDecodeError, ValueError):
            pass
        _scan_chunk(inner, "fence")

    # XML 工具标签内层
    for m in _XML_TOOL_RE.finditer(text):
        _scan_chunk(m.group(1), "xml")

    # 全文兜底（裸 JSON / 散落 JSON）
    _scan_chunk(text, "json")

    return calls
