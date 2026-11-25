"""
原生 function calling —— 工具调用的协议层

v2.8.7 新增（P0-3）。

背景
----
v2.8.6 及以前，fr-cli 的工具契约**完全靠文本标记**：

    【调用：tool_name({"参数": "值"})】

模型必须"记住"这个约定并精确复述出来。解析层已经做了三级容错
（``fr_cli/core/tool_protocol.py``），但**模型无法自纠正**：
参数名拼错、JSON 写坏，模型自己看不到错误，只能把错误文本再喂回去碰运气。

OpenAI 兼容协议原生支持 function calling：

    请求： tools=[{"type":"function","function":{"name","description","parameters"}}]
    响应： delta.tool_calls = [{"index":0,"id":"call_x","function":{"name","arguments"}}]

参数由 provider 用 JSON Schema 校验，模型拿到的是**结构化**的参数，
出错概率大幅下降；且工具返回结果可以按协议回填（``role="tool"``），
模型能基于真实结果继续推理。

本模块提供
----------
* :class:`ToolCall` —— 一次原生工具调用的结构化表示
* :class:`ToolCallAccumulator` —— 累积流式返回的 tool_call 分片
* :func:`build_tools_payload` —— 从注册表生成 OpenAI 格式的 tools 数组
* :func:`client_supports_tools` —— 客户端是否支持原生 tools

**降级是硬要求**：不是所有 provider / 模型都支持 tools。
不支持时必须自动退回文本标记路径 —— 两条路径共存，互不影响。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__all__ = [
    "ToolCall",
    "ToolCallAccumulator",
    "build_tools_payload",
    "client_supports_tools",
    "tool_calls_to_messages",
]


@dataclass
class ToolCall:
    """一次原生工具调用。

    Attributes:
        id: provider 给出的调用 id（回填 tool 结果时要原样带回）
        name: 工具名
        arguments: 已解析的参数字典
        raw_arguments: 原始 JSON 字符串（解析失败时用于报错）
        error: 参数解析错误信息（None 表示正常）
    """

    id: str
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    raw_arguments: str = ""
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        """参数是否解析成功。"""
        return self.error is None and bool(self.name)


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """兼容对象属性与 dict 两种形态（不同 SDK 的返回结构不一致）。"""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class ToolCallAccumulator:
    """累积流式返回的 tool_call 分片。

    OpenAI 协议下，一个工具调用的参数 JSON 是**分片下发**的：
    第一个分片带 ``id`` 与 ``name``，后续分片只带 ``arguments`` 的片段。
    本类按 ``index`` 归并，最终产出完整的 :class:`ToolCall` 列表。
    """

    def __init__(self) -> None:
        self._slots: Dict[int, Dict[str, Any]] = {}

    def add_delta(self, deltas: Any) -> None:
        """吃进一个 chunk 的 tool_calls 分片。"""
        if not deltas:
            return
        for delta in deltas:
            try:
                index = _get(delta, "index", 0)
                index = int(index) if index is not None else 0
            except (TypeError, ValueError):
                index = 0
            slot = self._slots.setdefault(index, {"id": "", "name": "", "arguments": ""})
            call_id = _get(delta, "id")
            if call_id:
                slot["id"] = str(call_id)
            fn = _get(delta, "function")
            if fn is not None:
                name = _get(fn, "name")
                if name:
                    slot["name"] = str(name)
                args = _get(fn, "arguments")
                if args:
                    slot["arguments"] += args if isinstance(args, str) else str(args)

    def finish(self) -> List[ToolCall]:
        """产出完整的工具调用列表（按 index 升序）。"""
        out: List[ToolCall] = []
        for index in sorted(self._slots):
            slot = self._slots[index]
            raw = slot["arguments"] or ""
            args: Dict[str, Any] = {}
            error: Optional[str] = None
            if raw.strip():
                try:
                    parsed = json.loads(raw)
                except Exception as e:
                    parsed = None
                    error = f"工具参数 JSON 解析失败: {e}"
                if error is None:
                    if isinstance(parsed, dict):
                        args = parsed
                    else:
                        error = f"工具参数不是 JSON 对象: {raw[:120]}"
            out.append(ToolCall(
                id=slot["id"] or f"call_{index}",
                name=slot["name"],
                arguments=args,
                raw_arguments=raw,
                error=error,
            ))
        return out

    def __len__(self) -> int:
        return len(self._slots)


def build_tools_payload(registry: Any = None, limit: int = 0) -> List[Dict[str, Any]]:
    """从工具注册表生成 OpenAI 格式的 tools 数组。

    Args:
        registry: 注册表实例，None → 全局注册表
        limit: 最多取多少个工具；0 → 不限

    Returns:
        ``[{"type": "function", "function": {...}}, ...]``
    """
    from fr_cli.command.schema import export_schemas
    try:
        schemas = export_schemas(registry)
    except Exception:
        return []
    # 过滤掉没有名字的脏数据
    schemas = [s for s in schemas if s.get("function", {}).get("name")]
    if limit and limit > 0:
        schemas = schemas[:limit]
    return schemas


def client_supports_tools(client: Any) -> bool:
    """客户端是否支持原生 function calling。

    通过类属性 ``SUPPORTS_TOOLS`` 声明 —— 不支持时上层自动退回文本标记路径。
    """
    return bool(getattr(client, "SUPPORTS_TOOLS", False))


def tool_calls_to_messages(calls: List[ToolCall], results: List[str]) -> List[Dict[str, Any]]:
    """把工具调用与执行结果转成 OpenAI 协议的消息，供第二轮回填。

    Args:
        calls: 工具调用列表
        results: 与 calls 一一对应的结果字符串

    Returns:
        消息列表 —— 先一条 assistant(tool_calls)，再逐条 role="tool"
    """
    messages: List[Dict[str, Any]] = []
    if not calls:
        return messages
    messages.append({
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": c.id,
                "type": "function",
                "function": {"name": c.name, "arguments": c.raw_arguments or "{}"},
            }
            for c in calls
        ],
    })
    for idx, call in enumerate(calls):
        content = results[idx] if idx < len(results) else ""
        messages.append({
            "role": "tool",
            "tool_call_id": call.id,
            "name": call.name,
            "content": content if isinstance(content, str) else str(content),
        })
    return messages
