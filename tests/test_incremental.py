"""增量持久化测试"""
import os
import tempfile
import unittest

from fr_cli.memory.incremental import (
    IncrementalSessionWriter, update_session_incremental,
    read_session_full_data,
)


class TestIncrementalWriter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="test_inc_")
        self.snap_path = os.path.join(self.tmp, "session.json")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_initial_state(self):
        w = IncrementalSessionWriter(self.snap_path)
        self.assertEqual(w._read_meta().get("delta_count", 0), 0)
        self.assertEqual(len(w.read_all()), 0)

    def test_append_single(self):
        w = IncrementalSessionWriter(self.snap_path)
        msgs = [{"role": "user", "content": "hi"}]
        result = w.append(msgs)
        self.assertFalse(result["snapshot_triggered"])
        self.assertEqual(result["delta_count"], 1)
        self.assertEqual(len(w.read_all()), 1)

    def test_append_multiple(self):
        w = IncrementalSessionWriter(self.snap_path)
        for i in range(5):
            w.append([{"role": "user", "content": f"msg-{i}"}])
        self.assertEqual(len(w.read_all()), 5)

    def test_snapshot_trigger(self):
        w = IncrementalSessionWriter(self.snap_path, threshold=3)
        for i in range(3):
            w.append([{"role": "user", "content": f"msg-{i}"}])
        # 触发 snapshot
        result = w.append([{"role": "user", "content": "msg-3"}])
        self.assertFalse(result["snapshot_triggered"])  # 这次没触发

        # 累积到 4 + 3-threshold = 触发
        w.append([{"role": "user", "content": "msg-4"}])
        w.append([{"role": "user", "content": "msg-5"}])

        # 再 append 应该会触发
        result = w.append([{"role": "user", "content": "msg-6"}])
        # 累计 delta_count 应该 <= threshold
        self.assertLessEqual(result["delta_count"], 3)

    def test_force_snapshot(self):
        w = IncrementalSessionWriter(self.snap_path, threshold=10)
        for i in range(3):
            w.append([{"role": "user", "content": f"msg-{i}"}])
        # 强制 snapshot
        n = w.snapshot_now()
        self.assertEqual(n, 3)
        self.assertEqual(w._read_meta().get("delta_count"), 0)
        self.assertEqual(len(w.read_all()), 3)

    def test_force_snapshot_empty(self):
        w = IncrementalSessionWriter(self.snap_path)
        n = w.snapshot_now()
        self.assertEqual(n, 0)

    def test_read_after_snapshot(self):
        w = IncrementalSessionWriter(self.snap_path, threshold=2)
        w.append([{"role": "user", "content": "1"}])
        w.append([{"role": "user", "content": "2"}])
        # 触发 snapshot
        w.append([{"role": "user", "content": "3"}])
        all_msgs = w.read_all()
        # snapshot + delta 一起
        self.assertGreaterEqual(len(all_msgs), 3)

    def test_stats(self):
        w = IncrementalSessionWriter(self.snap_path)
        w.append([{"role": "user", "content": "hi"}])
        stats = w.stats()
        self.assertIn("snapshot_size_bytes", stats)
        self.assertIn("delta_size_bytes", stats)
        self.assertEqual(stats["delta_count"], 1)

    def test_clear_cache_helper(self):
        result = update_session_incremental(self.snap_path, [])
        self.assertTrue(result["ok"])


class TestCompatibility(unittest.TestCase):
    """测试向后兼容旧的全量格式"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="test_compat_")
        self.snap_path = os.path.join(self.tmp, "old.json")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_old_format_read(self):
        import json
        # 写一个旧格式(没有 version 字段)
        with open(self.snap_path, "w", encoding="utf-8") as f:
            json.dump({
                "filename": "old.json",
                "messages": [{"role": "user", "content": "old"}],
            }, f, ensure_ascii=False)
        data = read_session_full_data(self.snap_path)
        self.assertEqual(len(data["messages"]), 1)
        self.assertEqual(data["messages"][0]["content"], "old")

    def test_v2_format_read(self):
        w = IncrementalSessionWriter(self.snap_path)
        w.append([{"role": "user", "content": "v2"}])
        data = read_session_full_data(self.snap_path)
        self.assertEqual(data["version"], 2)
        self.assertEqual(len(data["messages"]), 1)


if __name__ == "__main__":
    unittest.main()
