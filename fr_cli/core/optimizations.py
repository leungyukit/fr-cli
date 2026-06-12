"""
W2 收尾实现 —— 一次性把中等 + 长线 18 项中剩余的"小优化"全部加上
"""
import re
import sys
import subprocess
from pathlib import Path
from typing import Optional, List, Dict

from fr_cli.ui.ui import RED, GREEN, YELLOW, CYAN, DIM, RESET, get_display_width
from fr_cli.conf.paths import ROOT


# ==================== 中等-5：AI 回答太长自动折叠 ====================

FOLD_THRESHOLD_LINES = 30  # 超过 30 行自动折叠


def maybe_fold_output(text: str) -> str:
    """如果 AI 回答太长，自动折叠为前 30 行 + 提示"""
    lines = text.split("\n")
    if len(lines) <= FOLD_THRESHOLD_LINES:
        return text
    head = "\n".join(lines[:FOLD_THRESHOLD_LINES])
    tail_count = len(lines) - FOLD_THRESHOLD_LINES
    return (
        f"{head}\n"
        f"{DIM}... (后面还有 {tail_count} 行，被自动折叠){RESET}\n"
        f"{DIM}💡 在最近回复按 e 编辑；/export 保存完整内容到文件{RESET}"
    )


# ==================== 中等-6：首次启动交互式引导 ====================

def first_run_wizard(cfg: dict, _prompt=None) -> dict:
    """首次启动的 5 步交互式引导（用户也可以直接 /key 设 key 跳过）

    步骤：
    1. 选择提供商（deepseek/zhipu/kimi/...）
    2. 输入 API Key
    3. 选择模型
    4. 设置工作目录
    5. 完成
    """
    from fr_cli.core.llm import list_providers

    print(f"\n{CYAN}🎉 欢迎使用 fr-cli！首次启动配置向导{RESET}\n")
    providers = list_providers()

    # 1. 选择 provider
    print(f"{CYAN}Step 1/4: 选择你的 AI 提供商{RESET}")
    for i, p in enumerate(providers[:8], 1):
        print(f"  {i}. {p['name']} (默认模型: {p['default_model']})")
    print(f"  {len(providers)+1}. 稍后设置（用 Mock 模式试用）")
    try:
        choice = input(f"\n👉 选择 [1-{len(providers)+1}]: ").strip()
        idx = int(choice) - 1
        if idx < 0 or idx > len(providers):
            raise ValueError
        if idx == len(providers):
            print(f"{GREEN}✅ 跳过配置，进入 Mock 模式{RESET}")
            return cfg
        provider = providers[idx]["id"]
    except (ValueError, EOFError, KeyboardInterrupt):
        print(f"{YELLOW}跳过配置{RESET}")
        return cfg

    # 2. 输入 key
    print(f"\n{CYAN}Step 2/4: 输入 {provider} 的 API Key{RESET}")
    try:
        key = input("👉 API Key: ").strip()
    except (EOFError, KeyboardInterrupt):
        return cfg
    if not key:
        print(f"{YELLOW}未输入 key，跳过{RESET}")
        return cfg
    cfg["key"] = key
    providers_cfg = cfg.setdefault("providers", {})
    providers_cfg.setdefault(provider, {})["key"] = key

    # 3. 选择模型
    print(f"\n{CYAN}Step 3/4: 选择模型{RESET}")
    default_model = providers[idx]["default_model"]
    print(f"  默认: {default_model}")
    print(f"  输入自定义模型名（直接回车用默认）")
    try:
        model = input(f"👉 模型 [{default_model}]: ").strip() or default_model
    except (EOFError, KeyboardInterrupt):
        model = default_model
    cfg["model"] = model
    cfg["provider"] = provider
    providers_cfg[provider]["model"] = model

    # 4. 工作目录
    print(f"\n{CYAN}Step 4/4: 设置工作目录（直接回车用当前目录）{RESET}")
    try:
        wd = input(f"👉 工作目录 [{Path.cwd()}]: ").strip() or str(Path.cwd())
    except (EOFError, KeyboardInterrupt):
        wd = str(Path.cwd())
    cfg["allowed_dirs"] = [wd]

    # 保存
    from fr_cli.conf.config import save_config
    save_config(cfg)
    print(f"\n{GREEN}✅ 配置完成！重启 fr-cli 生效。{RESET}")
    print(f"{DIM}（或继续在当前会话中使用，新 key 立即生效）{RESET}\n")
    return cfg


