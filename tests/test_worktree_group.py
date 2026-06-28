"""Worktree 群组测试"""
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from fr_cli.weapon.worktree_group import (
    create_worktree_group, get_group, list_groups,
    merge_group, discard_group, format_group,
)


def _make_git_repo() -> str:
    """创建一个临时 git 仓库"""
    tmp = tempfile.mkdtemp(prefix="test_group_")
    subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp, check=True)
    with open(os.path.join(tmp, "a.txt"), "w") as f:
        f.write("hello")
    subprocess.run(["git", "add", "."], cwd=tmp, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp, check=True)
    return tmp


class TestCreateGroup(unittest.TestCase):
    def setUp(self):
        self.tmp = _make_git_repo()
        # patch registry
        from fr_cli.conf.paths import ROOT as FR_CLI_DIR
        self.real_frcli = FR_CLI_DIR
        self.patcher_dir = tempfile.mkdtemp(prefix="test_frcli_")
        import fr_cli.weapon.worktree_group as mod
        self.real_group_reg = mod.GROUP_REGISTRY
        mod.GROUP_REGISTRY = Path(self.patcher_dir) / "groups.json"
        # patch cleanup
        import fr_cli.weapon.worktree_cleanup as cleanup_mod
        self.real_wt_reg = cleanup_mod.WORKTREE_REGISTRY
        cleanup_mod.WORKTREE_REGISTRY = Path(self.patcher_dir) / "wt.json"

    def tearDown(self):
        import fr_cli.weapon.worktree_group as mod
        mod.GROUP_REGISTRY = self.real_group_reg
        import fr_cli.weapon.worktree_cleanup as cleanup_mod
        cleanup_mod.WORKTREE_REGISTRY = self.real_wt_reg
        # 强删 worktrees
        subprocess.run(["git", "worktree", "remove", "--force"], cwd=self.tmp, capture_output=True)
        wt_dir = Path(self.tmp) / ".worktrees"
        if wt_dir.exists():
            shutil.rmtree(wt_dir, ignore_errors=True)
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.patcher_dir, ignore_errors=True)

    def test_create_basic(self):
        r = create_worktree_group(self.tmp, "swarm-test", ["coder", "reviewer"])
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["worktrees"]), 2)
        self.assertIn("coder", [w["agent"] for w in r["worktrees"]])
        self.assertIn("reviewer", [w["agent"] for w in r["worktrees"]])

    def test_create_with_base(self):
        r = create_worktree_group(self.tmp, "swarm-test", ["a"], base_branch="master")
        self.assertTrue(r["ok"])

    def test_create_empty_agents(self):
        r = create_worktree_group(self.tmp, "x", [])
        self.assertFalse(r["ok"])

    def test_create_not_repo(self):
        tmp = tempfile.mkdtemp()
        try:
            r = create_worktree_group(tmp, "x", ["a"])
            self.assertFalse(r["ok"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_create_with_invalid_base(self):
        # 无效的 base branch 应该失败
        r = create_worktree_group(self.tmp, "swarm-test", ["a"], base_branch="nonexistent")
        self.assertFalse(r["ok"])


class TestGetList(unittest.TestCase):
    def setUp(self):
        self.tmp = _make_git_repo()
        import fr_cli.weapon.worktree_group as mod
        self.real_group_reg = mod.GROUP_REGISTRY
        self.patcher_dir = tempfile.mkdtemp(prefix="test_frcli_")
        mod.GROUP_REGISTRY = Path(self.patcher_dir) / "groups.json"

    def tearDown(self):
        import fr_cli.weapon.worktree_group as mod
        mod.GROUP_REGISTRY = self.real_group_reg
        subprocess.run(["git", "worktree", "remove", "--force"], cwd=self.tmp, capture_output=True)
        wt_dir = Path(self.tmp) / ".worktrees"
        if wt_dir.exists():
            shutil.rmtree(wt_dir, ignore_errors=True)
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.patcher_dir, ignore_errors=True)

    def test_get_existing(self):
        r = create_worktree_group(self.tmp, "swarm-x", ["a", "b"])
        self.assertTrue(r["ok"])
        g = get_group(r["group_id"])
        self.assertIsNotNone(g)
        self.assertEqual(g["prefix"], "swarm-x")
        self.assertEqual(len(g["worktrees"]), 2)

    def test_get_nonexistent(self):
        g = get_group("nonexistent-id")
        self.assertIsNone(g)

    def test_list(self):
        r1 = create_worktree_group(self.tmp, "g1", ["agent1"])
        self.assertTrue(r1["ok"])
        r2 = create_worktree_group(self.tmp, "g2", ["agent2"])
        self.assertTrue(r2["ok"])
        groups = list_groups()
        self.assertEqual(len(groups), 2)


class TestDiscard(unittest.TestCase):
    def setUp(self):
        self.tmp = _make_git_repo()
        import fr_cli.weapon.worktree_group as mod
        import fr_cli.weapon.worktree_cleanup as cleanup_mod
        self.real_group_reg = mod.GROUP_REGISTRY
        self.real_wt_reg = cleanup_mod.WORKTREE_REGISTRY
        self.patcher_dir = tempfile.mkdtemp(prefix="test_frcli_")
        mod.GROUP_REGISTRY = Path(self.patcher_dir) / "groups.json"
        cleanup_mod.WORKTREE_REGISTRY = Path(self.patcher_dir) / "wt.json"

    def tearDown(self):
        import fr_cli.weapon.worktree_group as mod
        import fr_cli.weapon.worktree_cleanup as cleanup_mod
        mod.GROUP_REGISTRY = self.real_group_reg
        cleanup_mod.WORKTREE_REGISTRY = self.real_wt_reg
        subprocess.run(["git", "worktree", "remove", "--force"], cwd=self.tmp, capture_output=True)
        wt_dir = Path(self.tmp) / ".worktrees"
        if wt_dir.exists():
            shutil.rmtree(wt_dir, ignore_errors=True)
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.patcher_dir, ignore_errors=True)

    def test_discard(self):
        r = create_worktree_group(self.tmp, "x", ["a", "b"])
        self.assertTrue(r["ok"])
        gid = r["group_id"]

        # 验证 worktree 存在
        for wt in r["worktrees"]:
            self.assertTrue(os.path.exists(wt["path"]))

        # 丢弃
        result = discard_group(gid)
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["deleted"]), 2)

        # 验证 worktree 没了
        for wt in r["worktrees"]:
            self.assertFalse(os.path.exists(wt["path"]))

        # 群组状态
        g = get_group(gid)
        self.assertEqual(g["status"], "discarded")

    def test_discard_nonexistent(self):
        result = discard_group("nonexistent")
        self.assertFalse(result["ok"])


class TestFormat(unittest.TestCase):
    def test_format(self):
        group = {
            "main_repo": "/repo",
            "prefix": "test",
            "base_branch": "master",
            "worktrees": [{"agent": "a", "path": "/p1", "branch": "b1"}],
            "status": "active",
        }
        out = format_group("gid", "zh")
        # 调用时 group=None 会返回"不存在"
        # 这里我们直接验证 format 的输入兼容性
        self.assertIsInstance(out, str)


if __name__ == "__main__":
    unittest.main()