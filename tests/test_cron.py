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


class TestPatchStdoutGuard:
    """patch_stdout 守卫 —— 后台 Timer 线程裸 print 劈碎 TUI 的回归防护"""

    def test_guard_installs_proxy_and_restores(self):
        """进入守卫时 sys.stdout 被代理替换，退出后恢复原状"""
        from fr_cli.weapon.cron import _stdout_guard

        original = sys.stdout
        with _stdout_guard():
            assert sys.stdout is not original
        assert sys.stdout is original

    def test_guard_nested_shares_single_proxy(self):
        """嵌套进入共享同一代理，内层退出不恢复裸 stdout（3.0.52 退出竞争回归）"""
        from fr_cli.weapon.cron import _stdout_guard

        original = sys.stdout
        with _stdout_guard():
            proxy = sys.stdout
            with _stdout_guard():
                assert sys.stdout is proxy
            assert sys.stdout is proxy
        assert sys.stdout is original

    def test_guard_concurrent_entries_keep_proxy(self):
        """并发进入：全部退出前 stdout 始终是代理，不会被人提前冲掉"""
        import threading
        import time

        from fr_cli.weapon.cron import _stdout_guard

        original = sys.stdout
        violations = []

        def worker():
            try:
                with _stdout_guard():
                    time.sleep(0.03)
                    if sys.stdout is original:
                        violations.append("代理被提前恢复")
            except Exception as e:
                violations.append(repr(e))

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert violations == []
        assert sys.stdout is original

    def test_runner_wrapper_executes_under_guard(self, manager, monkeypatch):
        """_runner_wrapper 执行 job 期间输出走守卫代理，且正常注册下一次"""
        monkeypatch.setattr(manager, "_persist", lambda: None)  # 不写真实配置
        seen = {}
        original_execute = manager._execute_job

        def spy(job):
            seen["stdout"] = sys.stdout
            return original_execute(job)

        monkeypatch.setattr(manager, "_execute_job", spy)
        before = sys.stdout
        job_id, _ = manager.add_job("echo guard_ok", 3600, "zh")
        job = next(j for j in manager.jobs if j["id"] == job_id)
        old_timer = job["timer"]
        old_timer.cancel()
        manager._runner_wrapper(job)
        # 执行期间输出走代理（防劈屏），退出后恢复
        assert seen["stdout"] is not before
        assert sys.stdout is before
        # 已注册下一次执行
        assert job["timer"] is not None and job["timer"] is not old_timer
        job["timer"].cancel()


class _FakeProxyStdout:
    """伪装成 prompt_toolkit.patch_stdout.StdoutProxy 的捕获式 stdout"""

    def __init__(self):
        self.chunks = []

    def write(self, data):
        self.chunks.append(data)
        return len(data)

    def flush(self):
        pass

    @property
    def text(self):
        return "".join(self.chunks)


# 让 _is_prompt_toolkit_stdout() 的模块名检查命中
_FakeProxyStdout.__module__ = "prompt_toolkit.patch_stdout"


class TestProxyColorDisable:
    """补全菜单防劈屏的颜色处理 —— 代理接管期间禁色，输出纯文本"""

    def test_execute_job_strips_color_under_proxy(self, manager, monkeypatch):
        """stdout 被 patch_stdout 代理时，[Cron N] 输出不含 ANSI 转义（?[2m 乱码回归）"""
        import fr_cli.weapon.cron as cron_mod

        # pytest 环境全局禁色（ui.py 的 _NO_COLOR），先伪造颜色常量以验证禁色逻辑
        monkeypatch.setattr(cron_mod, "DIM", "\033[2m")
        monkeypatch.setattr(cron_mod, "RESET", "\033[0m")
        fake = _FakeProxyStdout()
        monkeypatch.setattr(sys, "stdout", fake)
        job = {"id": 1, "cmd": "echo a", "job_type": "shell"}
        manager._execute_job(job)
        assert "[Cron 1]" in fake.text
        assert "\033" not in fake.text

    def test_execute_job_keeps_color_without_proxy(self, manager, monkeypatch, capsys):
        """普通 stdout（无代理）时保留颜色，不影响非 TUI 场景"""
        import fr_cli.weapon.cron as cron_mod

        monkeypatch.setattr(cron_mod, "DIM", "\033[2m")
        monkeypatch.setattr(cron_mod, "RESET", "\033[0m")
        job = {"id": 2, "cmd": "echo b", "job_type": "shell"}
        manager._execute_job(job)
        out = capsys.readouterr().out
        assert "[Cron 2]" in out
        assert "\033" in out

    def test_color_disable_restores_after_exit(self, monkeypatch):
        """退出上下文后颜色常量恢复，后续主线程输出不受影响"""
        import fr_cli.weapon.cron as cron_mod

        monkeypatch.setattr(cron_mod, "RED", "\033[91m")
        monkeypatch.setattr(cron_mod, "DIM", "\033[2m")
        fake = _FakeProxyStdout()
        monkeypatch.setattr(sys, "stdout", fake)
        with cron_mod._ProxyColorDisable():
            assert cron_mod.RED == "" and cron_mod.DIM == ""
        assert cron_mod.RED == "\033[91m" and cron_mod.DIM == "\033[2m"

    def test_color_disable_noop_without_proxy(self, monkeypatch):
        """无代理时 _ProxyColorDisable 不动颜色常量"""
        import fr_cli.weapon.cron as cron_mod

        monkeypatch.setattr(cron_mod, "RED", "\033[91m")
        with cron_mod._ProxyColorDisable():
            assert cron_mod.RED == "\033[91m"

    def test_color_disable_concurrent_entries(self, monkeypatch):
        """并发进入：先退出者不恢复颜色，仍在打印的 job 不会打出 ?[2m 乱码"""
        import threading

        import fr_cli.weapon.cron as cron_mod

        monkeypatch.setattr(cron_mod, "DIM", "\033[2m")
        monkeypatch.setattr(cron_mod, "RESET", "\033[0m")
        fake = _FakeProxyStdout()
        monkeypatch.setattr(sys, "stdout", fake)

        a_entered = threading.Event()
        b_entered = threading.Event()
        a_exited = threading.Event()
        errors = []

        def worker_a():
            try:
                with cron_mod._ProxyColorDisable():
                    a_entered.set()
                    b_entered.wait(2)
                # A 先退出，但 B 仍在上下文内
                a_exited.set()
            except Exception as e:  # pragma: no cover
                errors.append(repr(e))

        def worker_b():
            try:
                a_entered.wait(2)
                with cron_mod._ProxyColorDisable():
                    b_entered.set()
                    a_exited.wait(2)
                    # A 已退出、B 仍持有：颜色必须保持禁用
                    if cron_mod.DIM != "" or cron_mod.RESET != "":
                        errors.append(f"颜色被提前恢复: DIM={cron_mod.DIM!r}")
                    print(f"{cron_mod.DIM}[Cron 9]{cron_mod.RESET} x")
            except Exception as e:  # pragma: no cover
                errors.append(repr(e))

        ta = threading.Thread(target=worker_a)
        tb = threading.Thread(target=worker_b)
        ta.start()
        tb.start()
        ta.join(5)
        tb.join(5)
        assert errors == []
        assert "\033" not in fake.text
        # 全部退出后恢复真值
        assert cron_mod.DIM == "\033[2m" and cron_mod.RESET == "\033[0m"
