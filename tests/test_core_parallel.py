"""``fr_cli.core.parallel`` 的回归测试

覆盖:
- 结果按**原始顺序**装配（与完成顺序无关）
- 整体 deadline 到点立即返回，超时项被单独列出
- 单项异常只影响该项，不拖垮其余
- 并发上限（信号量闸门）真的生效
- 工作线程是 **daemon** —— 超时后进程能退出
- ``timeout=None`` 表示不限时，等全部完成

背景：``ThreadPoolExecutor`` 的 worker 是非 daemon 线程，解释器退出时会 join
它们，导致"命令跑完了、进程却退不出去"（实测 ``fr-cli -c`` 挂死 15 分钟）。
"""
import subprocess
import sys
import threading
import time

import pytest

from fr_cli.core.parallel import (
    MAX_PARALLEL_WORKERS,
    THREAD_NAME_PREFIX,
    run_with_deadline,
)


class TestOrdering:
    def test_results_keep_input_order(self):
        def worker(item):
            # 第一个最慢 —— 完成顺序与输入顺序相反
            time.sleep(0.3 if item == "慢" else 0.01)
            return f"结果-{item}"

        done, timed_out = run_with_deadline(["慢", "快"], worker, timeout=5)
        assert [item for item, _r, _e in done] == ["慢", "快"]
        assert [r for _i, r, _e in done] == ["结果-慢", "结果-快"]
        assert timed_out == []

    def test_empty_items(self):
        done, timed_out = run_with_deadline([], lambda x: x, timeout=1)
        assert done == []
        assert timed_out == []


class TestDeadline:
    def test_timeout_items_are_listed(self):
        def worker(item):
            if item == "慢":
                time.sleep(3)
            return item

        done, timed_out = run_with_deadline(
            ["慢", "快"], worker, timeout=0.3, max_workers=2
        )
        assert timed_out == ["慢"]
        assert [i for i, _r, _e in done] == ["快"]

    def test_no_timeout_means_wait_for_all(self):
        def worker(item):
            time.sleep(0.2)
            return item

        done, timed_out = run_with_deadline(["a", "b"], worker, timeout=None)
        assert timed_out == []
        assert len(done) == 2

    def test_zero_timeout_means_wait_for_all(self):
        """``timeout<=0`` 视为不限时（与蜂群既有的 ``<=0`` 语义一致）。"""
        done, timed_out = run_with_deadline(["a"], lambda i: i, timeout=0)
        assert timed_out == []
        assert len(done) == 1

    def test_returns_promptly_on_timeout(self):
        t0 = time.monotonic()
        run_with_deadline(["慢"], lambda i: time.sleep(5), timeout=0.3)
        assert time.monotonic() - t0 < 3


class TestErrorIsolation:
    def test_one_failure_does_not_kill_others(self):
        def worker(item):
            if item == "坏":
                raise ValueError("炸了")
            return item

        done, timed_out = run_with_deadline(["好", "坏"], worker, timeout=5)
        assert timed_out == []
        by_item = {i: (r, e) for i, r, e in done}
        assert by_item["好"] == ("好", None)
        assert by_item["坏"][0] is None
        assert isinstance(by_item["坏"][1], ValueError)
        assert str(by_item["坏"][1]) == "炸了"


class TestConcurrencyLimit:
    def test_worker_limit_is_enforced(self):
        peak = 0
        live = 0
        lock = threading.Lock()

        def worker(item):
            nonlocal peak, live
            with lock:
                live += 1
                peak = max(peak, live)
            time.sleep(0.1)
            with lock:
                live -= 1
            return item

        run_with_deadline(list(range(8)), worker, timeout=10, max_workers=3)
        assert peak <= 3, f"并发峰值 {peak} 超过上限 3"

    def test_max_workers_is_capped(self):
        """上限再大也不能超过 MAX_PARALLEL_WORKERS（防止一次拉起几百线程）。"""
        peak = 0
        live = 0
        lock = threading.Lock()

        def worker(item):
            nonlocal peak, live
            with lock:
                live += 1
                peak = max(peak, live)
            time.sleep(0.05)
            with lock:
                live -= 1
            return item

        run_with_deadline(
            list(range(40)), worker, timeout=20, max_workers=1000
        )
        assert peak <= MAX_PARALLEL_WORKERS


class TestDaemonThreads:
    def test_threads_are_daemon(self):
        started = threading.Event()

        def worker(item):
            started.set()
            time.sleep(2)
            return item

        run_with_deadline(["慢"], worker, timeout=0.2)
        assert started.wait(2)
        live = [t for t in threading.enumerate()
                if t.name.startswith(THREAD_NAME_PREFIX)]
        assert live
        assert all(t.daemon for t in live)

    def test_process_exits_after_timeout(self):
        """真实复现批处理模式：超时后子进程必须能自行退出。"""
        script = """
import time
from fr_cli.core.parallel import run_with_deadline
done, timed_out = run_with_deadline(["x"], lambda i: time.sleep(30), timeout=0.5)
print("RETURNED", len(timed_out))
"""
        try:
            proc = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True, text=True, timeout=25,
            )
        except subprocess.TimeoutExpired:
            pytest.fail("超时后进程没有退出 —— 工作线程不是 daemon 线程")
        assert proc.returncode == 0, proc.stderr
        assert "RETURNED" in proc.stdout
