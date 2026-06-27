from fr_cli.conf.paths import RAG_DB_DIR, RAG_WATCHER_PID_FILE, RAG_WATCHER_STOP_FILE, RAG_WATCHER_LOG_FILE
"""
@RAG 内置 Agent —— 本地知识库检索增强生成
使用 ChromaDB 持久化向量存储 + sentence-transformers 嵌入模型。
自动监控知识库目录，新文件自动向量化入库。
"""
import hashlib
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Tuple

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
        # 检索结果缓存(10 分钟 TTL)
        self._query_cache: Dict[str, Tuple[float, Any]] = {}
        self._cache_ttl = 600  # 秒
        self._cache_max = 128  # 最多缓存条数
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

    # ---------- 文件处理 ----------

    def _read_file(self, path):
        """读取文件内容"""
        path = Path(path)
        if not path.exists():
            return None
        try:
            if path.stat().st_size > 10 * 1024 * 1024:
                return None
        except Exception:
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
        """将单个文件向量化并入库。如果文件已存在，先删除旧片段再重新入库。"""
        if not self._ensure_initialized():
            return False, "缺少依赖: pip install chromadb sentence-transformers"

        text = self._read_file(path)
        if text is None:
            return False, f"无法读取文件: {path}"

        chunks = self._chunk_text(text, path)
        if not chunks:
            return False, "文件内容为空"

        with self._db_lock:
            # 如果文件之前已入库，先删除该文件的所有旧片段
            source_key = str(path)
            if source_key in self._file_state:
                try:
                    old_ids = self.collection.get(
                        where={"source": source_key}, include=[]
                    )
                    if old_ids and "ids" in old_ids and old_ids["ids"]:
                        self.collection.delete(ids=old_ids["ids"])
                except Exception:
                    pass

            ids = [c["id"] for c in chunks]
            texts = [c["text"] for c in chunks]
            embeddings = self.embedder.encode(texts).tolist()
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=[{"source": c["source"]} for c in chunks],
            )

        self._file_state[str(path)] = self._file_hash(path)
        return True, f"已入库 {len(chunks)} 个片段"

    def sync_directory(self, kb_dir=None):
        """扫描目录，自动向量化新文件/更新文件，并清理已删除文件的旧片段"""
        if not self._ensure_initialized():
            return False, "缺少依赖: pip install chromadb sentence-transformers"

        target = Path(kb_dir) if kb_dir else self.kb_dir
        if not target or not target.exists():
            return False, "知识库目录未设置或不存在"

        # 收集当前目录中的所有文件路径
        current_files = set()
        for root, _, files in os.walk(target):
            for fname in files:
                current_files.add(str(Path(root) / fname))

        with self._db_lock:
            # 清理已不在目录中的文件的旧片段
            removed_sources = [p for p in self._file_state if p not in current_files]
            for source in removed_sources:
                try:
                    old_ids = self.collection.get(
                        where={"source": source}, include=[]
                    )
                    if old_ids and "ids" in old_ids and old_ids["ids"]:
                        self.collection.delete(ids=old_ids["ids"])
                except Exception:
                    pass
                del self._file_state[source]

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

    def query(self, question, client, model, lang="zh", top_k=8):
        """向量检索 -> 取 Top-K 片段 -> 大模型综合生成回答

        缓存策略:基于 question + top_k + lang 的 SHA256 hash,TTL 10 分钟。
        跳过缓存:lang != "zh"/"en" 或 question > 2000 字符
        """
        if not self._ensure_initialized():
            return None, "缺少依赖: pip install chromadb sentence-transformers"

        # 缓存命中
        cache_key = self._query_cache_key(question, top_k, lang)
        if cache_key in self._query_cache:
            ts, cached = self._query_cache[cache_key]
            if time.time() - ts < self._cache_ttl:
                return cached, None
            else:
                # 过期清理
                self._query_cache.pop(cache_key, None)

        with self._db_lock:
            if self.collection.count() == 0:
                return None, "知识库为空，请先设置知识库目录并同步。"

            q_emb = self.embedder.encode([question]).tolist()
            results = self.collection.query(
                query_embeddings=q_emb,
                n_results=max(top_k, 1),
                include=["documents", "metadatas"],
            )

        candidates = []
        candidate_metas = []
        for i, doc_list in enumerate(results.get("documents", [])):
            for j, doc in enumerate(doc_list):
                meta = results.get("metadatas", [])[i][j] if results.get("metadatas") else {}
                candidates.append(doc)
                candidate_metas.append(meta)

        if not candidates:
            return None, "未检索到相关知识。"

        # 构造带来源标注的上下文
        doc_blocks = []
        for idx, (doc, meta) in enumerate(zip(candidates, candidate_metas), 1):
            source = meta.get("source", "未知")
            doc_blocks.append(f"片段{idx} [来源: {source}]\n{doc}")

        context = "\n\n---\n\n".join(doc_blocks)

        if lang == "zh":
            prompt = f"""你是一个知识库问答助手。以下是从知识库中向量检索出的相关片段，请基于这些片段综合回答用户问题。

知识片段:
{context}

用户问题: {question}

回答要求：
1. 优先基于上述片段内容回答，可综合多个片段
2. 如果片段信息不足以完整回答，请明确说明
3. 引用来源时请标注 [来源: 文件名]
4. 请用中文给出准确、简洁的回答
"""
        else:
            prompt = f"""You are a knowledge base Q&A assistant. Below are relevant snippets retrieved from the knowledge base. Please synthesize an answer based on these snippets.

Knowledge Snippets:
{context}

User Question: {question}

Instructions:
1. Base your answer on the snippets above; you may synthesize multiple snippets
2. If the snippets are insufficient, state so clearly
3. Cite sources as [Source: filename]
4. Give an accurate and concise answer
"""

        from fr_cli.core.stream import stream_cnt
        messages = [{"role": "user", "content": prompt}]
        result, _, _, _ = stream_cnt(client, model, messages, lang, custom_prefix="", max_tokens=4096)

        # 写缓存
        self._write_cache(cache_key, (result, None))
        return result, None

    def _query_cache_key(self, question: str, top_k: int, lang: str) -> str:
        """生成查询缓存 key"""
        # 超长问题或非标准 lang 不缓存
        if len(question) > 2000 or lang not in ("zh", "en"):
            return f"_nocache_{id(self)}_{time.time()}"
        h = hashlib.sha256(f"{question}|{top_k}|{lang}".encode("utf-8")).hexdigest()
        return h[:32]

    def _write_cache(self, key: str, value: Any) -> None:
        """写缓存(满了清掉最旧的)"""
        if key.startswith("_nocache_"):
            return
        if len(self._query_cache) >= self._cache_max:
            # 清掉最旧的 1/4
            to_remove = max(1, self._cache_max // 4)
            by_ts = sorted(self._query_cache.items(), key=lambda x: x[1][0])
            for k, _ in by_ts[:to_remove]:
                self._query_cache.pop(k, None)
        self._query_cache[key] = (time.time(), value)

    def clear_cache(self) -> int:
        """清空缓存,返回清理条数"""
        n = len(self._query_cache)
        self._query_cache.clear()
        return n

    def cache_stats(self) -> Dict[str, Any]:
        """缓存统计"""
        now = time.time()
        valid = sum(1 for ts, _ in self._query_cache.values() if now - ts < self._cache_ttl)
        expired = len(self._query_cache) - valid
        return {
            "total": len(self._query_cache),
            "valid": valid,
            "expired": expired,
            "ttl_seconds": self._cache_ttl,
            "max_entries": self._cache_max,
        }

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


# ---------- 独立守护进程管理器 ----------

import subprocess

RAG_WATCHER_PID_FILE = RAG_WATCHER_PID_FILE
RAG_WATCHER_STOP_FILE = RAG_WATCHER_STOP_FILE
RAG_WATCHER_LOG_FILE = RAG_WATCHER_LOG_FILE


class RAGWatcherManager:
    """RAG 知识库独立守护进程管理器 —— 知识库主宰
    负责在主进程之外独立启动/停止/监控知识库文件监听守护进程。
    守护进程脱离终端运行，用户退出 fr-cli 后仍继续工作。
    """

    @staticmethod
    def _daemon_script_path():
        return Path(__file__).with_name("rag_watcher_daemon.py")

    @staticmethod
    def _read_pid():
        if RAG_WATCHER_PID_FILE.exists():
            try:
                return int(RAG_WATCHER_PID_FILE.read_text(encoding="utf-8").strip())
            except Exception:
                pass
        return None

    @staticmethod
    def _is_pid_alive(pid):
        """跨平台检测进程是否存活"""
        try:
            if sys.platform == "win32":
                import ctypes
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(1, False, pid)
                if handle:
                    kernel32.CloseHandle(handle)
                    return True
                return False
            else:
                os.kill(pid, 0)
                return True
        except (OSError, ProcessLookupError):
            return False

    @staticmethod
    def _cleanup_files():
        for f in (RAG_WATCHER_PID_FILE, RAG_WATCHER_STOP_FILE):
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass

    def is_running(self):
        pid = self._read_pid()
        if pid and self._is_pid_alive(pid):
            return True
        if RAG_WATCHER_PID_FILE.exists():
            self._cleanup_files()
        return False

    def start(self, kb_dir, db_path=None, interval=30):
        """启动独立守护进程"""
        if self.is_running():
            pid = self._read_pid()
            return False, f"RAG 守护进程已在运行 (PID: {pid})"

        self._cleanup_files()
        daemon_script = self._daemon_script_path()
        if not daemon_script.exists():
            return False, f"守护进程脚本不存在: {daemon_script}"

        target = Path(kb_dir)
        if not target.exists():
            return False, f"知识库目录不存在: {kb_dir}"

        try:
            kwargs = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

            cmd = [
                sys.executable, str(daemon_script),
                "--kb_dir", str(target.resolve()),
                "--interval", str(max(5, interval)),
            ]
            if db_path:
                cmd.extend(["--db_path", str(db_path)])

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                close_fds=True,
                **kwargs
            )

            # 等待 PID 文件写入
            for _ in range(10):
                time.sleep(0.3)
                pid = self._read_pid()
                if pid and self._is_pid_alive(pid):
                    return True, f"RAG 守护进程已启动 (PID: {pid})"
                if proc.poll() is not None:
                    return False, "守护进程启动后立即退出，请检查日志: ~/.fr_cli/rag/watcher.log"

            return True, f"RAG 守护进程已启动 (PID: {proc.pid})"
        except Exception as e:
            return False, f"启动失败: {e}"

    def stop(self):
        """停止独立守护进程"""
        pid = self._read_pid()
        if not pid:
            self._cleanup_files()
            return False, "RAG 守护进程未运行。"

        if not self._is_pid_alive(pid):
            self._cleanup_files()
            return False, "RAG 守护进程未运行（已清理残留状态）。"

        # 写入停止标记
        try:
            RAG_WATCHER_STOP_FILE.write_text("1", encoding="utf-8")
        except Exception as e:
            return False, f"发送停止信号失败: {e}"

        # 等待进程自行退出
        for _ in range(15):
            if not self._is_pid_alive(pid):
                self._cleanup_files()
                return True, "RAG 守护进程已停止。"
            time.sleep(0.5)

        # 强制终止
        try:
            if sys.platform == "win32":
                os.kill(pid, signal.CTRL_BREAK_EVENT)
            else:
                os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except Exception:
            pass

        for _ in range(5):
            if not self._is_pid_alive(pid):
                self._cleanup_files()
                return True, "RAG 守护进程已停止。"
            time.sleep(0.5)

        self._cleanup_files()
        return True, "RAG 守护进程已强制停止。"

    def status(self):
        """查询守护进程状态"""
        pid = self._read_pid()
        if not pid:
            return "RAG 守护进程未运行。"
        if self._is_pid_alive(pid):
            return f"RAG 守护进程运行中 (PID: {pid})"
        self._cleanup_files()
        return "RAG 守护进程未运行（已清理残留状态）。"

    @staticmethod
    def get_log(lines=50):
        """读取守护进程日志最后 N 行"""
        if not RAG_WATCHER_LOG_FILE.exists():
            return "暂无日志。"
        try:
            with open(RAG_WATCHER_LOG_FILE, "r", encoding="utf-8") as f:
                all_lines = f.readlines()
            return "".join(all_lines[-lines:])
        except Exception as e:
            return f"读取日志失败: {e}"
