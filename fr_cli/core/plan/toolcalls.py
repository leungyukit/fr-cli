"""工具调用容错提取: 从 LLM 回复里挖出 {"tool", "params"}。

live 实测: step-5-preview 实际吐的是 tool_call XML 标签包裹的 JSON,
或裸 JSON, 而 master_loop 旧解析只认 ```tool 围栏 + 【调用：】,
于是工具调用被当成"最终答案"、ReAct 循环一步退出、工具从未
执行(静默失败)。逐层兜底:
  1. 整段文本就是 JSON(对象或对象数组)
  2. 任意代码围栏(```tool / ```json / 裸 ```)里的 JSON
  3. 括号匹配兜底: 挖 tool XML 标签 / 前后散文里的 JSON
  4. 显式扫 tool_call XML 标签内层
"""
import json
import re

from fr_cli.core.plan.generator import _iter_json_objects


def _normalize_tool_call(obj):
    """规范化成 {"tool": name, "params": dict}; 不是工具调用返回 None。

    接受的键位(live 实测 step-5-preview 会混用):
      {"tool","params"} / {"tool","arguments"} / {"name","arguments"}
      {"tool"} / {"function":{"name","arguments"}} (OpenAI 风格)
    """
    if not isinstance(obj, dict):
        return None
    if "steps" in obj:
        # 计划 JSON(goal/steps/summary)不是工具调用
        return None
    fn = obj.get("function")
    if isinstance(fn, dict):
        obj = fn
    name = obj.get("tool") or obj.get("name") or obj.get("tool_name")
    if not isinstance(name, str) or not name.strip():
        return None
    params = None
    for key in ("params", "arguments", "parameters"):
        val = obj.get(key)
        if isinstance(val, dict):
            params = val
            break
    return {"tool": name.strip(), "params": params or {}}


def extract_tool_calls(text: str) -> list:
    """容错提取工具调用, 返回去重后的 [{"tool", "params"}, ...]。"""
    if not text:
        return []
    calls = []
    seen = set()

    def _add(obj):
        norm = _normalize_tool_call(obj)
        if not norm:
            return
        key = (norm["tool"], json.dumps(norm["params"], sort_keys=True, ensure_ascii=False))
        if key in seen:
            return
        seen.add(key)
        calls.append(norm)

    def _emit(obj):
        if isinstance(obj, dict):
            _add(obj)
        elif isinstance(obj, list):
            for it in obj:
                _add(it)

    def _scan(chunk):
        # 1) 整段裸 JSON(对象或对象数组)
        try:
            obj = json.loads(chunk.strip())
        except Exception:
            obj = None
        if obj is not None:
            _emit(obj)
        # 2) 代码围栏内的 JSON(```tool / ```json / 裸 ```)
        for m in re.finditer(r"```(?:\w+)?\s*\n(.*?)\n```", chunk, re.DOTALL):
            inner = m.group(1).strip()
            if not inner.startswith(("{", "[")):
                continue
            try:
                _emit(json.loads(inner))
            except Exception:
                continue
        # 3) 括号匹配兜底(挖 <tool> XML / <tool_call> / 前后散文里的 JSON)
        for cand in _iter_json_objects(chunk):
            try:
                _emit(json.loads(cand))
            except Exception:
                continue

    _scan(text)
    # 4) 显式扫 XML 工具标签内层(双保险, 按出现先后)
    for m in re.finditer(r"<\s*tool[^>]*>(.*?)<\s*/\s*tool[^>]*>", text, re.DOTALL | re.IGNORECASE):
        _scan(m.group(1))
    return calls
