"""
RAGManager 检索生成 mixin —— query

从 fr_cli.agent.builtins.rag 拆出(原文件 509 行)。
向量检索 -> Top-K 片段 -> 带来源标注的上下文 -> 大模型综合生成。
"""
from __future__ import annotations

import time
from typing import Any, Tuple


class RAGQueryMixin:
    """检索 + 大模型生成"""

    def query(self, question, client, model, lang="zh", top_k=8) -> Tuple[Any, Any]:
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
