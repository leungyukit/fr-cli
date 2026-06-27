"""
项目记忆自动加载测试 —— .frcli.md / AGENTS.md / CLAUDE.md

覆盖:
- 向上回溯找到项目记忆文件
- 多个文件优先级
- 文件不存在 / 空目录
- 注入到 system prompt 的格式
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fr_cli.agent.project_memory import (
    find_project_memory_files,
    build_project_memory_section,
    should_inject_memory,
    _find_git_root,
    _is_git_root,
)


# ==================== 基础文件查找 ====================

class TestFindMemoryFiles:

    def test_no_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        files = find_project_memory_files()
        assert files == []

    def test_find_frcli_md(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".frcli.md").write_text("# 项目说明\n这是一个测试项目", encoding="utf-8")
        files = find_project_memory_files()
        assert len(files) == 1
        assert files[0][0].name == ".frcli.md"
        assert "测试项目" in files[0][1]

    def test_find_agents_md(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "AGENTS.md").write_text("agent guide", encoding="utf-8")
        files = find_project_memory_files()
        assert len(files) == 1
        assert files[0][0].name == "AGENTS.md"

    def test_find_claude_md(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "CLAUDE.md").write_text("claude guide", encoding="utf-8")
        files = find_project_memory_files()
        assert len(files) == 1

    def test_find_github_agents(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        gh_dir = tmp_path / ".github"
        gh_dir.mkdir()
        (gh_dir / "AGENTS.md").write_text("github agents", encoding="utf-8")
        files = find_project_memory_files()
        assert len(files) == 1

    def test_priority_frcli_over_agents(self, tmp_path, monkeypatch):
        """多个文件存在时按优先级 .frcli.md > AGENTS.md > CLAUDE.md"""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "AGENTS.md").write_text("agents content", encoding="utf-8")
        (tmp_path / "CLAUDE.md").write_text("claude content", encoding="utf-8")
        (tmp_path / ".frcli.md").write_text("frcli content", encoding="utf-8")
        files = find_project_memory_files()
        # .frcli.md 应在第一位
        assert ".frcli.md" in str(files[0][0])

    def test_empty_file_ignored(self, tmp_path, monkeypatch):
        """空文件不应被加载"""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".frcli.md").write_text("   \n\n  ", encoding="utf-8")
        files = find_project_memory_files()
        assert files == []

    def test_directory_walk_up(self, tmp_path, monkeypatch):
        """从子目录向上找父目录的文件"""
        sub = tmp_path / "src" / "lib"
        sub.mkdir(parents=True)
        (tmp_path / ".frcli.md").write_text("root project", encoding="utf-8")
        monkeypatch.chdir(sub)
        files = find_project_memory_files()
        assert len(files) >= 1
        assert "root project" in files[0][1]


# ==================== Git Root 行为 ====================

class TestGitRoot:

    def test_find_git_root(self, tmp_path):
        """找到 git root"""
        (tmp_path / ".git").mkdir()
        sub = tmp_path / "a" / "b"
        sub.mkdir(parents=True)
        root = _find_git_root(sub)
        assert root == tmp_path

    def test_no_git_root(self, tmp_path):
        """没 .git 时返回 None"""
        sub = tmp_path / "a"
        sub.mkdir()
        root = _find_git_root(sub)
        assert root is None

    def test_is_git_root(self, tmp_path):
        (tmp_path / ".git").mkdir()
        assert _is_git_root(tmp_path) is True

        sub = tmp_path / "sub"
        sub.mkdir()
        assert _is_git_root(sub) is False


# ==================== 注入格式 ====================

class TestBuildMemorySection:

    def test_no_files_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        section = build_project_memory_section()
        assert section == ""

    def test_single_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".frcli.md").write_text("hello world", encoding="utf-8")
        section = build_project_memory_section()
        assert "Project Memory" in section
        assert "hello world" in section

    def test_includes_filename(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".frcli.md").write_text("content", encoding="utf-8")
        section = build_project_memory_section()
        assert ".frcli.md" in section

    def test_truncates_long_content(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        long_content = "x" * 10000
        (tmp_path / ".frcli.md").write_text(long_content, encoding="utf-8")
        section = build_project_memory_section()
        # 4000 字符上限截断
        assert "truncated" in section
        assert len(section) < 12000

    def test_truncates_total(self, tmp_path, monkeypatch):
        """多个文件总长超出 16000 字符应截断"""
        monkeypatch.chdir(tmp_path)
        for i in range(10):
            (tmp_path / f".frcli-{i}.md").write_text("y" * 3000, encoding="utf-8")
        section = build_project_memory_section()
        # 应不超过 16000 字符 + 一些标题
        assert len(section) < 17000


class TestShouldInject:

    def test_no_files_no_inject(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert should_inject_memory() is False

    def test_has_files_yes_inject(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".frcli.md").write_text("x", encoding="utf-8")
        assert should_inject_memory() is True


# ==================== 集成:在 MasterAgent prompt 中 ====================

class TestIntegrationWithMasterAgent:

    def test_memory_loaded_into_prompt(self, tmp_path, monkeypatch):
        """验证 memory 真的进了 system prompt — 直接测 build_project_memory_section 输出格式"""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / ".frcli.md").write_text("测试项目说明", encoding="utf-8")
        monkeypatch.chdir(project_dir)

        section = build_project_memory_section()
        # section 字符串的格式应能被 MasterAgent prompt_builder 直接附加
        assert "Project Memory" in section
        assert "测试项目说明" in section
        # 格式应包含文件路径标签
        assert ".frcli.md" in section
        # 应包含引导文字
        assert "项目记忆" in section or "记忆" in section