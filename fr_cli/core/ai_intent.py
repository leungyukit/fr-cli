"""
AI 命令参数可视化 —— 让 AI 输出的命令更结构化、更易调试

现状问题:
- AI 输出【调用：tool({"参数": "值"})】时,参数是黑盒 JSON
- 用户看不到为什么 AI 选了这些参数
- 出错时很难定位

增强:
- 在调用前,显示"AI 想调用 X,参数是 Y,基于依据 Z"
- 让 AI 在 system prompt 中知道可以输出【理由：...】解释调用
- 解析【理由：...】标记并展示

新格式(AI 可以选):
```
【调用：search_web({"query": "Python 异步"})】
【理由：用户问 Python 异步教程,首选搜索官方文档和教程网站】
```

或者用"块标记":
```
[AI_INTENT]
tool: search_web
params: {query: "Python 异步"}
reason: 用户问异步教程,先搜索官方文档
[/AI_INTENT]
```
"""
import re
from typing import Dict, Any, Optional, Tuple


INTENT_BLOCK_PATTERN = re.compile(
    r"\[AI_INTENT\](.*?)\[/AI_INTENT\]", re.DOTALL
)
REASON_MARKER_PATTERN = re.compile(r"【理由：(.*?)】", re.DOTALL)


def parse_intent_block(text: str) -> Optional[Dict[str, Any]]:
    """解析 [AI_INTENT]...[/AI_INTENT] 块

    Returns:
        {"tool": str, "params": dict, "reason": str} 或 None
    """
    m = INTENT_BLOCK_PATTERN.search(text)
    if not m:
        return None

    block = m.group(1).strip()
    result = {}

    for line in block.splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        if key == "tool":
            result["tool"] = value
        elif key == "params":
            # 尝试解析 JSON / Python dict
            try:
                import json
                result["params"] = json.loads(value)
            except Exception:
                try:
                    import ast
                    result["params"] = ast.literal_eval(value)
                except Exception:
                    # 把整个 value 当成字符串参数
                    result["params"] = {"raw": value}
        elif key == "reason":
            result["reason"] = value

    return result if result else None


def parse_reason_marker(text: str) -> Optional[str]:
    """提取【理由：...】标记"""
    m = REASON_MARKER_PATTERN.search(text)
    return m.group(1).strip() if m else None


def format_intent_preview(intent: Dict[str, Any], use_color: bool = True) -> str:
    """格式化 AI 意图预览

    Args:
        intent: {"tool", "params", "reason"}
        use_color: ANSI 颜色

    Returns:
        格式化的预览文本
    """
    try:
        from fr_cli.ui.ui import CYAN, YELLOW, DIM, RESET, GREEN
    except ImportError:
        CYAN = YELLOW = DIM = RESET = GREEN = ""

    lines = []
    if use_color:
        lines.append(f"{CYAN}🤖 AI 意图{RESET}")

    if "tool" in intent:
        lines.append(f"  {YELLOW}工具:{RESET} {intent['tool']}")
    if "params" in intent:
        params_str = str(intent["params"])
        if len(params_str) > 200:
            params_str = params_str[:197] + "..."
        lines.append(f"  {YELLOW}参数:{RESET} {DIM}{params_str}{RESET}")
    if "reason" in intent:
        lines.append(f"  {GREEN}理由:{RESET} {intent['reason']}")

    return "\n".join(lines)


def enhance_ai_response_with_intent(ai_response: str, use_color: bool = True) -> Tuple[str, Optional[str]]:
    """从 AI 回复中提取意图,在执行前展示

    Args:
        ai_response: AI 原始回复
        use_color: ANSI 颜色

    Returns:
        (cleaned_response, intent_preview or None)
    """
    # 1. 尝试解析 [AI_INTENT] 块
    intent_block = parse_intent_block(ai_response)
    if intent_block:
        preview = format_intent_preview(intent_block, use_color=use_color)
        # 从 response 移除块
        cleaned = INTENT_BLOCK_PATTERN.sub("", ai_response).strip()
        return cleaned, preview

    # 2. 尝试解析【理由：...】标记
    reason = parse_reason_marker(ai_response)
    if reason:
        preview = f"{CYAN if use_color else ''}🤖 AI 理由:{RESET if use_color else ''} {reason}"
        cleaned = REASON_MARKER_PATTERN.sub("", ai_response).strip()
        return cleaned, preview

    # 没有意图信息
    return ai_response, None


def extract_ai_intent_hints() -> str:
    """生成 system prompt 提示,告诉 AI 可以用【理由：...】或 [AI_INTENT]"""
    return """
AI 意图声明(可选):
当你准备调用工具时,可以在调用标记前声明意图:

格式 1(简洁):
【理由：用户问 Python 异步教程,先搜索官方文档】
【调用：search_web({"query": "Python 异步教程"})】

格式 2(详细):
[AI_INTENT]
tool: search_web
params: {"query": "Python 异步教程"}
reason: 用户问异步教程,先搜索官方文档
[/AI_INTENT]
【调用：search_web({"query": "Python 异步教程"})】

效果:用户会在执行前看到"AI 准备做这件事,因为这个理由"。
用法场景:复杂任务、需要用户审批的关键操作、不确定的决策。
"""


# Color 常量 fallback(在 enhance 函数里 import ui 会重复,放外部)
try:
    from fr_cli.ui.ui import CYAN, YELLOW, DIM, RESET, GREEN
except ImportError:
    CYAN = YELLOW = DIM = RESET = GREEN = ""
