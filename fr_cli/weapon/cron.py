"""
结界定时引擎
使用线程实现轻量级的后台定时任务
"""
import threading
import subprocess
from fr_cli.ui.ui import RED, GREEN, DIM, YELLOW, RESET
from fr_cli.lang.i18n import T


class CronManager:
    """定时任务管理器 —— 结界掌控者"""

    def __init__(self):
        self.jobs = []
        self._job_id_counter = 0

    def _job_runner(self, job_id, cmd, interval, lang):
        """内部递归执行器，实现每隔 interval 秒执行一次"""
        job = next((j for j in self.jobs if j["id"] == job_id), None)
        if not job:
            return

        try:
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            out = res.stdout.strip()[:100]  # 截断输出
            print(f"{DIM}[Cron {job_id}]{RESET} {out}")
        except Exception as e:
            print(f"{RED}[Cron {job_id}] Error: {e}{RESET}")

        # 重新注册定时器
        job["timer"] = threading.Timer(interval, self._job_runner, args=(job_id, cmd, interval, lang))
        job["timer"].daemon = True
        job["timer"].start()

    def add_job(self, cmd, interval, lang):
        """添加一个定时循环任务"""
        try:
            interval = float(interval)
        except ValueError:
            return None, f"{RED}Invalid seconds{RESET}"

        self._job_id_counter += 1
        job_id = self._job_id_counter

        job = {"id": job_id, "cmd": cmd, "interval": interval, "timer": None}
        self.jobs.append(job)

        # 启动首次任务
        job["timer"] = threading.Timer(interval, self._job_runner, args=(job_id, cmd, interval, lang))
        job["timer"].daemon = True
        job["timer"].start()

        return job_id, T("cron_ok", lang, job_id, interval)

    def list_jobs(self, lang):
        """列出当前运行中的任务"""
        if not self.jobs:
            return None, T("empty", lang)
        res = []
        for j in self.jobs:
            res.append(f"{GREEN}ID:{j['id']}{RESET} | {YELLOW}{j['interval']}s{RESET} | {j['cmd'][:30]}")
        return res, None

    def del_job(self, job_id, lang):
        """根据 ID 终止定时任务"""
        for i, j in enumerate(self.jobs):
            if j["id"] == job_id:
                if j["timer"]:
                    j["timer"].cancel()
                self.jobs.pop(i)
                return True, T("cron_killed", lang, job_id)
        return False, f"{RED}Not found{RESET}"


# ------------------------------------------------------------------
# 默认全局实例（保持向后兼容）
# ------------------------------------------------------------------
_default_manager = CronManager()
JOBS = _default_manager.jobs


def add_job(cmd, interval, lang):
    """添加定时任务（委托给默认管理器）"""
    return _default_manager.add_job(cmd, interval, lang)


def list_jobs(lang):
    """列出定时任务（委托给默认管理器）"""
    return _default_manager.list_jobs(lang)


def del_job(job_id, lang):
    """删除定时任务（委托给默认管理器）"""
    return _default_manager.del_job(job_id, lang)
