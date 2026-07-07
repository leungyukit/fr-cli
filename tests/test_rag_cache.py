"""RAG 缓存测试"""
import time
import unittest

from fr_cli.agent.builtins.rag import RAGManager


class TestRAGCache(unittest.TestCase):
    def setUp(self):
        self.rag = RAGManager()

    def test_initial_state(self):
        stats = self.rag.cache_stats()
        self.assertEqual(stats["total"], 0)
        self.assertEqual(stats["ttl_seconds"], 600)
        self.assertEqual(stats["max_entries"], 128)

    def test_write_and_read_cache(self):
        key = self.rag._query_cache_key("test question", 8, "zh")
        self.rag._write_cache(key, ("answer", None))
        stats = self.rag.cache_stats()
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["valid"], 1)

    def test_clear_cache(self):
        key = self.rag._query_cache_key("q", 8, "zh")
        self.rag._write_cache(key, ("a", None))
        self.assertEqual(self.rag.cache_stats()["total"], 1)
        n = self.rag.clear_cache()
        self.assertEqual(n, 1)
        self.assertEqual(self.rag.cache_stats()["total"], 0)

    def test_cache_key_consistency(self):
        k1 = self.rag._query_cache_key("hello", 8, "zh")
        k2 = self.rag._query_cache_key("hello", 8, "zh")
        self.assertEqual(k1, k2)

    def test_cache_key_different_params(self):
        k1 = self.rag._query_cache_key("hello", 8, "zh")
        k2 = self.rag._query_cache_key("hello", 5, "zh")  # 不同 top_k
        k3 = self.rag._query_cache_key("hello", 8, "en")  # 不同 lang
        k4 = self.rag._query_cache_key("world", 8, "zh")  # 不同 question
        self.assertNotEqual(k1, k2)
        self.assertNotEqual(k1, k3)
        self.assertNotEqual(k1, k4)

    def test_cache_key_too_long(self):
        long_q = "x" * 3000
        key = self.rag._query_cache_key(long_q, 8, "zh")
        self.assertTrue(key.startswith("_nocache_"))

    def test_cache_key_unsupported_lang(self):
        key = self.rag._query_cache_key("hi", 8, "klingon")
        self.assertTrue(key.startswith("_nocache_"))

    def test_expired_entries(self):
        # 写入一条立刻过期的(模拟)
        key = "manual_test"
        self.rag._query_cache[key] = (time.time() - 700, ("old", None))  # 700s 前
        stats = self.rag.cache_stats()
        self.assertEqual(stats["expired"], 1)
        self.assertEqual(stats["valid"], 0)

    def test_cache_eviction(self):
        # 把 max 调小便于测试
        self.rag._cache_max = 10
        # 写满
        for i in range(10):
            key = f"key_{i}"
            self.rag._write_cache(key, (f"answer_{i}", None))
        # 再写一个,触发 LRU 清理
        self.rag._write_cache("key_new", ("new_answer", None))
        stats = self.rag.cache_stats()
        # 应该清掉了一些旧 key
        self.assertLess(stats["total"], 11)

    def test_no_cache_write_for_nocache_key(self):
        # _nocache_ 前缀的 key 不写
        self.rag._write_cache("_nocache_test", ("x", None))
        self.assertEqual(self.rag.cache_stats()["total"], 0)


if __name__ == "__main__":
    unittest.main()
