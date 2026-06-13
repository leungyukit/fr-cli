"""
Agent 生成器 —— 分身创建炉
利用大模型能力，根据用户需求自动生成完整的 Agent（人设、技能、代码、工作流）
"""
import sys
from fr_cli.core.stream import stream_cnt


GENERATION_PROMPT_ZH = '''你是 Agent 架构师。请根据以下需求，为一个新的 AI Agent 分身设计完整的设定和代码。

Agent 名称: {name}
需求描述: {description}

请严格按照以下格式输出（保持四个标记之间的顺序）：

---PERSONA_START---
# {name}

（在这里写人设设定，用 Markdown 格式。包括：角色定位、性格特点、行为准则、语气风格）
---PERSONA_END---

---SKILLS_START---
## 技能

（在这里写可用技能，用 Markdown 格式。列出 Agent 可以使用的工具和能力，每项技能包含名称、描述和调用方式。同时给出 @name 调用示例）
---SKILLS_END---

---CODE_START---
```python
# Agent: {name}
# 需求: {description}

def run(context, **kwargs):
    """
    Agent 入口函数。

    参数:
      context: dict，包含以下键：
        - 'persona': str — 人设文本
        - 'memory': str — 记忆文本
        - 'skills': str — 技能文本
        - 'client': LLM 客户端实例（已根据 Agent 专属配置或全局默认初始化）
        - 'provider': str — 当前使用的提供商 ID
        - 'model': str — 模型名称
        - 'lang': str — 语言代码（'zh' 或 'en'）
        - 'executor': CommandExecutor 实例（可使用 invoke_tool/execute 调用工具）
        - 'state': AppState 实例（可访问 vfs、cfg 等子系统）
        - 'agent_name': str — 当前 Agent 名称
      kwargs: 用户调用时传入的参数，常见键包括 'user_input'

    返回: str 类型的执行结果
    """
    user_input = kwargs.get("user_input", "")
    # TODO: 在此实现你的逻辑
    # 示例：让 LLM 基于人设和用户需求生成回答
    # messages = [
    #     {"role": "system", "content": context["persona"]},
    #     {"role": "user", "content": user_input},
    # ]
    # resp = context["client"].chat.completions.create(model=context["model"], messages=messages)
    # return resp.choices[0].message.content
    return f"[{context['agent_name']}] 收到任务: {{user_input}}"
```
---CODE_END---

---WORKFLOW_START---
# {name} 工作流

## 步骤1：理解需求
- **action**: ai_generate
- **params**:
  - prompt: "基于以下需求给出分析：{{user_input}}"

## 步骤2：执行核心逻辑
- **action**: invoke_tool
- **params**:
  - tool: "agent_call"
  - name: "{name}"
  - user_input: "{{user_input}}"
---WORKFLOW_END---

对 Python 代码的要求：
1. 必须包含 `def run(context, **kwargs):` 作为唯一入口函数
2. `context` 是一个字典，包含 'persona'、'memory'、'skills'、'client'、'provider'、'model'、'lang'、'executor'、'state'、'agent_name' 等键
3. `kwargs` 包含用户调用时传入的参数，常见键为 'user_input'
4. 函数返回 str 类型的执行结果
5. 代码要健壮，有异常处理
6. 使用中文注释
7. 充分利用 context 中的资源完成用户需求
8. 如果需要调用 AI，使用 context['client'].chat.completions.create()
9. 如果需要操作文件，使用 context['state'].vfs
10. 如果需要调用工具，使用 context['executor'].invoke_tool() 或 context['executor'].execute()

请确保输出中包含完整的四个部分（PERSONA、SKILLS、CODE、WORKFLOW），缺一不可。
'''


DEFAULT_AGENT_CODE_TEMPLATE = '''# Agent: {name}
# 由 /agent_create 自动生成

def run(context, **kwargs):
    """
    Agent 入口函数。
    默认实现：将 user_input 交给当前模型，结合人设生成回答。
    """
    import traceback

    user_input = kwargs.get("user_input", "")
    persona = context.get("persona", "")
    client = context.get("client")
    model = context.get("model", "")
    agent_name = context.get("agent_name", "{name}")

    if not user_input:
        return f"[{agent_name}] 请输入任务内容"

    try:
        if client and model:
            messages = [
                {"role": "system", "content": persona or "你是一个 helpful 的 AI 助手。"},
                {"role": "user", "content": user_input},
            ]
            resp = client.chat.completions.create(model=model, messages=messages)
            return resp.choices[0].message.content
        return f"[{agent_name}] 收到任务: {user_input}"
    except Exception as e:
        return f"[{agent_name}] 执行出错: {e}\n{traceback.format_exc()}"
'''


DEFAULT_AGENT_CODE = None  # 由 get_default_agent_code 延迟格式化，避免模板中大括号被提前解释


def get_default_agent_code(name: str) -> str:
    """生成指定名称的兜底 agent.py 代码"""
    return DEFAULT_AGENT_CODE_TEMPLATE.replace("{name}", name)


DEFAULT_WORKFLOW = '''# {name} 工作流

## 步骤1：理解需求
- **action**: ai_generate
- **params**:
  - prompt: "基于以下需求给出分析：{{user_input}}"

## 步骤2：生成回答
- **action**: ai_generate
- **params**:
  - prompt: "根据分析结果，给出最终回答：{{step1.result}}"
'''


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
    返回 {"persona": str, "skills": str, "code": str, "workflow": str, "raw": str}
    """
    prompt = GENERATION_PROMPT_ZH.replace("{name}", name).replace("{description}", description)
    messages = [{"role": "user", "content": prompt}]

    sys.stdout.write("🧙 正在创建分身... ")
    sys.stdout.flush()
    raw, _, _, _ = stream_cnt(client, model, messages, lang, custom_prefix="", max_tokens=4096)

    persona = _extract_section(raw, "---PERSONA_START---", "---PERSONA_END---")
    skills = _extract_section(raw, "---SKILLS_START---", "---SKILLS_END---")
    code = _extract_section(raw, "---CODE_START---", "---CODE_END---")
    code = _clean_code_block(code)
    workflow = _extract_section(raw, "---WORKFLOW_START---", "---WORKFLOW_END---")

    # 如果没有提取到代码，尝试从原始回复中直接找代码块
    if not code and "```python" in raw:
        s = raw.find("```python")
        e = raw.find("```", s + 1)
        if e > s:
            code = _clean_code_block(raw[s:e + 3])

    # 兜底：确保有可用代码
    if not code:
        code = get_default_agent_code(name)

    # 兜底：确保有工作流模板
    if not workflow:
        workflow = DEFAULT_WORKFLOW.replace("{name}", name)

    return {
        "persona": persona,
        "skills": skills,
        "code": code,
        "workflow": workflow,
        "raw": raw,
    }
