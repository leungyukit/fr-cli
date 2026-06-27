"""
MultiEdit 工具测试 —— atomic multi-file edit

覆盖:
- 单文件多个 edit
- 多文件混合 edit
- 失败回滚(任一文件失败 → 全部不写)
- 正则 + 字面量混合
- 错误路径
"""
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fr_cli.command.registered.fs import _multi_edit


@pytest.fixture
def vfs_with_files(tmp_path):
    """构造 VFS + 几个文件"""
    from fr_cli.weapon.fs import VFS
    vfs = VFS([str(tmp_path)])
    vfs.cd(str(tmp_path), "zh")
    return vfs


@pytest.fixture
def deps(vfs_with_files):
    mock_deps = MagicMock()
    mock_deps.vfs = vfs_with_files
    mock_deps.lang = "zh"
    return mock_deps


class TestMultiEditBasic:

    def test_single_file_single_edit(self, deps, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("hello world", encoding="utf-8")
        edits = [{"path": "a.txt", "old_text": "world", "new_text": "fr-cli"}]
        result = _multi_edit(deps, edits=edits)
        assert result.is_ok()
        assert f.read_text(encoding="utf-8") == "hello fr-cli"

    def test_single_file_multiple_edits(self, deps, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("aaa bbb ccc", encoding="utf-8")
        edits = [
            {"path": "a.txt", "old_text": "aaa", "new_text": "111"},
            {"path": "a.txt", "old_text": "bbb", "new_text": "222"},
            {"path": "a.txt", "old_text": "ccc", "new_text": "333"},
        ]
        result = _multi_edit(deps, edits=edits)
        assert result.is_ok()
        assert f.read_text(encoding="utf-8") == "111 222 333"

    def test_multiple_files(self, deps, tmp_path):
        (tmp_path / "a.txt").write_text("hello a", encoding="utf-8")
        (tmp_path / "b.txt").write_text("hello b", encoding="utf-8")
        edits = [
            {"path": "a.txt", "old_text": "hello", "new_text": "HI"},
            {"path": "b.txt", "old_text": "hello", "new_text": "HI"},
        ]
        result = _multi_edit(deps, edits=edits)
        assert result.is_ok()
        assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "HI a"
        assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "HI b"


class TestMultiEditAtomicity:

    def test_rollback_on_failure(self, deps, tmp_path):
        """任一文件失败 → 所有文件不改"""
        (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
        (tmp_path / "b.txt").write_text("world", encoding="utf-8")
        edits = [
            {"path": "a.txt", "old_text": "hello", "new_text": "CHANGED"},
            {"path": "b.txt", "old_text": "NONEXISTENT", "new_text": "X"},
        ]
        result = _multi_edit(deps, edits=edits)
        assert not result.is_ok()
        # a.txt 也不应被改
        assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "hello"
        assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "world"

    def test_missing_file_in_edit_fails_whole(self, deps, tmp_path):
        edits = [{"path": "nonexistent.txt", "old_text": "x", "new_text": "y"}]
        result = _multi_edit(deps, edits=edits)
        assert not result.is_ok()


class TestMultiEditRegex:

    def test_regex_edit(self, deps, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("a1 b22 c333", encoding="utf-8")
        edits = [{"path": "a.txt", "old_text": r"\d+", "new_text": "X", "use_regex": True}]
        result = _multi_edit(deps, edits=edits)
        assert result.is_ok()
        assert f.read_text(encoding="utf-8") == "aX bX cX"

    def test_invalid_regex_fails(self, deps, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("hello", encoding="utf-8")
        edits = [{
            "path": "a.txt",
            "old_text": r"[invalid(",
            "new_text": "X",
            "use_regex": True,
        }]
        result = _multi_edit(deps, edits=edits)
        assert not result.is_ok()


class TestMultiEditErrors:

    def test_empty_edits(self, deps):
        result = _multi_edit(deps, edits=[])
        assert not result.is_ok()

    def test_non_list_edits(self, deps):
        result = _multi_edit(deps, edits="not a list")
        assert not result.is_ok()

    def test_edit_missing_path(self, deps):
        result = _multi_edit(deps, edits=[{"old_text": "x", "new_text": "y"}])
        assert not result.is_ok()

    def test_edit_missing_old_text(self, deps, tmp_path):
        (tmp_path / "a.txt").write_text("x", encoding="utf-8")
        result = _multi_edit(deps, edits=[{"path": "a.txt", "new_text": "y"}])
        assert not result.is_ok()

    def test_edit_not_dict(self, deps):
        result = _multi_edit(deps, edits=["string_instead_of_dict"])
        assert not result.is_ok()

    def test_old_text_not_found(self, deps, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("actual content", encoding="utf-8")
        edits = [{"path": "a.txt", "old_text": "nonexistent text", "new_text": "X"}]
        result = _multi_edit(deps, edits=edits)
        assert not result.is_ok()
        # 文件不应被改
        assert f.read_text(encoding="utf-8") == "actual content"


class TestMultiEditReturnedInfo:

    def test_returns_edited_list_and_count(self, deps, tmp_path):
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        (tmp_path / "b.txt").write_text("b", encoding="utf-8")
        edits = [
            {"path": "a.txt", "old_text": "a", "new_text": "A"},
            {"path": "b.txt", "old_text": "b", "new_text": "B"},
        ]
        result = _multi_edit(deps, edits=edits)
        assert result.is_ok()
        data = result.unwrap()
        assert "edited" in data
        assert "count" in data
        assert data["count"] == 2
        assert "a.txt" in data["edited"]
        assert "b.txt" in data["edited"]


class TestMultiEditEdgeCases:

    def test_same_file_multiple_edits_in_order(self, deps, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("foo bar foo bar", encoding="utf-8")
        edits = [
            {"path": "a.txt", "old_text": "foo", "new_text": "FOO1"},
            {"path": "a.txt", "old_text": "foo", "new_text": "FOO2"},
        ]
        # 顺序执行:第一次 foo→FOO1,第二次再找 FOO1→FOO2
        # 但实际行为应该是全部先校验再写 — 这意味着第二次的"foo"应该找不到了
        result = _multi_edit(deps, edits=edits)
        # 校验失败(第二个 edit 的 old_text "foo" 不在原始内容里,因为第一个已经替换)
        # 实现是同时校验,所以会失败
        assert not result.is_ok()

    def test_unicode_content(self, deps, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("你好 世界 🌍", encoding="utf-8")
        edits = [{"path": "a.txt", "old_text": "你好", "new_text": "Hello"}]
        result = _multi_edit(deps, edits=edits)
        assert result.is_ok()
        assert "Hello" in f.read_text(encoding="utf-8")
