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

模块拆分(原单文件 439 行):
- cron_schedule.py: 调度规格解析 / 下次执行计算 / 描述(纯函数)
- cron.py:          本文件——CronManager(线程调度 + 持久化) + 默认实例
"""
import threading
import subprocess
import shlex
import weakref
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from fr_cli.ui.ui import RED, GREEN, DIM, YELLOW, RESET
from fr_cli.core.stream import _is_prompt_toolkit_stdout
from fr_cli.lang.i18n import T
from fr_cli.conf.config import load_namespace, save_namespace

from fr_cli.weapon.cron_schedule import (  # noqa: F401 (re-export,旧导入路径兼容)
    MIN_INTERVAL,
    _next_run,
    _parse_schedule,
    _schedule_desc,
)


# 保留用于一次性迁移（已弃用，新数据写入 ~/.fr_cli/config.json）
CRON_STORE_FILE = Path.home() / ".fr_cli" / "cron.json"


# ------------------------------------------------------------------
# patch_stdout 守卫
#
# job 跑在 threading.Timer 后台线程里，裸 print 会插进 prompt_toolkit 的
# 渲染帧，把补全菜单/提示栏劈碎（与 repl/queue.py 的 AI 回答线程同款处理）。
# prompt_toolkit 3.x 的 patch_stdout 退出时无条件恢复 sys.stdout，多个 job
# 并发执行时会互相冲掉代理，因此用引用计数让并发 job 共享同一个代理；
# 无 TUI 运行时 patch_stdout 自动退化为直写，无需判断环境。
# ------------------------------------------------------------------
class _PatchStdoutGuard:
    """进程内共享的 patch_stdout 引用计数守卫"""

    def __init__(self):
        self._lock = threading.Lock()
        self._cm = None
        self._refs = 0

    @staticmethod
    def _enter():
        """安装代理；prompt_toolkit 缺失或异常时返回 None（退化为直写）"""
        try:
            from prompt_toolkit.patch_stdout import patch_stdout
            cm = patch_stdout()
            cm.__enter__()
            return cm
        except Exception:
            return None

    def __call__(self):
        return self._guarded()

    @contextmanager
    def _guarded(self):
        with self._lock:
            if self._refs == 0:
                self._cm = self._enter()
            self._refs += 1
        try:
            yield
        finally:
            with self._lock:
                self._refs -= 1
                if self._refs == 0 and self._cm is not None:
                    cm, self._cm = self._cm, None
                    cm.__exit__(None, None, None)


_stdout_guard = _PatchStdoutGuard()


_color_disable_lock = threading.Lock()
_color_disable_depth = 0
_color_disable_orig = None


class _ProxyColorDisable:
    """patch_stdout 接管 stdout 期间临时禁用本模块颜色常量。

    StdoutProxy 非 raw 模式走 Vt100_Output.write()，该方法会把文本里的
    ESC 字节替换成字面 '?'（prompt_toolkit/output/vt100.py 的 "Removes
    vt100 escape codes -- used for safely writing text"），直接打印带色文本
    会让用户看到 ?[2m[Cron 1]?[0m 这类乱码。与 core/stream.py 的
    _ColorDisable 同款处理：接管期间输出纯文本，退出后恢复颜色。

    多个 job 并发执行时会嵌套/并行进入：颜色常量是模块级全局，直接
    保存/恢复会竞态——先退出的 job 把颜色恢复回真值，让仍在打印的
    并发 job 打出 ?[2m 乱码。因此与 _stdout_guard 同样用引用计数：
    只有最外层退出时才恢复。
    """

    def __enter__(self):
        global RED, GREEN, DIM, YELLOW, RESET
        global _color_disable_depth, _color_disable_orig
        with _color_disable_lock:
            if _color_disable_depth == 0:
                _color_disable_orig = (RED, GREEN, DIM, YELLOW, RESET)
                if _is_prompt_toolkit_stdout():
                    RED = GREEN = DIM = YELLOW = RESET = ""
            _color_disable_depth += 1
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        global RED, GREEN, DIM, YELLOW, RESET
        global _color_disable_depth, _color_disable_orig
        with _color_disable_lock:
            _color_disable_depth -= 1
            if _color_disable_depth == 0 and _color_disable_orig is not None:
                RED, GREEN, DIM, YELLOW, RESET = _color_disable_orig
                _color_disable_orig = None


# ------------------------------------------------------------------
# 活跃管理器登记簿
#
# CronManager 的计时器是 daemon 线程：进程退出时它们不会挡住收尾，
# 但在**进程存活期间**它们会持续触发。而每次触发都会进入
# _stdout_guard() —— prompt_toolkit.patch_stdout 是**进程级**的
# sys.stdout 替换，会把此刻其它线程的 print 全部劫持走
# （pytest 的 capsys 因此拿到空串，表现为"单跑通过、全量随机失败"）。
#
# 登记簿让"停掉所有定时任务"在任何地方都能做到：
#   * 应用退出 —— 不留后台线程在退出后继续裸写 stdout
#   * 测试夹具 teardown —— 不让计时器跨用例污染
# ------------------------------------------------------------------
_ACTIVE_MANAGERS = weakref.WeakSet()


class CronManager:
    """定时任务管理器 —— 任务调度器"""

    def __init__(self):
        self.jobs = []
        self._job_id_counter = 0
        self._lock = threading.Lock()
        # 停止标记：stop() 之后不再给已有任务续期
        self._stopped = False
        _ACTIVE_MANAGERS.add(self)

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

        # patch_stdout 代理接管 stdout 期间禁色：StdoutProxy 非 raw 模式走
        # Vt100_Output.write()，会把 ANSI 的 ESC 字节替换成字面 '?'，直接打色
        # 会显示 ?[2m[Cron 1]?[0m 这类乱码。与 core/stream.py 的 _ColorDisable
        # 同款处理：接管期间输出纯文本，退出后恢复颜色。
        with _ProxyColorDisable():
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
        # 已被 stop() 停掉的任务不再执行，也不再续期
        if self._stopped:
            return

        # 一次性任务：执行后从列表移除
        is_one_shot = job["mode"] == "at"

        # 整个执行过程（含 _execute_job 的 print 与 agent 输出）包进
        # patch_stdout 守卫，防止后台线程裸写劈碎 TUI 补全菜单
        with _stdout_guard():
            self._execute_job(job)

            if is_one_shot:
                with self._lock:
                    if job in self.jobs:
                        self.jobs.remove(job)
                self._persist()
                return

            # 注册下一次（stop() 可能在本次执行期间被调用）
            if self._stopped:
                return
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

        # 新任务意味着"要跑起来" —— 解除 stop() 留下的暂停标记
        self._stopped = False

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

    def stop(self, clear_persisted: bool = False) -> int:
        """停止所有定时任务（取消后台计时器）。

        计时器是 daemon 线程，进程退出时不会挡住收尾；但不取消的话它们
        会在进程存活期间继续触发，而每次触发都会进入 _stdout_guard() ——
        prompt_toolkit.patch_stdout 是**进程级**的 sys.stdout 替换，会把
        此刻其它线程/用例的 print 全部劫持走。

        Args:
            clear_persisted: 是否同时把任务从持久化配置里删掉。
                默认 False —— 只停"当前这一轮调度"，任务配置保留，
                下次启动仍会恢复（"暂停"而非"删除"）。

        Returns:
            int: 被停止的任务数
        """
        with self._lock:
            jobs = list(self.jobs)
            for job in jobs:
                timer = job.get("timer")
                if timer is not None:
                    try:
                        timer.cancel()
                    except Exception:
                        pass
                job["timer"] = None
            count = len(jobs)
            if clear_persisted:
                self.jobs.clear()
        # 置位后 _runner_wrapper 不再给已有任务续期
        self._stopped = True
        if clear_persisted:
            self._persist()
        return count

    def _persist(self):
        """将任务配置持久化到 ~/.fr_cli/config.json 的 cron 命名空间（不含线程对象）"""
        try:
            save_namespace("cron", self.export_jobs())
        except Exception:
            pass

    def load_persistent_jobs(self, lang="zh", state=None, state_provider=None):
        """从 ~/.fr_cli/config.json 的 cron 命名空间恢复定时任务

        幂等：重复调用不会产生重复任务（先停掉并清空当前任务，再按
        持久化配置重建）。这很重要 —— 恢复走的是**全局默认管理器**，
        AppState 每建一次就会调一次，不幂等就会把任务越堆越多。
        """
        try:
            # 动态计算老文件路径（避免 monkeypatch 不生效）
            from fr_cli.conf import paths as _paths
            old_path = _paths.ROOT / "cron.json"
            jobs = load_namespace("cron", default=list, old_path=old_path)
            if isinstance(jobs, list):
                # 先取快照再清空：clear_persisted=True 会把命名空间写成空，
                # 直接清会把刚读出来的持久化数据一起抹掉
                self.stop(clear_persisted=False)
                with self._lock:
                    self.jobs.clear()
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


def stop_all(clear_persisted: bool = False) -> int:
    """停止所有 CronManager 实例的定时任务。

    应用退出 / 测试夹具 teardown 用它把散落在各处的计时器一次收干净。

    Args:
        clear_persisted: 是否同时清掉持久化配置（默认保留）

    Returns:
        int: 被停止的任务总数
    """
    total = 0
    for mgr in list(_ACTIVE_MANAGERS):
        try:
            total += mgr.stop(clear_persisted=clear_persisted)
        except Exception:
            pass
    return total
