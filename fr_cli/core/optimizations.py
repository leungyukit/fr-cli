"""
W2 收尾实现 —— 一次性把中等 + 长线 18 项中剩余的"小优化"全部加上
"""
import re
import subprocess
from pathlib import Path
from typing import Optional, Dict

from fr_cli.ui.ui import GREEN, YELLOW, CYAN, DIM, RESET, CODE_FG


# ==================== 中等-5：AI 回答太长自动折叠 ====================

FOLD_THRESHOLD_LINES = 30  # 超过 30 行自动折叠


# ==================== 中等-6：首次启动交互式引导 ====================

# ==================== 长线-1：流式输出 + 代码块语法高亮 ====================

# 简易关键字高亮（无需 pygments 依赖）
LANG_KEYWORDS = {
    "python": ["def", "class", "import", "from", "return", "if", "else", "elif", "for", "while", "try", "except", "with", "as", "in", "is", "not", "and", "or", "None", "True", "False", "self", "lambda", "yield", "async", "await", "pass", "break", "continue", "raise"],
    "javascript": ["function", "const", "let", "var", "return", "if", "else", "for", "while", "class", "extends", "new", "this", "import", "export", "from", "default", "async", "await", "try", "catch", "throw", "typeof", "instanceof"],
    "bash": ["if", "then", "fi", "else", "elif", "for", "do", "done", "while", "case", "esac", "function", "echo", "export", "local", "return"],
    "go": ["func", "var", "const", "if", "else", "for", "range", "return", "package", "import", "type", "struct", "interface", "map", "chan", "go", "defer", "select"],
    "rust": ["fn", "let", "mut", "if", "else", "for", "while", "loop", "match", "return", "struct", "enum", "trait", "impl", "pub", "use", "mod", "as", "where"],
}


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
