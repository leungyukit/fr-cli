"""
定时任务生命周期测试 —— 计时器的停止、单一真相源、幂等恢复

背景
----
定时任务的计时器是 ``threading.Timer`` 后台线程（daemon=True）。每次触发
都会进入 ``fr_cli/weapon/cron.py::_stdout_guard()``，而
``prompt_toolkit.patch_stdout`` 是**进程级**的 ``sys.stdout`` 替换 ——
它会把此刻其它线程/用例的 print 全部劫持走。

于是就有了两类问题：

1. **跨用例污染**：用例创建的定时任务从不被回收，interval=10s 的任务
   会在整套测试跑到一半时触发，撞上别的用例的 capsys 断言
   （"断言输出为空"，没有任何异常信息，极难定位）。
2. **多实例割裂**：``/cron_list``、``/status``、gatekeeper 同步读的都是
   模块级默认管理器，但恢复任务却新建了一个临时实例 —— 任务在跑，
   却谁都看不见它。

本文件锁住这两类问题的修复。
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from fr_cli.weapon import cron as cron_mod
from fr_cli.weapon.cron import CronManager, _default_manager, stop_all


@pytest.fixture(autouse=True)
def _isolate_cron(tmp_path, monkeypatch):
    """每个测试独立的配置目录 + 干净的默认管理器"""
    fake_home = tmp_path / "home"
    fake_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))

    import fr_cli.conf.paths as _paths_mod
    fake_fr_cli = fake_home / ".fr_cli"
    fake_fr_cli.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(_paths_mod._root_holder, "value", fake_fr_cli)

    # 默认管理器是全局单例 —— 测试前清空，避免跨用例串味
    _default_manager.stop(clear_persisted=True)
    with _default_manager._lock:
        _default_manager.jobs.clear()
    _default_manager._job_id_counter = 0

    yield

    _default_manager.stop(clear_persisted=True)
    with _default_manager._lock:
        _default_manager.jobs.clear()
    _default_manager._job_id_counter = 0


# ===================================================================
# stop()
# ===================================================================


class TestStop:

    def test_stop_cancels_timers(self):
        """stop() 后计时器被取消，不再触发"""
        mgr = CronManager()
        mgr.add_job("echo should-not-run", 5, "zh")
        assert mgr.jobs[0]["timer"] is not None

        count = mgr.stop()
        assert count == 1
        assert mgr.jobs[0]["timer"] is None
        # timer 对象确实被 cancel 了（is_alive 为假 / 已取消）
        assert mgr._stopped is True

    def test_stop_keeps_jobs_by_default(self):
        """默认只停调度、不删任务（"暂停"而非"删除"）"""
        mgr = CronManager()
        mgr.add_job("echo hi", 30, "zh")
        mgr.stop()
        assert len(mgr.jobs) == 1

    def test_stop_clear_persisted_removes_jobs(self):
        """clear_persisted=True 连任务一起删掉并落盘"""
        mgr = CronManager()
        mgr.add_job("echo hi", 30, "zh")

        mgr.stop(clear_persisted=True)
        assert len(mgr.jobs) == 0

        cfg_file = Path.home() / ".fr_cli" / "config.json"
        cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
        assert cfg.get("cron", []) == []

    def test_stopped_job_does_not_reschedule(self):
        """已停止的任务执行完不会续期（否则 stop() 白停）"""
        mgr = CronManager()
        fired = []

        def _fake_execute(job):
            fired.append(job["id"])
            return True

        mgr._execute_job = _fake_execute
        job = {
            "id": 1, "mode": "interval", "value": 30, "cmd": "echo x",
            "lang": "zh", "timer": None, "job_type": "shell",
            "agent_name": None, "agent_input": "", "state_provider": None,
        }
        mgr.jobs.append(job)

        mgr.stop()
        mgr._runner_wrapper(job)

        assert fired == []          # stop 之后连执行都不该发生
        assert job["timer"] is None

    def test_add_job_after_stop_resumes(self):
        """stop() 之后再加任务要能重新跑起来"""
        mgr = CronManager()
        mgr.stop()
        assert mgr._stopped is True

        result = mgr.add_job("echo back", 30, "zh")
        assert result[0] is not None
        assert mgr._stopped is False
        assert mgr.jobs[0]["timer"] is not None


# ===================================================================
# stop_all()
# ===================================================================


class TestStopAll:

    def test_stop_all_stops_every_instance(self):
        """stop_all() 一次停掉所有 CronManager 实例"""
        mgr_a = CronManager()
        mgr_b = CronManager()
        mgr_a.add_job("echo a", 30, "zh")
        mgr_b.add_job("echo b", 30, "zh")

        stopped = stop_all()
        assert stopped >= 2
        assert mgr_a.jobs[0]["timer"] is None
        assert mgr_b.jobs[0]["timer"] is None

    def test_stop_all_stops_default_manager(self):
        """默认管理器也在 stop_all() 的射程内"""
        _default_manager.add_job("echo default", 30, "zh")
        assert _default_manager.jobs[0]["timer"] is not None

        stop_all()
        assert _default_manager.jobs[0]["timer"] is None


# ===================================================================
# 单一真相源
# ===================================================================


class TestSingleSourceOfTruth:

    def test_module_level_add_job_uses_default_manager(self):
        """模块级 add_job 落在默认管理器上"""
        cron_mod.add_job("echo global", 30, "zh")
        assert len(_default_manager.jobs) == 1
        assert _default_manager.jobs[0]["cmd"] == "echo global"

    def test_cron_list_sees_restored_jobs(self):
        """恢复进默认管理器后 /cron_list 能看见（历史：恢复进临时实例=孤儿）"""
        cfg_file = Path.home() / ".fr_cli" / "config.json"
        cfg_file.parent.mkdir(parents=True, exist_ok=True)
        cfg_file.write_text(
            json.dumps({
                "cron": [{
                    "id": 7, "mode": "interval", "value": 60,
                    "cmd": "echo restored", "lang": "zh",
                    "job_type": "shell", "agent_name": None, "agent_input": "",
                }],
            }, ensure_ascii=False),
            encoding="utf-8",
        )

        _default_manager.load_persistent_jobs(lang="zh")

        assert len(_default_manager.jobs) == 1
        assert _default_manager.jobs[0]["cmd"] == "echo restored"

    def test_restore_is_idempotent(self):
        """重复恢复不产生重复任务（AppState 每建一次就会调一次）"""
        cfg_file = Path.home() / ".fr_cli" / "config.json"
        cfg_file.parent.mkdir(parents=True, exist_ok=True)
        cfg_file.write_text(
            json.dumps({
                "cron": [{
                    "id": 1, "mode": "interval", "value": 60,
                    "cmd": "echo once", "lang": "zh",
                    "job_type": "shell", "agent_name": None, "agent_input": "",
                }],
            }, ensure_ascii=False),
            encoding="utf-8",
        )

        _default_manager.load_persistent_jobs(lang="zh")
        _default_manager.load_persistent_jobs(lang="zh")
        _default_manager.load_persistent_jobs(lang="zh")

        assert len(_default_manager.jobs) == 1

    def test_status_reports_real_cron_count(self):
        """/status 的 cron_jobs 数字不再恒为 0"""
        from unittest.mock import MagicMock

        from fr_cli.core.app_state_status import AppStateStatusMixin

        class _State(AppStateStatusMixin):
            pass

        state = _State()
        for attr in ("display_provider", "display_model", "api_key", "client",
                     "security", "master_agent", "agent_server", "hermes",
                     "gatekeeper", "cfg", "plugins", "agents"):
            setattr(state, attr, MagicMock())
        state.lang = "zh"

        _default_manager.add_job("echo counted", 30, "zh")
        summary = state.status_summary()
        assert summary["cron_jobs"] == 1


# ===================================================================
# 跨用例污染闸门（与 tests/conftest.py 的 autouse 夹具配套）
# ===================================================================


class TestNoCrossTestPollution:

    def test_timer_does_not_fire_after_teardown(self):
        """用例结束后的计时器必须已被取消（这是全量跑稳定的关键）"""
        fired = []
        mgr = CronManager()
        mgr._execute_job = lambda job: fired.append(job["id"]) or True

        # at 模式：1 秒后触发一次
        future = (datetime.now() + timedelta(seconds=1)).isoformat()
        mgr.add_job(schedule=future, cmd="echo late", lang="zh")
        assert len(mgr.jobs) == 1

        # 模拟 conftest 的 teardown 闸门
        mgr.stop()
        time.sleep(1.5)

        assert fired == []
        assert mgr.jobs[0]["timer"] is None
