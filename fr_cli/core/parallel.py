"""
带整体 deadline 的并行执行
==========================

给"并行跑若干任务、到点就返回"的场景用（Agent Team 的子任务、蜂群的任务单元）。

为什么不用 ``ThreadPoolExecutor``
--------------------------------
标准库的 worker 是**非 daemon** 线程，而 Python 在解释器退出时会 join 它们
（``concurrent.futures.thread._python_exit``）。于是：

    executor.shutdown(wait=False)      # 只是"不等这一轮"
    ...                               # 函数返回了，但进程退不出去

表现为**命令已经跑完、结果都打印了，进程却挂死不退出** —— 批处理模式
（``fr-cli -c "/agent_team run ..."``）会一直卡住，只能 kill -9。

本模块用 **daemon 线程** + ``concurrent.futures.Future``：
超时到点立即返回，进程也能立即退出。

诚实边界
--------
Python 无法强杀线程 —— 超时任务的线程会继续跑完。本模块只保证
"**不阻塞调用方返回、也不阻塞进程退出**"，不保证"超时后任务立刻停止"。
daemon 线程在进程退出时被直接丢弃（未完成的网络请求会被掐断）。
"""
from __future__ import annotations

import concurrent.futures
import threading
from typing import Any, Callable, Iterable, List, Optional, Tuple

#: 并发上限（防止一次拉起几百个线程）
MAX_PARALLEL_WORKERS = 16

#: 工作线程名前缀（便于测试与排查）
THREAD_NAME_PREFIX = "fr-parallel"


def run_with_deadline(
    items: Iterable[Any],
    worker: Callable[[Any], Any],
    timeout: Optional[float] = None,
    max_workers: int = 1,
) -> Tuple[List[Tuple[Any, Any, Optional[BaseException]]], List[Any]]:
    """并行执行 ``items``，整体 deadline 到点立即返回。

    Args:
        items: 待执行对象（会先物化成 list）。
        worker: 单项执行函数 ``worker(item) -> Any``；抛异常视为该项失败。
        timeout: 整体 deadline 秒数；``None`` 或 ``<=0`` 表示**不限时**（等全部完成）。
        max_workers: 最大并发数。

    Returns:
        ``(done, timed_out)``
        - ``done``: ``[(item, result, error)]``，``error`` 为 None 表示成功；
          顺序按 ``items`` 的原始顺序（与完成顺序无关）。
        - ``timed_out``: ``[item]`` —— 到点时仍未完成的项。
    """
    materialised = list(items)
    if not materialised:
        return [], []

    workers = max(1, min(int(max_workers or 1), MAX_PARALLEL_WORKERS))
    semaphore = threading.Semaphore(workers)
    futures: dict = {}

    def _entry(item: Any, fut: "concurrent.futures.Future") -> None:
        with semaphore:
            if not fut.set_running_or_notify_cancel():
                return
            try:
                fut.set_result(worker(item))
            except BaseException as e:  # 线程内必须兜住，不能让异常逃出去
                fut.set_exception(e)

    for item in materialised:
        fut = concurrent.futures.Future()
        futures[fut] = item
        threading.Thread(
            target=_entry,
            args=(item, fut),
            daemon=True,
            name=f"{THREAD_NAME_PREFIX}-{workers}",
        ).start()

    if timeout is not None and timeout > 0:
        done_futs, not_done_futs = concurrent.futures.wait(
            list(futures), timeout=timeout
        )
    else:
        done_futs, not_done_futs = set(futures), set()

    # 按原始顺序装配结果（与完成顺序无关）
    done: List[Tuple[Any, Any, Optional[BaseException]]] = []
    for fut, item in futures.items():
        if fut not in done_futs:
            continue
        try:
            done.append((item, fut.result(), None))
        except BaseException as e:
            done.append((item, None, e))

    timed_out = [futures[fut] for fut in not_done_futs]
    return done, timed_out
