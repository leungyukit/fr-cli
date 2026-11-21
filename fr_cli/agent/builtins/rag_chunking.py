"""
RAGManager 文件处理 mixin —— 读取 / 分块 / 哈希

从 fr_cli.agent.builtins.rag 拆出(原文件 509 行)。
本 mixin 提供知识库文件的读取、文本分块与变更检测。
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path


class RAGFileMixin:
    """文件读取 / 分块 / 变更哈希"""

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
