"""
结界定时引擎
使用线程实现轻量级的后台定时任务
支持 shell 命令和 Agent 分身两种任务类型
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
        self._lock = threading.Lock()

    def _job_runner(self, job_id, cmd, interval, lang, job_type="shell", agent_name=None, agent_input="", state=None):
        """内部递归执行器，实现每隔 interval 秒执行一次"""
        with self._lock:
            job = next((j for j in self.jobs if j["id"] == job_id), None)
        if not job:
            return

        try:
            if job_type == "agent" and agent_name:
                # 执行 Agent 分身
                if state is None:
                    print(f"{RED}[Cron {job_id}] Error: Agent 任务需要 AppState{RESET}")
                else:
                    from fr_cli.agent.executor import run_agent
                    result, err = run_agent(agent_name, state, user_input=agent_input)
                    out = (result or "")[:200]
                    if err:
                        out = f"Error: {err}"
                    print(f"{DIM}[Cron {job_id}] Agent[{agent_name}]{RESET} {out}")
            else:
                # 执行 shell 命令
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                out = res.stdout.strip()[:100]  # 截断输出
                print(f"{DIM}[Cron {job_id}]{RESET} {out}")
        except Exception as e:
            print(f"{RED}[Cron {job_id}] Error: {e}{RESET}")

        # 重新注册定时器
        job["timer"] = threading.Timer(
            interval, self._job_runner,
            args=(job_id, cmd, interval, lang),
            kwargs={"job_type": job_type, "agent_name": agent_name, "agent_input": agent_input, "state": state}
        )
        job["timer"].daemon = True
        job["timer"].start()

    def add_job(self, cmd, interval, lang, job_type="shell", agent_name=None, agent_input="", state=None):
        """添加一个定时循环任务

        Args:
            cmd: 命令字符串（shell 类型）或 Agent 名称（agent 类型）
            interval: 执行间隔（秒）
            lang: 界面语言
            job_type: "shell" 或 "agent"
            agent_name: Agent 分身名称（agent 类型时有效）
            agent_input: 传递给 Agent 的输入内容（agent 类型时有效）
            state: AppState 实例（agent 类型时必需）
        """
        try:
            interval = float(interval)
        except ValueError:
            return None, f"{RED}Invalid seconds{RESET}"

        with self._lock:
            self._job_id_counter += 1
            job_id = self._job_id_counter

            job = {
                "id": job_id,
                "cmd": cmd,
                "interval": interval,
                "timer": None,
                "job_type": job_type,
                "agent_name": agent_name,
                "agent_input": agent_input,
            }
            self.jobs.append(job)

        # 启动首次任务
        job["timer"] = threading.Timer(
            interval, self._job_runner,
            args=(job_id, cmd, interval, lang),
            kwargs={"job_type": job_type, "agent_name": agent_name, "agent_input": agent_input, "state": state}
        )
        job["timer"].daemon = True
        job["timer"].start()

        return job_id, T("cron_ok", lang, job_id, interval)

    def list_jobs(self, lang):
        """列出当前运行中的任务"""
        with self._lock:
            jobs_copy = list(self.jobs)
        if not jobs_copy:
            return None, T("empty", lang)
        res = []
        for j in jobs_copy:
            jtype = j.get("job_type", "shell")
            type_tag = f"[{jtype}]" if jtype == "agent" else "[shell]"
            target = j.get("agent_name", j["cmd"]) if jtype == "agent" else j["cmd"]
            res.append(f"{GREEN}ID:{j['id']}{RESET} | {type_tag} | {YELLOW}{j['interval']}s{RESET} | {target[:30]}")
        return res, None

    def del_job(self, job_id, lang):
        """根据 ID 终止定时任务"""
        with self._lock:
            job = next((j for j in self.jobs if j["id"] == job_id), None)
            if not job:
                return False, f"{RED}Not found{RESET}"
            if job["timer"]:
                job["timer"].cancel()
            self.jobs.remove(job)
        return True, T("cron_killed", lang, job_id)

    def sync_jobs(self, job_configs, lang="zh", state=None):
        """同步任务列表：根据配置增删任务，保持当前任务与配置一致

        Args:
            job_configs: 任务配置列表，每项为 dict，包含 cmd/interval/job_type/agent_name/agent_input
            lang: 界面语言
            state: AppState 实例（agent 类型任务必需）
        """
        with self._lock:
            current_ids = {j["id"] for j in self.jobs}
            target_ids = {j.get("id") for j in job_configs if j.get("id")}

            # 删除不在配置中的任务
            for j in list(self.jobs):
                if j["id"] not in target_ids:
                    if j["timer"]:
                        j["timer"].cancel()
                    self.jobs.remove(j)

        # 添加配置中有但当前没有的任务（在锁外调用 add_job，避免死锁）
        for cfg in job_configs:
            jid = cfg.get("id")
            if jid and jid not in current_ids:
                self.add_job(
                    cmd=cfg.get("cmd", ""),
                    interval=cfg.get("interval", 60),
                    lang=lang,
                    job_type=cfg.get("job_type", "shell"),
                    agent_name=cfg.get("agent_name"),
                    agent_input=cfg.get("agent_input", ""),
                    state=state,
                )

    def export_jobs(self):
        """导出所有定时任务为可持久化的字典列表（不含线程对象）"""
        with self._lock:
            jobs_copy = list(self.jobs)
        return [
            {
                "id": j["id"],
                "cmd": j["cmd"],
                "interval": j["interval"],
                "job_type": j.get("job_type", "shell"),
                "agent_name": j.get("agent_name"),
                "agent_input": j.get("agent_input", ""),
            }
            for j in jobs_copy
        ]

    def import_jobs(self, jobs, lang="zh", state=None):
        """从字典列表恢复定时任务"""
        for job in jobs:
            try:
                self.add_job(
                    cmd=job.get("cmd", ""),
                    interval=job.get("interval", 60),
                    lang=lang,
                    job_type=job.get("job_type", "shell"),
                    agent_name=job.get("agent_name"),
                    agent_input=job.get("agent_input", ""),
                    state=state,
                )
            except Exception:
                pass


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
