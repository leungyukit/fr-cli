"""
定时任务引擎 —— 凡人结界
支持三种调度模式：
  - interval: 间隔秒数（兼容旧式）
  - cron:     标准 cron 表达式（如 "0 9 * * *" 每天 9 点）
  - at:       一次性任务，ISO 时间字符串（如 "2026-12-31 23:59:59"）

使用线程实现轻量级后台定时任务。
支持 shell 命令和 Agent 分身两种任务类型。

定时任务列表统一收敛到 ~/.fr_cli/config.json 的 cron 命名空间。
旧文件 ~/.fr_cli/cron.json 会在首次加载时一次性迁移。
"""
import threading
import subprocess
import shlex
from datetime import datetime
from pathlib import Path

from croniter import croniter

from fr_cli.ui.ui import RED, GREEN, DIM, YELLOW, RESET
from fr_cli.lang.i18n import T
from fr_cli.conf.config import load_namespace, save_namespace


# 保留用于一次性迁移（已弃用，新数据写入 ~/.fr_cli/config.json）
CRON_STORE_FILE = Path.home() / ".fr_cli" / "cron.json"

# 最小执行间隔（秒）—— interval 模式限制，cron/at 模式不受此限制
MIN_INTERVAL = 5


def _parse_schedule(spec):
    """解析调度规格，返回 (mode, value) 元组。

    支持：
      - "every 60s" / "every 60" / "interval:60"  → ("interval", 60.0)
      - "0 9 * * *" / "cron:0 9 * * *"            → ("cron", "0 9 * * *")
      - "2026-12-31 23:59:59" / "at:..."           → ("at", datetime)

    如果无法解析，抛 ValueError。
    """
    if not spec or not isinstance(spec, str):
        raise ValueError(f"无效的调度规格: {spec!r}")

    s = spec.strip()

    # at: 模式
    if s.startswith("at:"):
        return ("at", datetime.fromisoformat(s[3:].strip()))
    # ISO 时间
    try:
        return ("at", datetime.fromisoformat(s))
    except ValueError:
        pass

    # every 模式（旧式 interval 兼容）
    if s.startswith("every"):
        rest = s[5:].strip().rstrip("sS").strip()
        try:
            return ("interval", float(rest))
        except ValueError:
            raise ValueError(f"无法解析 interval: {spec!r}")
    if s.startswith("interval:"):
        try:
            return ("interval", float(s[9:].strip()))
        except ValueError:
            raise ValueError(f"无法解析 interval: {spec!r}")

    # cron: 前缀或裸 cron 表达式
    if s.startswith("cron:"):
        s = s[5:].strip()

    # 用 croniter 验证是否为合法 cron 表达式
    try:
        croniter(s, datetime.now())
        return ("cron", s)
    except Exception as e:
        raise ValueError(f"无效的 cron 表达式: {spec!r} ({e})")


def _next_run(mode, value, after=None):
    """计算下一次执行时间（datetime）。

    mode = "interval":  value 是秒数 → after + timedelta
    mode = "cron":      value 是 cron 表达式 → croniter.get_next
    mode = "at":        value 是 datetime → 直接返回
    """
    base = after or datetime.now()
    if mode == "interval":
        from datetime import timedelta
        return base + timedelta(seconds=float(value))
    if mode == "cron":
        return croniter(value, base).get_next(datetime)
    if mode == "at":
        return value
    raise ValueError(f"未知调度模式: {mode}")


