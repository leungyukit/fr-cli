"""
Agent 生成器 —— 分身铸造炉
利用大模型能力，根据用户需求自动生成完整的 Agent（人设、技能、代码）
"""
import sys
from fr_cli.core.stream import stream_cnt


GENERATION_PROMPT_ZH = """你是 Agent 架构师。请根据以下需求，为一个新的 AI Agent 分身设计完整的设定和代码。

Agent 名称: {name}
需求描述: {description}

请严格按照以下格式输出（保持三个标记之间的顺序）：

---PERSONA_START---
（在这里写人设设定，用 Markdown 格式。包括：角色定位、性格特点、行为准则、语气风格）
---PERSONA_END---

---SKILLS_START---
（在这里写可用技能，用 Markdown 格式。列出 Agent 可以使用的工具和能力，每项技能包含名称、描述和调用方式）
---SKILLS_END---

---CODE_START---
```python
（在这里写完整的 Python 代码）
```
---CODE_END---

对 Python 代码的要求：
1. 必须包含 `def run(context, **kwargs):` 作为唯一入口函数
2. `context` 是一个字典，包含以下键：
   - 'persona': str — 人设文本
   - 'memory': str — 记忆文本
   - 'skills': str — 技能文本
   - 'client': ZhipuAI 实例
   - 'model': str — 模型名称
   - 'lang': str — 语言代码（'zh' 或 'en'）
   - 'executor': CommandExecutor 实例（可使用 invoke_tool/execute 调用工具）
   - 'state': AppState 实例（可访问 vfs、cfg 等子系统）
3. `kwargs` 包含用户调用时传入的参数
4. 函数返回 str 类型的执行结果
5. 代码要健壮，有异常处理
6. 使用中文注释
7. 充分利用 context 中的资源完成用户需求
8. 如果需要调用 AI，使用 context['client'].chat.completions.create()
9. 如果需要操作文件，使用 context['state'].vfs
10. 如果需要调用工具，使用 context['executor'].invoke_tool() 或 context['executor'].execute()

请确保输出中包含完整的三个部分（PERSONA、SKILLS、CODE），缺一不可。
"""


def _extract_section(text: str, start_marker: str, end_marker: str) -> str:
    """从 AI 回复中提取标记之间的内容"""
    s = text.find(start_marker)
    e = text.find(end_marker)
    if s == -1 or e == -1 or e <= s:
        return ""
    return text[s + len(start_marker):e].strip()


def _clean_code_block(code: str) -> str:
    """去除代码块标记 ```python ... ```"""
    code = code.strip()
    if code.startswith("```python"):
        code = code[len("```python"):].strip()
    elif code.startswith("```"):
        code = code[len("```"):].strip()
    if code.endswith("```"):
        code = code[:-3].strip()
    return code


def generate_agent(client, model, name: str, description: str, lang: str = "zh") -> dict:
    """
    调用大模型生成完整的 Agent。
    返回 {"persona": str, "skills": str, "code": str, "raw": str}
    """
    prompt = GENERATION_PROMPT_ZH.format(name=name, description=description)
    messages = [{"role": "user", "content": prompt}]

    sys.stdout.write("🧙 正在铸造分身... ")
    sys.stdout.flush()
    raw, _, _ = stream_cnt(client, model, messages, lang, custom_prefix="", max_tokens=4096)

    persona = _extract_section(raw, "---PERSONA_START---", "---PERSONA_END---")
    skills = _extract_section(raw, "---SKILLS_START---", "---SKILLS_END---")
    code = _extract_section(raw, "---CODE_START---", "---CODE_END---")
    code = _clean_code_block(code)

    # 如果没有提取到代码，尝试从原始回复中直接找代码块
    if not code and "```python" in raw:
        s = raw.find("```python")
        e = raw.find("```", s + 1)
        if e > s:
            code = _clean_code_block(raw[s:e + 3])

    return {
        "persona": persona,
        "skills": skills,
        "code": code,
        "raw": raw,
    }
