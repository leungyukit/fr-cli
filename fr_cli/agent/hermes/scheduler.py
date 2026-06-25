"""
Hermes 任务调度器 —— 后台轮询执行 pending 任务
"""
import threading
import time

from fr_cli.agent.hermes.models import TaskStatus


class HermesScheduler(threading.Thread):
    """Hermes 任务调度器 —— 后台轮询执行 pending 任务"""

    def __init__(self, engine, poll_interval: float = 5.0):
        super().__init__(daemon=True, name="HermesScheduler")
        self.engine = engine
        self.poll_interval = poll_interval
        self.running = True

    def stop(self):
        self.running = False

    def run(self):
        while self.running:
            try:
                now = time.time()
                pending = [
                    t for t in self.engine.task_manager.list_tasks()
                    if t.status == TaskStatus.PENDING
                    and (t.scheduled_at is None or t.scheduled_at <= now)
                    and self.engine._dependencies_satisfied(t)
                ]
                # 优先级降序
                pending.sort(key=lambda t: (-t.priority.value, t.created_at))
                for task in pending:
                    if not self.running:
                        break
                    if self.engine._has_cycle(task.id):
                        self.engine._fail_task(task, "依赖存在循环")
                        continue
                    try:
                        self.engine._execute_task(task)
                    except Exception as e:
                        # 调度器自身异常不应导致崩溃
                        self.engine._log_error(f"Scheduler failed to execute {task.id}: {e}")
            except Exception as e:
                self.engine._log_error(f"Scheduler loop error: {e}")
            time.sleep(self.poll_interval)