class CronManager:
    """定时任务管理器 —— 任务调度器"""

    def __init__(self):
        self.jobs = []
        self._job_id_counter = 0
        self._lock = threading.Lock()

    def _resolve_state(self, state_provider):
        """解析最新 state 对象，避免闭包捕获旧引用"""
        if state_provider is None:
            return None
        if callable(state_provider):
            try:
                return state_provider()
            except Exception:
                return None
        return state_provider

    def _execute_job(self, job):
        """执行一次任务（不分调度模式）"""
        job_id = job["id"]
        cmd = job["cmd"]
        job_type = job.get("job_type", "shell")
        agent_name = job.get("agent_name")
        agent_input = job.get("agent_input", "")
        state_provider = job.get("state_provider")

        state = self._resolve_state(state_provider)

        try:
            if job_type == "agent" and agent_name:
                if state is None:
                    print(f"{RED}[Cron {job_id}] Error: Agent 任务需要 AppState{RESET}")
                    return False  # 不再注册下次
                from fr_cli.agent.executor import run_agent
                agent_result = run_agent(agent_name, state, user_input=agent_input)
                out = (agent_result.unwrap_or("") or "")[:200]
                if agent_result.is_fail():
                    out = f"Error: {agent_result.error}"
                print(f"{DIM}[Cron {job_id}] Agent[{agent_name}]{RESET} {out}")
            else:
                try:
                    cmd_list = shlex.split(cmd)
                except ValueError:
                    cmd_list = [cmd]
                res = subprocess.run(cmd_list, shell=False, capture_output=True, text=True, timeout=30)
                out = res.stdout.strip()[:100]
                print(f"{DIM}[Cron {job_id}]{RESET} {out}")
            return True
        except Exception as e:
            print(f"{RED}[Cron {job_id}] Error: {e}{RESET}")
            return False

    def _schedule_next(self, job):
        """根据 job 的调度模式注册下一次执行。

        interval 模式：用 threading.Timer 实现
        cron / at 模式：用绝对时间，sleep 等待
        at 模式是一次性的，执行后从 jobs 列表移除
        """
        mode = job["mode"]
        value = job["value"]

        if mode == "interval":
            interval = float(value)
            job["timer"] = threading.Timer(interval, self._runner_wrapper, args=(job,))
            job["timer"].daemon = True
            job["timer"].start()
            return

        # cron / at 模式：用绝对时间 sleep
        # at 模式: value 可能是 ISO 字符串,需要转回 datetime
        if mode == "at" and isinstance(value, str):
            try:
                value_dt = datetime.fromisoformat(value)
            except ValueError:
                return
        else:
            value_dt = value
        next_at = _next_run(mode, value_dt)
        now = datetime.now()
        delay = max((next_at - now).total_seconds(), 0.1)
        job["next_run"] = next_at.isoformat()
        job["timer"] = threading.Timer(delay, self._runner_wrapper, args=(job,))
        job["timer"].daemon = True
        job["timer"].start()

    def _runner_wrapper(self, job):
        """统一执行入口：执行任务 → 处理一次性/at 任务清理 → 注册下一次"""
        # 一次性任务：执行后从列表移除
        is_one_shot = job["mode"] == "at"

        self._execute_job(job)

        if is_one_shot:
            with self._lock:
                if job in self.jobs:
                    self.jobs.remove(job)
            self._persist()
            return

        # 注册下一次
        self._schedule_next(job)
        self._persist()

    def add_job(
        self,
        cmd=None,
        interval=None,
        lang="zh",
        schedule=None,
        job_type="shell",
        agent_name=None,
        agent_input="",
        state=None,
        state_provider=None,
    ):
        """添加一个定时任务。

        新接口（推荐）：add_job(schedule="0 9 * * *", cmd="echo morning", ...)
        旧接口（向后兼容）：add_job(cmd="echo hi", interval=60, ...)
        """
        # 旧式调用兼容：interval 为秒数
        if interval is not None and schedule is None:
            try:
                interval = float(interval)
            except (TypeError, ValueError):
                return None, f"{RED}Invalid seconds{RESET}"
            if interval < MIN_INTERVAL:
                return None, f"{RED}间隔不能小于 {MIN_INTERVAL} 秒(当前: {interval}s){RESET}"
            mode, value = "interval", interval
        elif schedule is not None:
            try:
                mode, value = _parse_schedule(schedule)
            except ValueError as e:
                return None, f"{RED}{e}{RESET}"
            if mode == "interval" and float(value) < MIN_INTERVAL:
                return None, f"{RED}间隔不能小于 {MIN_INTERVAL} 秒{RESET}"
        else:
            return None, f"{RED}必须指定 schedule 或 interval{RESET}"

        # 包装 state_provider
        if state_provider is None and state is not None:
            state_ref = {"current": state}
            state_provider = lambda: state_ref["current"]

        with self._lock:
            self._job_id_counter += 1
            job_id = self._job_id_counter
            job = {
                "id": job_id,
                "mode": mode,
                "value": value if mode != "at" else value.isoformat(),
                "cmd": cmd,
                "lang": lang,
                "timer": None,
                "job_type": job_type,
                "agent_name": agent_name,
                "agent_input": agent_input,
                "state_provider": state_provider,
            }
            self.jobs.append(job)

        # 注册第一次
        self._schedule_next(job)
        self._persist()
        return job_id, T("cron_ok", lang, job_id, _schedule_desc(mode, value))

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
            sched = _schedule_desc(j["mode"], j["value"])
            res.append(
                f"{GREEN}ID:{j['id']}{RESET} | {type_tag} | {YELLOW}{sched}{RESET} | {target[:30]}"
            )
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
        self._persist()
        return True, T("cron_killed", lang, job_id)

    def _persist(self):
        """将任务配置持久化到 ~/.fr_cli/config.json 的 cron 命名空间（不含线程对象）"""
        try:
            save_namespace("cron", self.export_jobs())
        except Exception:
            pass

    def load_persistent_jobs(self, lang="zh", state=None, state_provider=None):
        """从 ~/.fr_cli/config.json 的 cron 命名空间恢复定时任务"""
        try:
            # 动态计算老文件路径（避免 monkeypatch 不生效）
            from fr_cli.conf import paths as _paths
            old_path = _paths.ROOT / "cron.json"
            jobs = load_namespace("cron", default=list, old_path=old_path)
            if isinstance(jobs, list):
                self.import_jobs(jobs, lang=lang, state=state, state_provider=state_provider)
        except Exception:
            pass

    def sync_jobs(self, job_configs, lang="zh", state=None, state_provider=None):
        """同步任务列表：根据配置增删任务，保持当前任务与配置一致"""
        with self._lock:
            current_ids = {j["id"] for j in self.jobs}
            target_ids = {j.get("id") for j in job_configs if j.get("id")}

            for j in list(self.jobs):
                if j["id"] not in target_ids:
                    if j["timer"]:
                        j["timer"].cancel()
                    self.jobs.remove(j)

        for cfg in job_configs:
            jid = cfg.get("id")
            if jid and jid not in current_ids:
                self._add_from_config(cfg, lang=lang, state=state, state_provider=state_provider)
        self._persist()

    def export_jobs(self):
        """导出所有定时任务为可持久化的字典列表（不含线程对象）"""
        with self._lock:
            jobs_copy = list(self.jobs)
        result = []
        for j in jobs_copy:
            mode = j["mode"]
            value = j["value"]
            # 把 datetime 转回字符串
            if mode == "at" and isinstance(value, datetime):
                value = value.isoformat()
            result.append({
                "id": j["id"],
                "mode": mode,
                "value": value,
                "cmd": j["cmd"],
                "lang": j.get("lang", "zh"),
                "job_type": j.get("job_type", "shell"),
                "agent_name": j.get("agent_name"),
                "agent_input": j.get("agent_input", ""),
            })
        return result

    def import_jobs(self, jobs, lang="zh", state=None, state_provider=None):
        """从字典列表恢复定时任务"""
        for job in jobs:
            try:
                self._add_from_config(job, lang=lang, state=state, state_provider=state_provider)
            except Exception:
                pass

    def _add_from_config(self, cfg, lang="zh", state=None, state_provider=None):
        """从配置字典添加任务（处理新旧两种格式）"""
        # 旧式配置只有 interval，没有 mode
        if "mode" not in cfg:
            interval = float(cfg.get("interval", 60))
            return self.add_job(
                interval=interval,
                cmd=cfg.get("cmd", ""),
                lang=cfg.get("lang", lang),
                job_type=cfg.get("job_type", "shell"),
                agent_name=cfg.get("agent_name"),
                agent_input=cfg.get("agent_input", ""),
                state=state,
                state_provider=state_provider,
            )
        # 新式配置
        mode = cfg["mode"]
        value = cfg["value"]
        # at 模式需要把字符串转回 datetime
        if mode == "at" and isinstance(value, str):
            value = datetime.fromisoformat(value)
        return self.add_job(
            schedule=f"{mode}:{value.isoformat() if isinstance(value, datetime) else value}",
            cmd=cfg.get("cmd", ""),
            lang=cfg.get("lang", lang),
            job_type=cfg.get("job_type", "shell"),
            agent_name=cfg.get("agent_name"),
            agent_input=cfg.get("agent_input", ""),
            state=state,
            state_provider=state_provider,
        )


