"""RAG 持久化缓存测试"""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fr_cli.agent.builtins.rag import RAGManager


class TestPersistentCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="test_rag_persist_")
        # patch ROOT 让缓存写到 tmp
        self.patcher = patch("fr_cli.conf.paths.ROOT", Path(self.tmp))

    def tearDown(self):
        self.patcher.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_init_with_persist(self):
        with self.patcher:
            rag = RAGManager(persist_cache=True)
            self.assertTrue(rag._persist_cache)
            self.assertIsNotNone(rag._persist_path)
            self.assertIn(str(self.tmp), rag._persist_path)

    def test_enable_persist_later(self):
        with self.patcher:
            rag = RAGManager(persist_cache=False)
            self.assertFalse(rag._persist_cache)
            result = rag.enable_persistent_cache(True)
            self.assertTrue(result)
            self.assertTrue(rag._persist_cache)

    def test_flush_and_load(self):
        with self.patcher:
            rag = RAGManager(persist_cache=True)
            # 写缓存
            rag._query_cache["key1"] = (time.time(), ("answer1", None))
            rag._flush_persistent_cache()

            # 验证磁盘文件存在
            self.assertTrue(os.path.exists(rag._persist_path))

            # 新实例应该能加载
            rag2 = RAGManager(persist_cache=True)
            self.assertIn("key1", rag2._query_cache)

    def test_load_skips_expired(self):
        with self.patcher:
            rag = RAGManager(persist_cache=True)
            rag._query_cache["expired"] = (time.time() - 1000, ("old", None))
            rag._query_cache["valid"] = (time.time(), ("new", None))
            rag._flush_persistent_cache()

            rag2 = RAGManager(persist_cache=True)
            self.assertNotIn("expired", rag2._query_cache)
            self.assertIn("valid", rag2._query_cache)

    def test_clear_cache_removes_file(self):
        with self.patcher:
            rag = RAGManager(persist_cache=True)
            rag._query_cache["k"] = (time.time(), ("v", None))
            rag._flush_persistent_cache()
            self.assertTrue(os.path.exists(rag._persist_path))

            rag.clear_cache()
            self.assertFalse(os.path.exists(rag._persist_path))

    def test_stats_includes_persist_info(self):
        with self.patcher:
            rag = RAGManager(persist_cache=True)
            stats = rag.cache_stats()
            self.assertIn("persist_enabled", stats)
            self.assertIn("persist_path", stats)
            self.assertTrue(stats["persist_enabled"])

    def test_load_when_file_missing(self):
        with self.patcher:
            rag = RAGManager(persist_cache=True)
            # 不写文件
            rag._load_persistent_cache()
            # 不应该报错
            self.assertEqual(len(rag._query_cache), 0)


if __name__ == "__main__":
    unittest.main()