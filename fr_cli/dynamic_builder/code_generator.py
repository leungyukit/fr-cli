"""
动态构建 —— 代码生成

调用 LLM 根据用户需求生成可注册的工具代码。
"""
import re
from fr_cli.core.stream import stream_cnt


CODE_GENERATION_PROMPT_ZH = """你是一位 fr-cli 工具开发专家。请根据用户需求生成一个 Python 工具函数。

要求：
1. 生成的代码必须是一个完整的 Python 文件内容，可直接保存为 .py 文件。
2. 必须包含一个名为 `run(deps, **kwargs)` 的函数，作为工具的入口。
   - deps 是一个命名空间对象，包含：vfs, mail_c, web_c, disk_c, plugins, lang, security, cfg, client, model_name, mcp
   - 函数返回 (result, error)，result 是执行结果，error 是错误字符串或 None
3. 函数第一行必须是文档字符串，说明工具的功能、参数和返回值。
4. 如果需要第三方依赖，请在函数内部使用 try/except ImportError 包裹导入，并在缺失时返回错误提示，提示中包含准确的 pip install 命令。
5. 不要写 main 块、测试代码或示例调用。
6. 代码要简洁、健壮，处理好边界情况。
7. 工具名称（用于注册）必须是合法的 Python 标识符，且尽量反映功能。

用户需求：{requirement}

请只返回 Python 代码（不要包含 Markdown 代码块标记 ```python 等）："""


CODE_GENERATION_PROMPT_EN = """You are an fr-cli tool development expert. Please generate a Python tool function based on the user's requirement.

Requirements:
1. The generated code must be a complete Python file content, ready to be saved as a .py file.
2. It must contain a function named `run(deps, **kwargs)` as the tool entry point.
   - deps is a namespace object containing: vfs, mail_c, web_c, disk_c, plugins, lang, security, cfg, client, model_name, mcp
   - The function returns (result, error), where result is the execution result and error is an error string or None
3. The first line of the function must be a docstring describing the tool's function, parameters, and return value.
4. If third-party dependencies are needed, wrap imports in try/except ImportError inside the function, and return an error hint including the exact pip install command when missing.
5. Do not write main blocks, test code, or example calls.
6. Keep the code concise and robust, handling edge cases.
7. The tool name (used for registration) must be a valid Python identifier and should reflect the function.

User requirement: {requirement}

Please return only Python code (do not include Markdown code block markers like ```python):"""


def extract_tool_name(code: str) -> str:
    """从生成的代码中提取工具函数名，默认返回 run 或第一个 def 的函数名"""
    match = re.search(r'def\s+(\w+)\s*\(\s*deps\s*,\s*\*\*kwargs\s*\)', code)
    if match:
        return match.group(1)
    # 兜底：取第一个 def
    match = re.search(r'def\s+(\w+)\s*\(', code)
    if match:
        return match.group(1)
    return "dynamic_tool"


def generate_tool_code(requirement: str, state, lang: str = "zh") -> str:
    """
    调用 LLM 生成工具代码。

    Returns:
        生成的 Python 代码字符串（已清理 Markdown 标记）
    """
    prompt_template = CODE_GENERATION_PROMPT_ZH if lang == "zh" else CODE_GENERATION_PROMPT_EN
    prompt = prompt_template.format(requirement=requirement)

    messages = [{"role": "user", "content": prompt}]
    txt, _, _, _ = stream_cnt(
        state.client,
        state.model_name,
        messages,
        lang,
        custom_prefix="",
        max_tokens=2048,
        silent=False,
    )

    return _clean_code_markers(txt)


def _clean_code_markers(text: str) -> str:
    """清理 LLM 返回的 Markdown 代码块标记"""
    text = text.strip()
    if text.startswith("```"):
        # 去掉第一行 ```python
        text = text[text.find("\n") + 1:]
    if text.endswith("```"):
        text = text[:text.rfind("```")]
    return text.strip()
