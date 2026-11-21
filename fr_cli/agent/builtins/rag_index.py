"""
RAGManager 向量入库 mixin —— add_document / sync_directory

从 fr_cli.agent.builtins.rag 拆出(原文件 509 行)。
依赖 rag.py 核心提供的 self.client / self.collection / self.embedder /
self._db_lock / self._file_state(均由 _ensure_initialized 与 __init__ 建立)。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple


class RAGIndexMixin:
    """向量入库与目录同步"""

    def add_document(self, path) -> Tuple[bool, str]:
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

    def sync_directory(self, kb_dir=None) -> Tuple[bool, str]:
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
