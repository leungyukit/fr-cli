"""
@RAG 内置 Agent —— 本地知识库检索增强生成
使用 ChromaDB 持久化向量存储 + sentence-transformers 嵌入模型。
自动监控知识库目录，新文件自动向量化入库。
"""
import hashlib
import os
import threading
import time
from pathlib import Path

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


class RAGManager:
    """RAG 知识库管理器 —— 向量存储 + 文件监控 + 检索生成"""

    DEFAULT_MODEL = "all-MiniLM-L6-v2"
    CHUNK_SIZE = 500
    CHUNK_OVERLAP = 50

    def __init__(self, kb_dir=None, db_path=None):
        self.kb_dir = Path(kb_dir) if kb_dir else None
        self.db_path = Path(db_path) if db_path else Path.home() / ".fr_cli_rag_db"
        self.client = None
        self.collection = None
        self.embedder = None
        self._watcher_thread = None
        self._stop_watcher = threading.Event()
        self._file_state = {}  # path -> (mtime, hash)
        self._initialized = False

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

    # ---------- 文件处理 ----------

    def _read_file(self, path):
        """读取文件内容"""
        path = Path(path)
        if not path.exists():
            return None
        try:
            if path.suffix.lower() in (".txt", ".md", ".py", ".js", ".json", ".html", ".css", ".xml", ".yaml", ".yml"):
                return path.read_text(encoding="utf-8", errors="ignore")
            elif path.suffix.lower() in (".csv",):
                import pandas as pd
                df = pd.read_csv(path, nrows=1000)
                return df.to_string(index=False)
            elif path.suffix.lower() in (".xlsx", ".xls"):
                import pandas as pd
                df = pd.read_excel(path, nrows=1000)
                return df.to_string(index=False)
        except Exception:
            pass
        return None

    def _chunk_text(self, text, source):
        """将文本分块"""
        chunks = []
        start = 0
        text_len = len(text)
        idx = 0
        while start < text_len:
            end = min(start + self.CHUNK_SIZE, text_len)
            chunk = text[start:end]
            chunk_id = hashlib.md5(f"{source}:{idx}:{chunk[:50]}".encode()).hexdigest()
            chunks.append({"id": chunk_id, "text": chunk, "source": str(source)})
            start += self.CHUNK_SIZE - self.CHUNK_OVERLAP
            idx += 1
        return chunks

    def _file_hash(self, path):
        """计算文件哈希用于去重检测"""
        try:
            stat = os.stat(path)
            return f"{stat.st_mtime}_{stat.st_size}"
        except Exception:
            return ""

    # ---------- 向量入库 ----------

    def add_document(self, path):
        """将单个文件向量化并入库"""
        if not self._ensure_initialized():
            return False, "缺少依赖: pip install chromadb sentence-transformers"

        text = self._read_file(path)
        if text is None:
            return False, f"无法读取文件: {path}"

        chunks = self._chunk_text(text, path)
        if not chunks:
            return False, "文件内容为空"

        ids = [c["id"] for c in chunks]
        # 去重：检查哪些 chunk 已存在
        existing = self.collection.get(ids=ids, include=[])
        existing_ids = set(existing["ids"]) if existing and "ids" in existing else set()
        new_chunks = [c for c in chunks if c["id"] not in existing_ids]

        if new_chunks:
            texts = [c["text"] for c in new_chunks]
            embeddings = self.embedder.encode(texts).tolist()
            self.collection.add(
                ids=[c["id"] for c in new_chunks],
                embeddings=embeddings,
                documents=texts,
                metadatas=[{"source": c["source"]} for c in new_chunks],
            )

        self._file_state[str(path)] = self._file_hash(path)
        return True, f"已入库 {len(new_chunks)} 个新片段（共 {len(chunks)} 个）"

    def sync_directory(self, kb_dir=None):
        """扫描目录，自动向量化新文件/更新文件"""
        if not self._ensure_initialized():
            return False, "缺少依赖: pip install chromadb sentence-transformers"

        target = Path(kb_dir) if kb_dir else self.kb_dir
        if not target or not target.exists():
            return False, "知识库目录未设置或不存在"

        results = []
        for root, _, files in os.walk(target):
            for fname in files:
                path = Path(root) / fname
                fhash = self._file_hash(path)
                prev = self._file_state.get(str(path))
                if prev != fhash:
                    ok, msg = self.add_document(path)
                    results.append(f"{fname}: {msg}")

        if not results:
            return True, "所有文件已是最新状态"
        return True, "\n".join(results)

    # ---------- 检索生成 ----------

    def query(self, question, client, model, lang="zh", top_k=5):
        """向量检索 + 大模型生成回答"""
        if not self._ensure_initialized():
            return None, "缺少依赖: pip install chromadb sentence-transformers"

        if self.collection.count() == 0:
            return None, "知识库为空，请先设置知识库目录并同步。"

        q_emb = self.embedder.encode([question]).tolist()
        results = self.collection.query(query_embeddings=q_emb, n_results=top_k, include=["documents", "metadatas"])

        docs = []
        for i, doc_list in enumerate(results.get("documents", [])):
            for j, doc in enumerate(doc_list):
                meta = results.get("metadatas", [])[i][j] if results.get("metadatas") else {}
                source = meta.get("source", "未知")
                docs.append(f"[来源: {source}]\n{doc}")

        context = "\n\n---\n\n".join(docs)
        prompt = f"""你是一个知识库问答助手。请根据以下检索到的知识片段回答用户问题。
如果知识片段不足以回答问题，请明确说明。

知识片段:
{context}

用户问题: {question}

请用中文给出准确、简洁的回答。引用来源时请标注 [来源: 文件名]。
"""
        from fr_cli.core.stream import stream_cnt
        messages = [{"role": "user", "content": prompt}]
        result, _, _ = stream_cnt(client, model, messages, lang, custom_prefix="", max_tokens=4096)
        return result, None

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

    def stop_watcher(self):
        self._stop_watcher.set()
        self._watcher_thread = None


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

    # 启动后台监控（如果未启动）
    if mgr._watcher_thread is None or not mgr._watcher_thread.is_alive():
        mgr.start_watcher()

    print(f"{CYAN}🔍 正在检索知识库并生成回答...{RESET}")
    result, err = mgr.query(question, state.client, state.model_name, state.lang)
    if err:
        print(f"{RED}{err}{RESET}")
    else:
        print(f"\n{GREEN}{result}{RESET}")
