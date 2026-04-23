"""
意图判定引擎

封装关键词预检与 LLM 意图分类逻辑。
负责判定用户输入是直接问答还是需要调用工具。
"""

from fr_cli.core.stream import stream_cnt


# 明确的工具操作关键词（兜底规则，避免大模型漏判）
# 同时包含中英文，覆盖用户在任何语言界面下输入任意语言的场景
_FORCE_TOOL_KEYWORDS = [
    # 中文关键词
    "保存", "保存到", "保存文件", "写入", "写到", "写入文件", "写到文件",
    "创建文件", "生成文件", "输出到文件", "导出到", "导出文件",
    "搜索", "查找", "查一下", "搜一下",
    "发送邮件", "发邮件", "发信", "发邮件给", "发信给",
    "查看目录", "列出文件", "查看文件", "打开文件",
    "画图", "生成图片", "画一张", "画个", "生成图像",
    "运行代码", "执行代码", "执行脚本", "运行脚本",
    "定时任务", "定时执行", "循环任务",
    "上传", "上传到", "下载", "下载到",
    "保存会话", "导出会话", "切换模型", "设置密钥",
    # 英文关键词
    "save", "save to", "save file", "write", "write to", "write file",
    "create file", "generate file", "output to file", "export", "export to",
    "search", "look up", "look for", "find", "google", "bing",
    "send email", "send mail", "send an email", "email to", "mail to",
    "list files", "list directory", "show files", "show directory", "open file",
    "draw", "generate image", "create image", "paint", "image of",
    "run code", "execute code", "run script", "execute script",
    "schedule", "scheduled task", "cron job", "timer",
    "upload", "upload to", "download", "download to",
    "save session", "export session", "switch model", "set key", "set api key",
    # MCP 外部神通关键词
    "mcp", "外部工具", "外部神通", "调用工具", "use tool", "invoke tool",
]

# 保存意图关键词（用于第二轮强制保存检测）
_SAVE_KEYWORDS = [
    "保存", "保存到", "保存文件", "写入", "写到", "写入文件", "写到文件",
    "存储", "存到", "存为", "导出到", "导出文件",
    "save", "save to", "save file", "save as", "write", "write to", "write file",
    "store", "store to", "export to", "export file",
]

# 信息获取关键词（触发"先回答再调用工具"双源模式）
_INFO_FETCH_KEYWORDS = [
    # 搜索/查询
    "搜索", "查询", "查一下", "搜一下", "什么是", "是什么", "介绍", "了解一下",
    "最新", "新闻", "资讯", "百科", "定义", "概念", "解释",
    "search", "look up", "what is", "what are", "introduction to", "latest",
    "news", "wikipedia", "who is", "how to", "define", "explain",
    # 远程/RAG/Agent
    "远程", "rag", "知识库", "agent", "mcp", "外部工具", "外部神通",
    "remote", "knowledge base", "external tool",
    # 文件/数据读取
    "读取", "查看内容", "分析文件", "总结", "提取",
    "read", "analyze file", "summarize", "extract",
]


def should_force_tool(user_input):
    """快速关键词预检：如果包含明确的工具操作关键词，直接判定为需要工具。
    同时检测中英文关键词，不依赖当前界面语言。"""
    u = user_input.lower()
    for kw in _FORCE_TOOL_KEYWORDS:
        if kw in u:
            return True
    return False


def classify_intent(state, user_input, tools, lang):
    """
    意图判定：让大模型判定用户提问是直接查询还是需要调用工具。
    将用户提问内容和 fr-cli 功能列表发给大模型，由大模型做判定。
    返回 "DIRECT"（直接回答）或 "TOOL"（需要调用工具）。
    根据 lang 自动切换中英文 prompt。
    """
    tools_desc = "\n".join([
        f"- {t['name']}: {t['description']} (commands: {', '.join(t['commands'])}"
        for t in tools
    ])

    if lang == "en":
        classify_prompt = f"""You are an intent classifier. Based on the user's question, determine whether they need a direct answer or need to use the following tools to complete their task.

Available tools:
{tools_desc}

Rules (strict):
- DIRECT: The user is only asking for information, concepts, advice, or chatting. No action is required.
- TOOL: The user requests any specific action, including but not limited to saving files, searching the web, sending emails, listing directories, running code, generating images, etc. If the user mentions any action word like "save", "write", "search", "send", "look up", "list", etc., even if the first half is a question, it MUST be classified as TOOL.

User question: {user_input}

Output only one word: DIRECT or TOOL. No explanation."""
    else:
        classify_prompt = f"""你是一个意图分类器。请根据用户的提问，判定用户是需要直接获得回答，还是需要调用以下工具来完成任务。

可用工具列表：
{tools_desc}

判定规则（请严格遵守）：
- DIRECT：用户只是单纯询问信息、概念、建议、闲聊，没有任何操作要求。
- TOOL：用户要求执行任何具体操作，包括但不限于保存文件、搜索网页、发送邮件、查看目录、运行代码、画图等。只要用户提到了"保存"、"写入"、"搜索"、"发送"、"查看"等操作性词汇，即使前半句是询问信息，也必须判定为 TOOL。

用户提问：{user_input}

请只输出一个单词：DIRECT 或 TOOL。不要输出任何解释。"""

    messages = [{"role": "user", "content": classify_prompt}]
    txt, _, _ = stream_cnt(
        state.client, state.model_name, messages, lang,
        custom_prefix="", max_tokens=10, silent=True
    )

    return "TOOL" if "TOOL" in txt.upper() else "DIRECT"


def has_info_fetch_intent(user_input):
    """检测用户输入是否包含信息获取关键词（触发双源回答模式）。"""
    return any(kw in user_input.lower() for kw in _INFO_FETCH_KEYWORDS)


def has_save_intent(user_input):
    """检测用户输入是否包含保存意图关键词。"""
    return any(kw in user_input.lower() for kw in _SAVE_KEYWORDS)
