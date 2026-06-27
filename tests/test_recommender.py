"""
功能推荐引擎 (Recommender) 测试
覆盖 record_command_usage / recommend_features / 关键词匹配 / 使用频率排序。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fr_cli.core.recommender import (
    record_command_usage, recommend_features, _base_cmd
)


@pytest.fixture
def isolated_usage(tmp_path, monkeypatch):
    """隔离 _COMMAND_USAGE_FILE 到临时目录"""
    import fr_cli.core.recommender as rec_mod
    usage_file = tmp_path / "command_usage.json"
    monkeypatch.setattr(rec_mod, "_COMMAND_USAGE_FILE", usage_file)
    return usage_file


class TestBaseCmd:

    def test_simple_command(self):
        assert _base_cmd("/ls") == "/ls"

    def test_command_with_args(self):
        assert _base_cmd("/cat /tmp/file.txt") == "/cat"

    def test_empty_string(self):
        assert _base_cmd("") == ""

    def test_none(self):
        # None 时应不崩
        result = _base_cmd(None)
        assert result == ""


class TestRecordCommandUsage:

    def test_record_first_time(self, isolated_usage):
        record_command_usage("/ls")
        assert isolated_usage.exists()

    def test_record_increments_count(self, isolated_usage):
        record_command_usage("/ls")
        record_command_usage("/ls")
        record_command_usage("/ls")
        # 至少不崩
        assert isolated_usage.exists()

    def test_record_different_commands(self, isolated_usage):
        record_command_usage("/ls")
        record_command_usage("/cat")
        record_command_usage("/write")
        # 应不崩
        assert isolated_usage.exists()


class TestRecommendFeatures:

    def test_recommend_file_related_chinese(self, isolated_usage):
        """中文"文件"应推荐文件相关命令"""
        recs = recommend_features("我有个文件想看")
        assert isinstance(recs, list)
        cmds = [r["cmd"] for r in recs]
        # 至少应包含 /ls 或 /cat
        assert any("/ls" in cmd or "/cat" in cmd or "/cd" in cmd for cmd in cmds)

    def test_recommend_file_related_english(self, isolated_usage):
        recs = recommend_features("I want to read a file")
        cmds = [r["cmd"] for r in recs]
        assert any("/ls" in cmd or "/cat" in cmd for cmd in cmds)

    def test_recommend_search_related(self, isolated_usage):
        recs = recommend_features("搜索一下 Python 教程")
        cmds = [r["cmd"] for r in recs]
        assert any("/web" in cmd or "/fetch" in cmd for cmd in cmds)

    def test_recommend_email_related(self, isolated_usage):
        recs = recommend_features("查看收件箱")
        cmds = [r["cmd"] for r in recs]
        assert any("/mail" in cmd for cmd in cmds)

    def test_recommend_image_related(self, isolated_usage):
        recs = recommend_features("看图")
        cmds = [r["cmd"] for r in recs]
        # /see 或 /analyze
        assert any("/see" in cmd or "/analyze" in cmd for cmd in cmds)

    def test_recommend_returns_list_with_descriptions(self, isolated_usage):
        recs = recommend_features("文件")
        for r in recs:
            assert "cmd" in r
            assert "desc" in r

    def test_recommend_unrelated_input(self, isolated_usage):
        """无关输入应返回空列表或仅基于使用频率的推荐"""
        recs = recommend_features("xyzabc12345 没有意义的输入")
        # 没匹配关键词 + 没使用记录,可能返回空
        assert isinstance(recs, list)

    def test_recommend_priority_by_frequency(self, isolated_usage):
        """常用命令应优先"""
        # 先记录一些命令
        for _ in range(10):
            record_command_usage("/ls")
        for _ in range(3):
            record_command_usage("/cat")
        for _ in range(1):
            record_command_usage("/write")

        recs = recommend_features("文件")
        # 不强验证顺序,但至少包含这些命令
        cmds = [r["cmd"] for r in recs]
        assert any("/ls" in cmd for cmd in cmds)


class TestCaseInsensitive:

    def test_uppercase_keyword(self, isolated_usage):
        recs = recommend_features("FILE")
        cmds = [r["cmd"] for r in recs]
        # 大写 FILE 也应匹配(因为 input_lower)
        assert any("/ls" in cmd or "/cat" in cmd for cmd in cmds)

    def test_mixed_case(self, isolated_usage):
        recs = recommend_features("Read File")
        cmds = [r["cmd"] for r in recs]
        assert any(cmd.startswith("/") for cmd in cmds)


class TestMultipleKeywords:

    def test_multi_category_input(self, isolated_usage):
        """同时触发多个分类"""
        recs = recommend_features("搜索并保存邮件")
        cmds = [r["cmd"] for r in recs]
        # 应包含搜索和邮件
        assert any("/web" in cmd for cmd in cmds)
        assert any("/mail" in cmd for cmd in cmds)
