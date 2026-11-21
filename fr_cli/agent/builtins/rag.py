"""
@RAG 内置 Agent —— 本地知识库检索增强生成
使用 ChromaDB 持久化向量存储 + sentence-transformers 嵌入模型。
自动监控知识库目录，新文件自动向量化入库。

模块拆分(原单文件 509 行,按职责拆为 4 个 mixin):
- rag_chunking.py: 文件读取 / 分块 / 变更哈希(RAGFileMixin)
- rag_index.py:    向量入库 / 目录同步(RAGIndexMixin)
- rag_query.py:    检索 + 大模型生成(RAGQueryMixin)
- rag_cache.py:    查询缓存,内存 TTL + 跨会话持久化(RAGCacheMixin)
- rag.py:          本文件——RAGManager 组装 + 初始化 + 后台监控 + 单例 + @RAG 入口

公开 API 不变:
    from fr_cli.agent.builtins.rag import RAGManager, get_rag_manager, handle_rag
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Dict, Tuple

from fr_cli.conf.paths import RAG_DB_DIR

from fr_cli.agent.builtins.rag_cache import RAGCacheMixin
from fr_cli.agent.builtins.rag_chunking import RAGFileMixin
from fr_cli.agent.builtins.rag_index import RAGIndexMixin
from fr_cli.agent.builtins.rag_query import RAGQueryMixin

# 可选依赖延迟导入
_chroma = None
_sentence_transformers = None


def _get_chroma():
    global _chroma
    if _chroma is None:
        try:
            import chromadb
            _chroma = chromadb
        except ImportError:
            pass
    return _chroma


def _get_st():
    global _sentence_transformers
    if _sentence_transformers is None:
        try:
            import sentence_transformers as st
            _sentence_transformers = st
        except ImportError:
            pass
    return _sentence_transformers


class RAGManager(RAGCacheMixin, RAGFileMixin, RAGIndexMixin, RAGQueryMixin):
    """RAG 知识库管理器 —— 向量存储 + 文件监控 + 检索生成

    职责分布(见各 mixin 文件):
    - RAGCacheMixin:   查询缓存(TTL / 上限 / 持久化)
    - RAGFileMixin:    文件读取 / 分块 / 哈希
    - RAGIndexMixin:   add_document / sync_directory
    - RAGQueryMixin:   query(检索 + 生成)
    - 本类:           初始化 / 依赖装配 / 后台监控
    """

    DEFAULT_MODEL = "all-MiniLM-L6-v2"
    CHUNK_SIZE = 500
    CHUNK_OVERLAP = 50

    def __init__(self, kb_dir=None, db_path=None, persist_cache=False):
        self.kb_dir = Path(kb_dir) if kb_dir else None
        # 检索结果缓存(10 分钟 TTL,默认内存,可选持久化)
        self._query_cache: Dict[str, Tuple[float, Any]] = {}
        self._cache_ttl = 600  # 秒
        self._cache_max = 128  # 最多缓存条数
        # v2.8+:跨会话持久化缓存(到磁盘)
        self._persist_cache = persist_cache
        self._persist_path = None
        if persist_cache:
            try:
                from fr_cli.conf.paths import ROOT as FR_CLI_DIR
                cache_path = FR_CLI_DIR / "rag_cache.json"
                self._persist_path = str(cache_path)
                self._load_persistent_cache()
            except Exception:
                pass
        self.db_path = Path(db_path) if db_path else RAG_DB_DIR
        self.client = None
        self.collection = None
        self.embedder = None
        self._watcher_thread = None
        self._stop_watcher = threading.Event()
        self._file_state = {}  # path -> (mtime, hash)
        self._initialized = False
        self._db_lock = threading.Lock()

    def _ensure_initialized(self):
        if self._initialized:
            return True
        chroma = _get_chroma()
        st = _get_st()
        if not chroma or not st:
            return False

        self.client = chroma.PersistentClient(path=str(self.db_path))
        self.collection = self.client.get_or_create_collection(name="kb")
        self.embedder = st.SentenceTransformer(self.DEFAULT_MODEL)
        self._initialized = True
        return True

    # ---------- 后台监控 ----------

    def start_watcher(self, kb_dir=None):
        """启动后台线程监控目录变化"""
        target = Path(kb_dir) if kb_dir else self.kb_dir
        if not target:
            return False, "知识库目录未设置"

        self.kb_dir = target
        self._stop_watcher.clear()

        def _watch():
            while not self._stop_watcher.is_set():
                self.sync_directory()
                time.sleep(30)  # 每30秒扫描一次

        self._watcher_thread = threading.Thread(target=_watch, daemon=True)
        self._watcher_thread.start()
        return True, f"后台监控已启动: {target}（每30秒扫描）"


# ---------- 全局单例 ----------
_rag_manager = None


def get_rag_manager(kb_dir=None):
    global _rag_manager
    if _rag_manager is None:
        _rag_manager = RAGManager(kb_dir=kb_dir)
    if kb_dir and _rag_manager.kb_dir != Path(kb_dir):
        _rag_manager.kb_dir = Path(kb_dir)
    return _rag_manager


def handle_rag(user_input, state):
    """处理 @RAG 前缀的请求"""
    from fr_cli.ui.ui import CYAN, GREEN, RED, YELLOW, DIM, RESET

    question = user_input[len("@RAG"):].strip()
    if not question:
        print(f"{RED}用法: @RAG <问题>{RESET}")
        return

    # 检查知识库目录
    kb_dir = state.cfg.get("rag_dir", "")
    if not kb_dir:
        print(f"{YELLOW}未设置知识库目录。{RESET}")
        path = input(f"{DIM}请输入知识库目录路径: {RESET}").strip()
        if not path or not Path(path).exists():
            print(f"{RED}目录不存在。{RESET}")
            return
        state.cfg["rag_dir"] = path
        from fr_cli.conf.config import save_config
        save_config(state.cfg)
        kb_dir = path

    mgr = get_rag_manager(kb_dir)

    # 首次同步
    print(f"{CYAN}📚 正在同步知识库...{RESET}")
    ok, msg = mgr.sync_directory()
    if ok:
        print(f"{GREEN}{msg}{RESET}")
    else:
        print(f"{YELLOW}{msg}{RESET}")

    # 如果独立守护进程在运行，不启动内置 watcher
    watcher = RAGWatcherManager()
    if watcher.is_running():
        print(f"{DIM}ℹ️ 独立守护进程正在后台运行，知识库将自动同步。{RESET}")
    else:
        # 启动内置后台监控（如果未启动）
        if mgr._watcher_thread is None or not mgr._watcher_thread.is_alive():
            mgr.start_watcher()

    print(f"{CYAN}🔍 正在检索知识库并生成回答...{RESET}")
    result, err = mgr.query(question, state.client, state.model_name, state.lang)
    if err:
        print(f"{RED}{err}{RESET}")
    else:
        print(f"\n{GREEN}{result}{RESET}")


# ---------- 独立守护进程管理器(已拆到 rag_watcher.py) ----------

# 向后兼容 re-export:老代码可能直接 import RAGWatcherManager
try:
    from fr_cli.agent.builtins.rag_watcher import RAGWatcherManager  # noqa: F401
except Exception:
    pass
