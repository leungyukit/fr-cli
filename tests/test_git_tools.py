"""
Git 集成工具测试
覆盖 git_status / git_diff / git_log / git_add / git_commit / git_branch / git_show。

用临时 git 仓库做真实验证。
"""
import os
import sys
import subprocess

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fr_cli.weapon.git_tools import (
    git_status, git_diff, git_log, git_add, git_commit,
    git_branch, git_show, git_is_repo, _run_git,
)


@pytest.fixture
def git_repo(tmp_path):
    """初始化一个临时 git 仓库并配置用户"""
    repo = tmp_path / "repo"
    repo.mkdir()
    # git init
    subprocess.run(["git", "init"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(repo), check=True, capture_output=True)
    # 初始 commit
    (repo / "README.md").write_text("# Test Repo", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=str(repo), check=True, capture_output=True)
    return repo


# ==================== _run_git ====================

class TestRunGit:

    def test_successful_command(self, tmp_path):
        result = _run_git(["status"], cwd=str(tmp_path))
        assert "stdout" in result
        assert "ok" in result

    def test_invalid_command(self, tmp_path):
        result = _run_git(["nonexistent-command"], cwd=str(tmp_path))
        assert result["ok"] is False

    def test_timeout(self, tmp_path):
        """超时配置生效"""
        result = _run_git(["status"], cwd=str(tmp_path), timeout=1)
        assert "ok" in result


# ==================== git_is_repo ====================

class TestGitIsRepo:

    def test_is_repo_true(self, git_repo):
        assert git_is_repo(cwd=str(git_repo)) is True

    def test_is_repo_false(self, tmp_path):
        assert git_is_repo(cwd=str(tmp_path)) is False


# ==================== git_status ====================

class TestGitStatus:

    def test_clean_repo(self, git_repo):
        result = git_status(cwd=str(git_repo))
        assert result["ok"] is True
        assert result["is_repo"] is True
        assert "branch" in result
        # 工作区干净
        assert result["status"] == ""

    def test_with_unstaged_changes(self, git_repo):
        (git_repo / "README.md").write_text("# Modified", encoding="utf-8")
        result = git_status(cwd=str(git_repo))
        assert result["ok"] is True
        assert "M " in result["status"] or " M" in result["status"]

    def test_with_untracked_file(self, git_repo):
        (git_repo / "new.txt").write_text("new", encoding="utf-8")
        result = git_status(cwd=str(git_repo))
        assert "new.txt" in result["status"]

    def test_non_git_dir(self, tmp_path):
        result = git_status(cwd=str(tmp_path))
        assert result["ok"] is False
        assert result["is_repo"] is False


# ==================== git_diff ====================

class TestGitDiff:

    def test_no_diff_clean(self, git_repo):
        result = git_diff(cwd=str(git_repo))
        assert result["ok"] is True
        assert result["diff"] == ""

    def test_show_changes(self, git_repo):
        (git_repo / "README.md").write_text("# Changed", encoding="utf-8")
        result = git_diff(cwd=str(git_repo))
        assert result["ok"] is True
        assert "# Changed" in result["diff"] or "Changed" in result["diff"]

    def test_diff_specific_file(self, git_repo):
        (git_repo / "README.md").write_text("# A", encoding="utf-8")
        (git_repo / "other.txt").write_text("other", encoding="utf-8")
        result = git_diff(cwd=str(git_repo), path="README.md")
        assert result["ok"] is True
        assert "other.txt" not in result["diff"]

    def test_staged_diff(self, git_repo):
        (git_repo / "README.md").write_text("# Staged", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=str(git_repo), check=True, capture_output=True)
        result = git_diff(cwd=str(git_repo), staged=True)
        assert result["ok"] is True
        assert "Staged" in result["diff"]


# ==================== git_log ====================

class TestGitLog:

    def test_log_has_at_least_one_commit(self, git_repo):
        result = git_log(cwd=str(git_repo))
        assert result["ok"] is True
        assert "initial" in result["log"]

    def test_log_with_limit(self, git_repo):
        # 创建额外 commit
        (git_repo / "f1.txt").write_text("1", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=str(git_repo), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "second"], cwd=str(git_repo), check=True, capture_output=True)

        result = git_log(cwd=str(git_repo), limit=1)
        assert result["ok"] is True
        assert "second" in result["log"]
        assert "initial" not in result["log"]

    def test_log_oneline(self, git_repo):
        result = git_log(cwd=str(git_repo), oneline=True)
        assert result["ok"] is True
        assert "initial" in result["log"]


