"""worktree 工具测试"""
import os
import shutil
import subprocess
import tempfile
import unittest

from fr_cli.weapon.worktree import (
    worktree_is_repo, worktree_list, worktree_create,
    worktree_remove, worktree_prune, format_worktree_list,
)


def _make_temp_repo() -> str:
    """创建一个临时 git 仓库用于测试"""
    tmp = tempfile.mkdtemp(prefix="test_wt_")
    subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=tmp, check=True)
    with open(os.path.join(tmp, "a.txt"), "w") as f:
        f.write("hello")
    subprocess.run(["git", "add", "."], cwd=tmp, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp, check=True)
    return tmp


class TestWorktreeBasics(unittest.TestCase):
    def setUp(self):
        self.tmp = _make_temp_repo()

    def tearDown(self):
        # 强制清理 worktree
        subprocess.run(["git", "worktree", "remove", "--force"],
                       cwd=self.tmp, capture_output=True)
        # 尝试移除 worktree 目录
        wt_dir = os.path.join(self.tmp, ".worktrees")
        if os.path.exists(wt_dir):
            shutil.rmtree(wt_dir, ignore_errors=True)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_is_repo(self):
        self.assertTrue(worktree_is_repo(self.tmp))

    def test_not_repo(self):
        not_repo = tempfile.mkdtemp()
        try:
            self.assertFalse(worktree_is_repo(not_repo))
        finally:
            shutil.rmtree(not_repo, ignore_errors=True)

    def test_list_initial(self):
        result = worktree_list(self.tmp)
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["worktrees"]), 1)
        self.assertEqual(result["worktrees"][0]["branch"], "master")

    def test_create_branch(self):
        result = worktree_create(cwd=self.tmp, branch="feat-test")
        self.assertTrue(result["ok"])
        self.assertIn("feat-test", result["path"])
        self.assertTrue(os.path.exists(result["path"]))

    def test_create_with_path(self):
        custom = os.path.join(self.tmp, "my-custom-wt")
        result = worktree_create(cwd=self.tmp, path=custom)
        self.assertTrue(result["ok"])
        self.assertEqual(result["path"], custom)

    def test_create_with_base(self):
        result = worktree_create(cwd=self.tmp, branch="from-master", base="master")
        self.assertTrue(result["ok"])

    def test_create_no_branch_no_path(self):
        result = worktree_create(cwd=self.tmp)
        self.assertFalse(result["ok"])
        self.assertIn("需要提供", result["error"])

    def test_create_detach(self):
        result = worktree_create(cwd=self.tmp, branch="tmp-wt", detach=True)
        self.assertTrue(result["ok"])

    def test_remove(self):
        create = worktree_create(cwd=self.tmp, branch="to-remove")
        self.assertTrue(create["ok"])
        rem = worktree_remove(cwd=self.tmp, path=create["path"])
        self.assertTrue(rem["ok"])
        self.assertFalse(os.path.exists(create["path"]))

    def test_remove_nonexistent(self):
        rem = worktree_remove(cwd=self.tmp, path="/nope/nonexistent")
        self.assertFalse(rem["ok"])

    def test_remove_no_path(self):
        rem = worktree_remove(cwd=self.tmp)
        self.assertFalse(rem["ok"])

    def test_remove_force(self):
        create = worktree_create(cwd=self.tmp, branch="with-changes")
        # 在 worktree 里加一个未提交的文件
        with open(os.path.join(create["path"], "untracked.txt"), "w") as f:
            f.write("dirty")
        rem = worktree_remove(cwd=self.tmp, path=create["path"], force=True)
        self.assertTrue(rem["ok"])

    def test_prune(self):
        result = worktree_prune(cwd=self.tmp)
        self.assertTrue(result["ok"])

    def test_list_after_operations(self):
        worktree_create(cwd=self.tmp, branch="a")
        worktree_create(cwd=self.tmp, branch="b")
        result = worktree_list(self.tmp)
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["worktrees"]), 3)

    def test_not_repo_operations(self):
        not_repo = tempfile.mkdtemp()
        try:
            r1 = worktree_list(not_repo)
            self.assertFalse(r1["ok"])
            r2 = worktree_create(cwd=not_repo, branch="x")
            self.assertFalse(r2["ok"])
        finally:
            shutil.rmtree(not_repo, ignore_errors=True)


class TestWorktreeFormatting(unittest.TestCase):
    def test_format_empty(self):
        out = format_worktree_list([])
        self.assertIn("无", out)

    def test_format_one(self):
        wts = [{"path": "/p1", "head": "abc123def", "branch": "main"}]
        out = format_worktree_list(wts)
        self.assertIn("/p1", out)
        self.assertIn("main", out)
        self.assertIn("abc123de", out)

    def test_format_with_current_marker(self):
        wts = [{"path": "/p1", "head": "abc", "branch": "main"}]
        out = format_worktree_list(wts, current_cwd="/p1")
        self.assertIn("当前", out)


if __name__ == "__main__":
    unittest.main()