def _schedule_desc(mode, value):
    """把调度规格格式化成可读字符串。"""
    if mode == "interval":
        return f"every {value}s"
    if mode == "cron":
        return f"cron: {value}"
    if mode == "at":
        if isinstance(value, datetime):
            return f"at: {value.isoformat()}"
        return f"at: {value}"
    return f"{mode}: {value}"


# ------------------------------------------------------------------
# 默认全局实例（保持向后兼容）
# ------------------------------------------------------------------
_default_manager = CronManager()
JOBS = _default_manager.jobs


def add_job(cmd=None, interval=None, lang="zh", schedule=None, **_unused):
    """添加定时任务（向后兼容旧接口）。

    支持两种调用：
      - 旧式：add_job(cmd, interval, lang)
      - 新式：add_job(cmd=..., schedule=..., lang=...)
    """
    if schedule is not None:
        return _default_manager.add_job(cmd=cmd, schedule=schedule, lang=lang)
    return _default_manager.add_job(cmd=cmd, interval=interval, lang=lang)


def list_jobs(lang="zh"):
    """列出定时任务（委托给默认管理器）"""
    return _default_manager.list_jobs(lang)


def del_job(job_id, lang="zh"):
    """删除定时任务（委托给默认管理器）"""
    return _default_manager.del_job(job_id, lang)