# ==================== git_add ====================

class TestGitAdd:

    def test_add_specific_files(self, git_repo):
        (git_repo / "a.txt").write_text("a", encoding="utf-8")
        result = git_add(cwd=str(git_repo), paths=["a.txt"])
        assert result["ok"] is True

        # 验证 staged
        status = subprocess.run(["git", "status", "--short"], cwd=str(git_repo),
                                capture_output=True, text=True, check=True)
        assert "A  a.txt" in status.stdout

    def test_add_all_default(self, git_repo):
        (git_repo / "a.txt").write_text("a", encoding="utf-8")
        result = git_add(cwd=str(git_repo))  # 不传 paths
        assert result["ok"] is True


# ==================== git_commit ====================

class TestGitCommit:

    def test_commit_empty_message_fails(self, git_repo):
        result = git_commit(cwd=str(git_repo), message="")
        assert result["ok"] is False
        assert "不能为空" in result["error"]

    def test_commit_with_changes(self, git_repo):
        (git_repo / "new.txt").write_text("content", encoding="utf-8")
        result = git_commit(cwd=str(git_repo), message="add new file", add_all=True)
        assert result["ok"] is True

        # 验证 commit 存在
        log = subprocess.run(["git", "log", "--oneline"], cwd=str(git_repo),
                             capture_output=True, text=True, check=True)
        assert "add new file" in log.stdout

    def test_commit_with_explicit_add(self, git_repo):
        (git_repo / "b.txt").write_text("b", encoding="utf-8")
        result = git_commit(cwd=str(git_repo), message="add b", add_all=False)
        # add_all=False 但有 add 失败
        assert result["ok"] is False

    def test_commit_nothing_to_commit(self, git_repo):
        result = git_commit(cwd=str(git_repo), message="nothing")
        assert result["ok"] is False  # 没有变更


# ==================== git_branch ====================

class TestGitBranch:

    def test_list_branches(self, git_repo):
        result = git_branch(cwd=str(git_repo), action="list")
        assert result["ok"] is True
        assert "main" in result["branches"] or "master" in result["branches"]

    def test_create_branch(self, git_repo):
        result = git_branch(cwd=str(git_repo), action="create", name="feature-x")
        assert result["ok"] is True

        # 验证分支存在
        result2 = git_branch(cwd=str(git_repo), action="list")
        assert "feature-x" in result2["branches"]

    def test_create_without_name_fails(self, git_repo):
        result = git_branch(cwd=str(git_repo), action="create")
        assert result["ok"] is False

    def test_checkout_branch(self, git_repo):
        git_branch(cwd=str(git_repo), action="create", name="dev")
        result = git_branch(cwd=str(git_repo), action="checkout", name="dev")
        assert result["ok"] is True

    def test_delete_branch(self, git_repo):
        git_branch(cwd=str(git_repo), action="create", name="to-delete")
        # 先切换回主分支
        main_branch = git_branch(cwd=str(git_repo))["current"]
        git_branch(cwd=str(git_repo), action="checkout", name=main_branch)
        result = git_branch(cwd=str(git_repo), action="delete", name="to-delete")
        assert result["ok"] is True

    def test_unknown_action(self, git_repo):
        result = git_branch(cwd=str(git_repo), action="invalid")
        assert result["ok"] is False


# ==================== git_show ====================

class TestGitShow:

    def test_show_head(self, git_repo):
        result = git_show(cwd=str(git_repo), ref="HEAD")
        assert result["ok"] is True
        assert "initial" in result["output"]
        assert "Tester" in result["output"]


# ==================== 工具注册 ====================

class TestToolRegistration:

    def test_git_status_registered(self):
        """git_status 工具应在 registry 中"""
        from fr_cli.command.registry import get_registry
        reg = get_registry()
        tools = getattr(reg, "_tools", {})
        assert "git_status" in tools

    def test_all_git_tools_registered(self):
        """7 个 git 工具都应注册"""
        from fr_cli.command.registry import get_registry
        reg = get_registry()
        tools = getattr(reg, "_tools", {})
        for name in ["git_status", "git_diff", "git_log", "git_add",
                     "git_commit", "git_branch", "git_show"]:
            assert name in tools, f"{name} 未注册"
