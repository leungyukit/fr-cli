"""Worktree 自动清理测试"""
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from fr_cli.weapon.worktree_cleanup import (
    register_worktree, unregister_worktree, touch_worktree,
    list_worktrees_for_cleanup, find_idle_worktrees,
    clean_idle_worktrees, _find_repo_root_for_wt,
    format_cleanup_report,
)


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="test_wtc_")
        self.rp = Path(self.tmp) / "registry.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_register(self):
        result = register_worktree("/p1", "b1", auto_clean=True, registry_path=self.rp)
        self.assertTrue(result)
        wts = list_worktrees_for_cleanup(self.rp)
        self.assertEqual(len(wts), 1)
        self.assertEqual(wts[0]["branch"], "b1")

    def test_register_twice_updates(self):
        register_worktree("/p1", "b1", registry_path=self.rp)
        register_worktree("/p1", "b1-renamed", registry_path=self.rp)
        wts = list_worktrees_for_cleanup(self.rp)
        self.assertEqual(len(wts), 1)
        self.assertEqual(wts[0]["branch"], "b1-renamed")

    def test_unregister(self):
        register_worktree("/p1", "b1", registry_path=self.rp)
        register_worktree("/p2", "b2", registry_path=self.rp)
        unregister_worktree("/p1", registry_path=self.rp)
        wts = list_worktrees_for_cleanup(self.rp)
        self.assertEqual(len(wts), 1)
        self.assertEqual(wts[0]["path"], "/p2")

    def test_touch(self):
        register_worktree("/p1", "b1", registry_path=self.rp)
        wts = list_worktrees_for_cleanup(self.rp)
        original_ts = wts[0]["last_used_at"]
        time.sleep(0.1)
        result = touch_worktree("/p1", registry_path=self.rp)
        self.assertTrue(result)
        wts = list_worktrees_for_cleanup(self.rp)
        self.assertGreater(wts[0]["last_used_at"], original_ts)

    def test_touch_nonexistent(self):
        result = touch_worktree("/nope", registry_path=self.rp)
        self.assertFalse(result)


class TestFindIdle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="test_idle_")
        self.rp = Path(self.tmp) / "registry.json"
        # 真实存在的路径(因为 find_idle 会检查路径存在性)
        self.real_path = Path(self.tmp) / "fake_wt"
        self.real_path.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_find_idle_old(self):
        register_worktree(str(self.real_path), "b1", registry_path=self.rp)
        # 直接修改文件
        from fr_cli.core.store import JsonStore
        data = JsonStore(str(self.rp), default=dict).read()
        data["worktrees"][0]["last_used_at"] = time.time() - 10 * 86400
        JsonStore(str(self.rp), default=dict).write(data)

        idle = find_idle_worktrees(idle_days=7, registry_path=self.rp)
        self.assertEqual(len(idle), 1)
        self.assertIn("空闲", idle[0]["reason"])

    def test_find_idle_none(self):
        register_worktree(str(self.real_path), "b1", registry_path=self.rp)
        idle = find_idle_worktrees(idle_days=7, registry_path=self.rp)
        self.assertEqual(len(idle), 0)

    def test_find_idle_no_auto_clean(self):
        register_worktree(str(self.real_path), "b1", auto_clean=False, registry_path=self.rp)
        from fr_cli.core.store import JsonStore
        data = JsonStore(str(self.rp), default=dict).read()
        data["worktrees"][0]["last_used_at"] = time.time() - 10 * 86400
        JsonStore(str(self.rp), default=dict).write(data)

        idle = find_idle_worktrees(idle_days=7, registry_path=self.rp)
        self.assertEqual(len(idle), 0)

    def test_find_orphan(self):
        """路径不存在 = 孤儿"""
        register_worktree("/nonexistent/path", "b1", registry_path=self.rp)
        idle = find_idle_worktrees(idle_days=7, registry_path=self.rp)
        self.assertEqual(len(idle), 1)
        self.assertIn("不存在", idle[0]["reason"])


class TestCleanup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="test_cleanup_")
        self.rp = Path(self.tmp) / "registry.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_dry_run(self):
        register_worktree("/nonexistent/path", "b1", registry_path=self.rp)
        from fr_cli.core.store import JsonStore
        data = JsonStore(str(self.rp), default=dict).read()
        data["worktrees"][0]["last_used_at"] = time.time() - 10 * 86400
        JsonStore(str(self.rp), default=dict).write(data)

        report = clean_idle_worktrees(idle_days=7, dry_run=True, registry_path=self.rp)
        self.assertEqual(len(report["cleaned"]), 0)
        self.assertEqual(len(report["skipped"]), 1)
        self.assertTrue(report["dry_run"])

    def test_real_cleanup_orphan(self):
        register_worktree("/nonexistent/path", "b1", registry_path=self.rp)
        from fr_cli.core.store import JsonStore
        data = JsonStore(str(self.rp), default=dict).read()
        data["worktrees"][0]["last_used_at"] = time.time() - 10 * 86400
        JsonStore(str(self.rp), default=dict).write(data)

        report = clean_idle_worktrees(idle_days=7, registry_path=self.rp)
        self.assertEqual(len(report["cleaned"]), 1)
        self.assertEqual(report["cleaned"][0]["path"], "/nonexistent/path")


class TestFindRepoRoot(unittest.TestCase):
    def test_under_dotworktrees(self):
        result = _find_repo_root_for_wt("/repo/.worktrees/feat-x")
        self.assertEqual(result, "/repo")

    def test_via_git_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp) / "main"
            wt = Path(tmp) / "main" / ".worktrees" / "feat"
            wt.mkdir(parents=True)
            git_file = wt / ".git"
            git_file.write_text(f"gitdir: {main}/.git/worktrees/feat")

            result = _find_repo_root_for_wt(str(wt))
            self.assertEqual(result, str(main))

    def test_unknown(self):
        result = _find_repo_root_for_wt("/random/path/no/git")
        self.assertIsNone(result)


class TestFormatReport(unittest.TestCase):
    def test_zh_empty(self):
        report = {"cleaned": [], "skipped": [], "errors": [], "dry_run": False, "idle_days_threshold": 7}
        out = format_cleanup_report(report, "zh")
        self.assertIn("Worktree", out)

    def test_en_with_cleaned(self):
        report = {"cleaned": [{"path": "/p1", "branch": "b1", "method": "git"}],
                  "skipped": [], "errors": [], "dry_run": False, "idle_days_threshold": 7}
        out = format_cleanup_report(report, "en")
        self.assertIn("Cleaned", out)
        self.assertIn("/p1", out)


if __name__ == "__main__":
    unittest.main()
