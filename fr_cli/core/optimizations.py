"""
W2 收尾实现 —— 中等 + 长线 18 项里剩余的"小优化"

v2.8.7 清理说明
----------------
此前本文件里有一半是**只有标题、没有实现**的占位段（"中等-5 AI 回答太长
自动折叠" / "中等-6 首次启动引导" / "长线-1 代码块语法高亮" / "长线-3~5"），
配套的常量（``FOLD_THRESHOLD_LINES`` / ``LANG_KEYWORDS``）也**全仓零引用**
—— 读代码的人会以为这些功能已经存在，实际上一行都没跑起来。

现在的归属（都已落地并接入）：
======================================  ==========================================
能力                                        实现位置
======================================  ==========================================
代码块语法高亮（零依赖）                     ``fr_cli/ui/syntax.py``
长回答折叠 + Ctrl+O 展开                    ``fr_cli/ui/markdown_stream.py``
                                            ``fr_cli/core/collapse.py``
首次启动"快速上手"卡片                     ``fr_cli/repl/bootstrap.py``
原生 FC 多工具并发执行                      ``fr_cli/command/parallel.py``
                                            ``fr_cli/core/chat/pipeline_respond.py``
会话增量持久化（增量写 + 周期快照）          ``fr_cli/memory/incremental.py``
                                            ``fr_cli/memory/session.py``
RAG 查询缓存（TTL 600s + 磁盘持久化）        ``fr_cli/agent/builtins/rag_cache.py``
======================================  ==========================================

本文件末尾的"收口记录"一节列出了逐条核实过后的真实状态。
"""
import subprocess
from typing import Optional, Dict


# ------------------------------------------------------------------
# 长线-2：本地小模型 fallback（ollama）
# ------------------------------------------------------------------

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
            "[x] 未检测到本地 ollama 服务\n"
            "   安装: https://ollama.com/download\n"
            "   启动: ollama serve"
        )
    # 切换 provider
    state.cfg["provider"] = "ollama"
    state.cfg["model"] = info["models"][0]
    state.reinit_client()
    return f"[OK] 已切换到本地 ollama: {info['models']}\n   URL: {info['url']}", None


# ------------------------------------------------------------------
# 收口记录（v2.8.7 复核后更正 —— 此前这里的三条 TODO 有两条是**过时**的）
#
# ⚠️ 本节曾写着"长线-3/4/5 未实现"。逐条核实代码后的真实情况：
#
# - 长线-3 并行工具调用 —— **已实现**（本次补齐原生路径）
#     并发执行器早就存在（``command/parallel.py::ParallelExecutor``），
#     但只接在**文本标记路径**（【并行调用】）；**原生 function calling**
#     返回多个 tool_calls 时仍是串行。现已让原生路径也并发
#     （``core/chat/pipeline_respond.py``），结果按调用顺序回填。
#     另修掉一个隐患：并行时多个线程会同时 ``input()`` 抢终端，
#     用户的 Y/A/F/N 可能落到另一个工具上 —— 已加全局确认锁
#     （``security/security.py::_CONFIRM_LOCK``）。
#
# - 长线-4 消息分块持久化 —— **已实现**（本次把生产路径接上）
#     增量写入器（``memory/incremental.py``：增量写 + 周期全量 snapshot
#     + 合并读取）**早就写好了，但只有它自己的测试在用**；
#     ``memory/session.py::update_session`` 仍是每轮全量重写整个
#     messages JSON（1000 条消息 ≈ 1MB/轮）。现已接线，并补上
#     v1 → v2 存量迁移、历史被 ``/undo`` 截断时的全量重写、
#     以及 ``list_sessions`` 对 v2 格式的计数。
#
# - 长线-5 RAG 检索结果缓存 —— **早已实现**（不是缺口）
#     ``agent/builtins/rag_cache.py``（内存 TTL 600s + 跨会话磁盘持久化）
#     且**已接线**到 ``rag_query.py`` 的查询路径（命中即返回）。
#     此前这条 TODO 是**过时信息** —— 读代码的人会以为缓存没做。
#
# 仍未做、且**有意不做**的：
# - ``/api/command``（Web → AI）：默认关闭。放开需要独立高权限 token
#   + 命令白名单 + 强制非交互 —— 详见 ``web/console/handler.py`` 注释。
# - Bot 侧新增平台通道（企微 / 钉钉 / 邮件）：属于**新增功能**而非补欠账，
#   且路线图要求先拍板"首个接入哪个平台"（docs/BOT_HARNESS_ROADMAP.md 第 7 节）。
# ------------------------------------------------------------------
