"""
工具 Schema 导出与参数类型校验 —— Harness 可扩展性内核的一部分

提供两块能力:

1. **JSON Schema 导出**
   把注册表里的工具定义转成 OpenAI 风格 function schema, 便于外部
   harness / 插件 / MCP 客户端消费:
   ```python
   {"type": "function", "function": {"name": ..., "description": ...,
    "parameters": {"type": "object", "properties": {...}, "required": [...]}}}
   ```

2. **参数类型校验**
   在 dispatch 之前拦住"类型不对"的参数, 给出可读错误信息; 对可以安全
   转换的值做**宽容转换**(如 ``"123"`` → ``123``、``"true"`` → ``True``),
   转换失败才报错。

类型映射约定:
- ``type_name()``  返回 Python 侧类型名(str/int/float/bool/list/dict),
  与注册表 ``get_available_tools()`` 的展示保持一致。
- ``schema_type()`` 返回 JSON Schema 侧类型名
  (string/integer/number/boolean/array/object)。

注意: Python 里 ``bool`` 是 ``int`` 的子类(``isinstance(True, int)`` 为 True),
因此所有类型判断都**先判 bool 再判 int**。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "type_name",
    "schema_type",
    "tool_schema",
    "export_schemas",
    "export_schema_text",
    "validate_params",
]


# Python 类型 → 展示用类型名(与注册表 / AI 提示词一致)
_TYPE_NAMES: Dict[type, str] = {
    str: "str",
    int: "int",
    float: "float",
    bool: "bool",
    list: "list",
    dict: "dict",
}

# Python 类型 → JSON Schema type
_SCHEMA_TYPES: Dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}

# 字符串 → bool 的合法字面量
_TRUE_LITERALS = ("true", "1", "yes", "on")
_FALSE_LITERALS = ("false", "0", "no", "off")


# ------------------------------------------------------------------
# 类型名映射
# ------------------------------------------------------------------
def type_name(ptype: Any) -> str:
    """把 Python 类型映射成类型名: str / int / float / bool / list / dict。

    Args:
        ptype: Python 类型(或 None / 非类型对象)

    Returns:
        类型名字符串; 无法识别时退化为 ``__name__`` 或 ``str(ptype)``。
    """
    if ptype is None:
        return "any"
    if isinstance(ptype, type):
        # 注意: bool 是 int 的子类, 但两者在字典里是独立 key, 查表即可正确区分
        if ptype in _TYPE_NAMES:
            return _TYPE_NAMES[ptype]
        return ptype.__name__
    return str(ptype)


def schema_type(ptype: Any) -> str:
    """把 Python 类型映射成 JSON Schema type。

    string / integer / number / boolean / array / object;
    未识别的类型统一按 "string" 处理。
    """
    if ptype is None:
        return "string"
    if isinstance(ptype, type):
        # bool 必须先判 —— bool 是 int 的子类
        if ptype is bool:
            return "boolean"
        if ptype in _SCHEMA_TYPES:
            return _SCHEMA_TYPES[ptype]
        return "string"
    return "string"


# ------------------------------------------------------------------
# Schema 导出
# ------------------------------------------------------------------
def tool_schema(tool_info: Dict[str, Any]) -> Dict[str, Any]:
    """从注册表里的 tool_info 生成 OpenAI 风格 function schema。

    Args:
        tool_info: 注册表中的工具元数据(含 name / description / params)

    Returns:
        ``{"type": "function", "function": {...}}`` 结构的 dict。
        注册表里 ``params`` 表示必填参数, 因此全部 key 都进 ``required``。
    """
    info = tool_info or {}
    params = info.get("params") or {}

    properties: Dict[str, Any] = {}
    required: List[str] = []
    for pname, ptype in params.items():
        properties[pname] = {"type": schema_type(ptype)}
        required.append(pname)

    return {
        "type": "function",
        "function": {
            "name": info.get("name", ""),
            "description": info.get("description", ""),
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


def _resolve_registry(registry: Any = None) -> Any:
    """取注册表实例(默认用全局注册表)。延迟导入避免循环依赖。"""
    if registry is not None:
        return registry
    from fr_cli.command.registry import get_registry
    return get_registry()


def export_schemas(registry: Any = None) -> List[Dict[str, Any]]:
    """遍历注册表所有工具, 导出 function schema 列表。

    Args:
        registry: 可选的注册表实例, 默认使用全局 ``get_registry()``
    """
    reg = _resolve_registry(registry)
    return [tool_schema(t) for t in reg.get_tools()]


def export_schema_text(registry: Any = None) -> str:
    """把全部工具导出成可注入 system prompt 的文本。

    每个工具一段, 含工具名 / 说明 / 参数名与类型, 比
    ``fr_cli.core.chat.pipeline_intent._build_tools_info`` 更结构化。
    """
    reg = _resolve_registry(registry)
    lines = ["当前可用的工具列表(格式: 工具名: 说明 | 参数: 参数名(类型)):"]
    for tool in reg.get_tools():
        params = tool.get("params") or {}
        if params:
            params_desc = ", ".join(f"{k}({type_name(v)})" for k, v in params.items())
        else:
            params_desc = "无参数"
        lines.append(
            f"- {tool.get('name', '')}: {tool.get('description', '')} | 参数: {params_desc}"
        )
    return "\n".join(lines)


# ------------------------------------------------------------------
# 参数类型校验
# ------------------------------------------------------------------
def _json_convert(value: str, expected: type) -> Optional[Any]:
    """尝试把 JSON 字符串解析成期望的容器类型, 失败返回 None。"""
    text = value.strip()
    if not text or text[0] not in "[{":
        return None
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return None
    if isinstance(expected, type) and isinstance(parsed, expected):
        return parsed
    return None


def _coerce_value(param: str, ptype: Any, value: Any) -> Tuple[Optional[str], Any]:
    """校验单个参数的类型, 必要时做宽容转换。

    Returns:
        ``(错误信息, 转换后的值)``; 错误信息为 None 表示通过。
    """
    if ptype is None:
        return None, value

    expected = type_name(ptype)

    if not isinstance(ptype, type):
        # 非类型对象(例如字符串描述)不做校验, 直接放行
        return None, value

    # ---- bool: 必须最先判断(bool 是 int 的子类) ----
    if ptype is bool:
        if isinstance(value, bool):
            return None, value
        if isinstance(value, str):
            low = value.strip().lower()
            if low in _TRUE_LITERALS:
                return None, True
            if low in _FALSE_LITERALS:
                return None, False
        elif isinstance(value, int) and value in (0, 1):
            return None, bool(value)
        return (
            f"Invalid type for parameter '{param}': expected bool, got {type(value).__name__}",
            value,
        )

    # ---- int ----
    if ptype is int:
        if isinstance(value, bool):
            # bool 是 int 的子类, 但显式拒绝(True 不等于 1)
            return (
                f"Invalid type for parameter '{param}': expected int, got bool",
                value,
            )
        if isinstance(value, int):
            return None, value
        if isinstance(value, float) and value.is_integer():
            return None, int(value)
        if isinstance(value, str):
            try:
                return None, int(value.strip())
            except (ValueError, TypeError):
                pass
        return (
            f"Invalid type for parameter '{param}': expected int, got {type(value).__name__}",
            value,
        )

    # ---- float ----
    if ptype is float:
        if isinstance(value, bool):
            return (
                f"Invalid type for parameter '{param}': expected float, got bool",
                value,
            )
        if isinstance(value, float):
            return None, value
        if isinstance(value, int):
            return None, float(value)
        if isinstance(value, str):
            try:
                return None, float(value.strip())
            except (ValueError, TypeError):
                pass
        return (
            f"Invalid type for parameter '{param}': expected float, got {type(value).__name__}",
            value,
        )

    # ---- str ----
    if ptype is str:
        if isinstance(value, str):
            return None, value
        # 宽容转换: 数字/布尔转字符串(历史路径允许 int 形态的 schedule 等)
        if isinstance(value, bool):
            return None, "true" if value else "false"
        if isinstance(value, (int, float)):
            return None, str(value)
        return (
            f"Invalid type for parameter '{param}': expected str, got {type(value).__name__}",
            value,
        )

    # ---- list ----
    if ptype is list:
        if isinstance(value, list):
            return None, value
        if isinstance(value, tuple):
            return None, list(value)
        if isinstance(value, str):
            converted = _json_convert(value, list)
            if converted is not None:
                return None, converted
        return (
            f"Invalid type for parameter '{param}': expected list, got {type(value).__name__}",
            value,
        )

    # ---- dict ----
    if ptype is dict:
        if isinstance(value, dict):
            return None, value
        if isinstance(value, str):
            converted = _json_convert(value, dict)
            if converted is not None:
                return None, converted
        return (
            f"Invalid type for parameter '{param}': expected dict, got {type(value).__name__}",
            value,
        )

    # ---- 其他自定义类型: 只做 isinstance 判断, 不做转换 ----
    if isinstance(value, ptype):
        return None, value
    return (
        f"Invalid type for parameter '{param}': expected {expected}, got {type(value).__name__}",
        value,
    )


def validate_params(
    tool_info: Dict[str, Any],
    kwargs: Dict[str, Any],
    strict_containers: bool = True,
) -> Optional[str]:
    """校验工具参数(存在性 + 类型)。

    规则:
    - 必填参数缺失 → 返回 ``"Missing required parameter: xxx"``
    - 类型不匹配 → 先尝试宽容转换(``"123"`` → ``123``、``"true"`` → ``True``),
      转换成功就地写回 kwargs; 转换失败才返回错误信息
    - 参数类型未指定(None)或 params 为空 → 直接通过
    - 值为 None 时跳过类型校验(沿用旧行为, 交给 handler 处理)

    Args:
        tool_info: 注册表里的工具元数据(含 params)
        kwargs: 待校验参数(可能被就地改写为转换后的值)
        strict_containers: 是否严格校验 list / dict 类型。
            默认 True(纯函数语义: 类型不符即报错);
            注册表调度路径传 False, 以兼容历史 ``/cmd`` 通道把
            list/dict 参数当字符串传递的既有行为。

    Returns:
        None 表示通过; str 表示错误信息。
    """
    params = (tool_info or {}).get("params") or {}
    if not params:
        return None

    for param, ptype in params.items():
        if param not in kwargs:
            return f"Missing required parameter: {param}"

        value = kwargs[param]
        if value is None:
            # None 视为"未提供", 保持旧行为(不拦, 交给 handler)
            continue

        if not strict_containers and ptype in (list, dict):
            # 宽松模式: 容器类型不做拦截, 仅尝试 JSON 转换
            converted = _json_convert(value, ptype) if isinstance(value, str) else None
            if converted is not None:
                kwargs[param] = converted
            continue

        err, converted = _coerce_value(param, ptype, value)
        if err:
            return err
        if converted is not value:
            kwargs[param] = converted

    return None