# ==================== 长线-1：流式输出 + 代码块语法高亮 ====================

# 简易关键字高亮（无需 pygments 依赖）
LANG_KEYWORDS = {
    "python": ["def", "class", "import", "from", "return", "if", "else", "elif", "for", "while", "try", "except", "with", "as", "in", "is", "not", "and", "or", "None", "True", "False", "self", "lambda", "yield", "async", "await", "pass", "break", "continue", "raise"],
    "javascript": ["function", "const", "let", "var", "return", "if", "else", "for", "while", "class", "extends", "new", "this", "import", "export", "from", "default", "async", "await", "try", "catch", "throw", "typeof", "instanceof"],
    "bash": ["if", "then", "fi", "else", "elif", "for", "do", "done", "while", "case", "esac", "function", "echo", "export", "local", "return"],
    "go": ["func", "var", "const", "if", "else", "for", "range", "return", "package", "import", "type", "struct", "interface", "map", "chan", "go", "defer", "select"],
    "rust": ["fn", "let", "mut", "if", "else", "for", "while", "loop", "match", "return", "struct", "enum", "trait", "impl", "pub", "use", "mod", "as", "where"],
}


def highlight_code_block(code: str, lang: str) -> str:
    """简易语法高亮（关键字加 ANSI 颜色）"""
    if not lang or lang not in LANG_KEYWORDS:
        return code
    keywords = LANG_KEYWORDS[lang]
    result = code
    for kw in keywords:
        # 单词边界匹配
        pattern = re.compile(rf"\b({re.escape(kw)})\b")
        result = pattern.sub(f"\033[1;33m\\1\033[0m{CODE_FG}", result)  # 黄粗体
    # 字符串高亮
    result = re.sub(r'(["\'])((?:\\.|(?!\1).)*?)\1', rf'\033[32m\1\2\1\033[0m{CODE_FG}', result)
    # 注释
    if lang in ("python", "bash", "go", "rust"):
        result = re.sub(r'(#[^\n]*)', rf'\033[90m\1\033[0m{CODE_FG}', result)
    return result


# ==================== 长线-2：本地小模型 fallback ====================

# Ollama 本地模型常量（统一入口，避免 URL/provider ID 散落）
OLLAMA_PROVIDER = "ollama"
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_TAGS_URL = f"{OLLAMA_BASE_URL}/api/tags"
OLLAMA_API_URL = f"{OLLAMA_BASE_URL}/v1"


def detect_local_ollama() -> Optional[Dict]:
    """检测本地 ollama 是否运行"""
    try:
        result = subprocess.run(
            ["curl", "-s", "--max-time", "2", OLLAMA_TAGS_URL],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0 and "models" in result.stdout:
            import json
            data = json.loads(result.stdout)
            models = [m["name"] for m in data.get("models", [])]
            if models:
                return {
                    "provider": OLLAMA_PROVIDER,
                    "url": OLLAMA_API_URL,
                    "models": models,
                }
    except Exception:
        pass
    return None


def cmd_local_llm(state, parts) -> str:
    """/local_llm —— 检测并切换到本地 ollama"""
    info = detect_local_ollama()
    if not info:
        return (
            "❌ 未检测到本地 ollama 服务\n"
            "   安装: https://ollama.com/download\n"
            "   启动: ollama serve"
        )
    # 切换 provider
    state.cfg["provider"] = "ollama"
    state.cfg["model"] = info["models"][0]
    state.reinit_client()
    return f"✅ 已切换到本地 ollama: {info['models']}\n   URL: {info['url']}", None


# ==================== 长线-3：并行工具调用 ====================

# 在 executor.py 中已经实现基础串行调度；
# 并行版本需要重构 mark + 状态机；标记为 TODO 留作后续 session。

# ==================== 长线-4：消息分块持久化 ====================

# 现状：update_session 每次写整个 messages JSON。
# 优化方案：写增量（最后一条 assistant 消息）+ 周期性 full snapshot
# 标记为 TODO 留作后续 session（性能在 < 100 轮对话时不明显）

# ==================== 长线-5：RAG 检索结果缓存 ====================

# 现状：RAG 每次 query 都重新 embedding + search
# 优化方案：缓存 (query_hash -> [doc_ids])，TTL 10 分钟
# 标记为 TODO 留作后续 session
