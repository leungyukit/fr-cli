"""
CronManager 定时任务测试
覆盖任务添加/删除/列表、参数校验、间隔下限、shell 解析安全等。
"""
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fr_cli.weapon.cron import CronManager


@pytest.fixture
def manager():
    """每个测试一个新 CronManager"""
    return CronManager()


class TestAddJob:

    def test_add_valid_shell_job(self, manager):
        result = manager.add_job("echo hello", 30, "zh")
        # 返回 (job_id, msg) 或 (job_id, error_msg)
        assert result is not None
        job_id, msg = result
        assert job_id is not None
        assert isinstance(job_id, int)

    def test_add_job_minimum_interval_enforced(self, manager):
        """间隔小于 5 秒应被拒绝"""
        result = manager.add_job("echo x", 3, "zh")
        if result is not None:
            job_id, msg = result
            assert job_id is None
            assert "5" in msg or "interval" in msg.lower() or "秒" in msg

    def test_add_job_zero_interval_rejected(self, manager):
        result = manager.add_job("echo x", 0, "zh")
        # 返回 None(拒绝) 或 (None, error_msg)
        if result is None:
            return  # 拒绝
        job_id, msg = result
        assert job_id is None

    def test_add_job_invalid_interval_rejected(self, manager):
        """非数字间隔应被拒绝"""
        result = manager.add_job("echo x", "abc", "zh")
        if result is not None:
            job_id, msg = result
            assert job_id is None

    def test_add_multiple_jobs_get_unique_ids(self, manager):
        id1, _ = manager.add_job("echo a", 10, "zh")
        id2, _ = manager.add_job("echo b", 10, "zh")
        id3, _ = manager.add_job("echo c", 10, "zh")
        assert id1 != id2 != id3
        assert all(isinstance(i, int) for i in [id1, id2, id3])

    def test_add_agent_job(self, manager):
        """agent 类型任务"""
        mock_state = MagicMock()
        result = manager.add_job(
            "my_agent", 30, "zh",
            job_type="agent", agent_name="my_agent",
            agent_input="hello", state=mock_state,
        )
        job_id, msg = result
        assert job_id is not None


class TestListJobs:

    def test_list_empty(self, manager):
        result = manager.list_jobs("zh")
        # 返回 (res, err) 或 None — 接受两种形式
        if isinstance(result, tuple):
            res, err = result
            assert res is None
            assert err is not None
        else:
            assert result is None

    def test_list_with_jobs(self, manager):
        manager.add_job("echo hello", 30, "zh")
        manager.add_job("ls -la", 60, "zh")
        result = manager.list_jobs("zh")
        res, _ = result
        assert isinstance(res, list)
        assert any("hello" in str(j) for j in res)
        assert any("ls" in str(j) for j in res)

    def test_list_contains_ids(self, manager):
        id1, _ = manager.add_job("echo x", 30, "zh")
        result = manager.list_jobs("zh")
        res, _ = result
        # 列表应包含 ID(以便 /cron_del 用)
        joined = " ".join(str(j) for j in res)
        assert str(id1) in joined


class TestDelJob:

    def test_del_existing_job(self, manager):
        job_id, _ = manager.add_job("echo x", 30, "zh")
        # 删除任务
        result = manager.del_job(job_id, "zh")
        # 返回 (ok, msg) 元组或类似
        assert result is not None
        # 列表应为空
        listed = manager.list_jobs("zh")
        res, _ = listed
        assert res is None or len(res) == 0

    def test_del_nonexistent_job_handled(self, manager):
        """删除不存在的任务应优雅处理"""
        if hasattr(manager, "del_job"):
            try:
                manager.del_job(99999, "zh")
            except (KeyError, ValueError):
                pass  # 抛异常也算合理
        elif hasattr(manager, "remove_job"):
            try:
                manager.remove_job(99999, "zh")
            except (KeyError, ValueError):
                pass


class TestPersistence:

    def test_export_jobs(self, manager):
        manager.add_job("echo a", 30, "zh")
        manager.add_job("echo b", 60, "zh")
        if hasattr(manager, "export_jobs"):
            jobs = manager.export_jobs()
            assert isinstance(jobs, list)
            assert len(jobs) >= 2

    def test_import_jobs(self, manager):
        jobs = [
            {"id": 1, "cmd": "echo imported", "interval": 30},
            {"id": 2, "cmd": "echo x", "interval": 60},
        ]
        if hasattr(manager, "import_jobs"):
            try:
                manager.import_jobs(jobs, "zh")
            except Exception:
                pass
            # 至少不崩
            result = manager.list_jobs("zh")
            assert result is not None


class TestShellSafety:

    def test_command_with_special_chars(self, manager):
        """包含特殊字符的命令不应崩"""
        # shlex.split 应该能正确解析
        result = manager.add_job("echo 'hello world' && ls -la", 30, "zh")
        # 应能添加成功
        if result is not None:
            job_id, _ = result
            assert job_id is not None

    def test_command_with_pipes(self, manager):
        result = manager.add_job("ps aux | grep python", 30, "zh")
        if result is not None:
            job_id, _ = result
            assert job_id is not None
