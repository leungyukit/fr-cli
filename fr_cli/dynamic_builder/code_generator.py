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
8. **只输出一个完整实现**：不要给多个候选版本，不要写实现思路、对比说明或
   “方案一/方案二”这类草稿；直接给出一份可以保存成 .py 的最终代码。

【沙箱限制 —— 必须遵守，违反的工具会被拒绝注册】
工具代码运行在**受限子进程**里，以下写法一律不可用：
- 禁止 import：os, sys, subprocess, socket, ssl, select, asyncio, urllib, requests, httpx,
  http, ftplib, smtplib, imaplib, pathlib, glob, tempfile, shutil, importlib, imp, runpy,
  pickle, ctypes, inspect, threading, multiprocessing, signal, resource, fr_cli
- 禁止调用内置函数：open, eval, exec, compile, input, __import__, globals, locals, vars
- 禁止访问 __class__ / __globals__ / __subclasses__ 等 dunder 属性
- 可安全 import 的常用模块：json, re, math, datetime, hashlib, base64, collections,
  itertools, functools, string, statistics, random, textwrap, unicodedata, decimal, uuid

替代方案（务必使用 deps 提供的能力）：
- **读写文件** → `deps.vfs`：read(fn, lang) / write(fn, content, lang, mode='w') /
  append(fn, content, lang) / ls(lang) / cd(path, lang) / exists(fn) /
  list_dirs(lang) / grep_text(fn, pattern, use_regex, lang) / delete(fn, lang)。
  这些方法返回 Result 对象，用 `.is_ok()` / `.data` / `.error` 判断，语言参数传 `deps.lang`。
- **联网搜索 / 抓网页** → `deps.web_c.search(query, lang)` / `deps.web_c.fetch(url, lang)`
- **收发邮件** → `deps.mail_c.inbox(lang)` / `deps.mail_c.read(mail_id, lang)` /
  `deps.mail_c.send(to, subject, body, lang)`
- **云盘** → `deps.disk_c.ls(lang)` / `deps.disk_c.cd(path, lang)` /
  `deps.disk_c.up(local_path, cloud_name, lang)` / `deps.disk_c.down(cloud_name, local_path, lang)`
- **调用大模型** → `deps.client.stream_chat(model, messages)`；注意沙箱里它返回的是
  **列表**（不是生成器），遍历取 `chunk["content"]`
- `deps.security` 在沙箱里是「一律拒绝」的安全桩，不要调用它
- `deps.cfg` 是脱敏后的配置副本，凭证字段一律是 "***"，不要依赖其中的密钥

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
8. **Output exactly ONE complete implementation**: no alternative drafts, no design
   notes, no "option A / option B" sections — just the final code ready to save as .py.

[SANDBOX RESTRICTIONS - you MUST follow them, violating tools are rejected at registration]
The tool runs inside a **restricted child process**. The following are forbidden:
- Forbidden imports: os, sys, subprocess, socket, ssl, select, asyncio, urllib, requests, httpx,
  http, ftplib, smtplib, imaplib, pathlib, glob, tempfile, shutil, importlib, imp, runpy,
  pickle, ctypes, inspect, threading, multiprocessing, signal, resource, fr_cli
- Forbidden builtins: open, eval, exec, compile, input, __import__, globals, locals, vars
- Forbidden dunder access: __class__ / __globals__ / __subclasses__ etc.
- Safe to import: json, re, math, datetime, hashlib, base64, collections, itertools, functools,
  string, statistics, random, textwrap, unicodedata, decimal, uuid

Use the capabilities provided by deps instead:
- **Read/write files** -> `deps.vfs`: read(fn, lang) / write(fn, content, lang, mode='w') /
  append(fn, content, lang) / ls(lang) / cd(path, lang) / exists(fn) / list_dirs(lang) /
  grep_text(fn, pattern, use_regex, lang) / delete(fn, lang).
  These return Result objects - check `.is_ok()` / `.data` / `.error`, and pass `deps.lang`.
- **Web search / fetch** -> `deps.web_c.search(query, lang)` / `deps.web_c.fetch(url, lang)`
- **Mail** -> `deps.mail_c.inbox(lang)` / `deps.mail_c.read(mail_id, lang)` /
  `deps.mail_c.send(to, subject, body, lang)`
- **Cloud disk** -> `deps.disk_c.ls(lang)` / `deps.disk_c.cd(path, lang)` /
  `deps.disk_c.up(local_path, cloud_name, lang)` / `deps.disk_c.down(cloud_name, local_path, lang)`
- **Call the LLM** -> `deps.client.stream_chat(model, messages)`; inside the sandbox it
  returns a **list** (not a generator) - iterate and take `chunk["content"]`
- `deps.security` is a deny-all stub inside the sandbox - do not call it
- `deps.cfg` is a scrubbed copy - credential fields are always "***"

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
        max_tokens=4096,
        silent=False,
    )

    return _clean_code_markers(txt)


def _clean_code_markers(text: str) -> str:
    """清理 LLM 返回的 Markdown 代码块标记。

    v2.8.7：推理模型（stepfun / glm 等）的 ``reasoning_content`` 会被
    ``core/llm/base.py`` 在 ``content`` 为空时回退拼进正文。

    v2.8.7(第四阶段)：思考与答案已在 ``core/stream.py`` 分离 —— 思考不进返回文本，
    所以正常情况下这里拿到的已经只有答案。本函数保留为**兜底**：
    若 provider 把答案也塞进了 ``reasoning_content``（答案只在思考通道里），
    文本里仍可能夹带散文，这里优先抽取真正的代码块；没有围栏时从
    ``def run(`` 处切开，避免把散文喂给 ``exec()``。
    """
    text = text.strip()
    if not text:
        return text

    # 1) 有围栏代码块 —— 取包含 run 入口且最完整的那一段
    blocks = re.findall(r"```(?:python|py)?[ \t]*\r?\n(.*?)```", text, re.DOTALL)
    if blocks:
        candidates = [b for b in blocks if "def run(" in b] or blocks
        # 推理模型常给出多个草稿版本 —— 取最长的（信息量最大、最可能完整）
        return max(candidates, key=lambda b: len(b)).strip()

    # 2) 无围栏 —— 丢掉正文/思考，从 run 入口开始截
    if "def run(" in text:
        return text[text.index("def run("):].strip()

    # 3) 兜底：原有逻辑
    if text.startswith("```"):
        text = text[text.find("\n") + 1:]
    if text.endswith("```"):
        text = text[:text.rfind("```")]
    return text.strip()
