"""
Hermes 功能模块
参考 NousResearch/hermes-agent 实现核心功能

整合:
- TaskManager: 任务管理
- Analytics: 分析统计
- GoalTracker: 目标追踪
- ConfigManager: 配置管理
- CronScheduler: 定时任务
- SkillManager: 技能系统 (见 skills.py)
- PersonalityManager: 个性系统 (见 personality.py)
- ContextFilesManager: 上下文文件 (见 context_files.py)
"""

import os
import json
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


@dataclass
class Task:
    """任务"""
    id: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    result: Optional[str] = None
    error: Optional[str] = None


class TaskManager:
    """任务管理器 - Hermes 核心功能"""

    def __init__(self):
        self.tasks: Dict[str, Task] = {}
        self.history: List[Task] = []
        self._task_counter = 0

    def create_task(self, description: str) -> Task:
        """创建任务"""
        self._task_counter += 1
        task_id = f"task-{self._task_counter}-{int(time.time())}"
        task = Task(id=task_id, description=description)
        self.tasks[task_id] = task
        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        return self.tasks.get(task_id)

    def complete_task(self, task_id: str, result: str):
        """完成任务"""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.status = TaskStatus.COMPLETED
            task.result = result
            self.history.append(task)
            del self.tasks[task_id]

    def fail_task(self, task_id: str, error: str):
        """任务失败"""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.status = TaskStatus.FAILED
            task.error = error
            self.history.append(task)
            del self.tasks[task_id]

    def list_tasks(self) -> List[Task]:
        """列出所有任务"""
        return list(self.tasks.values())

    def list_history(self, limit: int = 50) -> List[Task]:
        """列出历史任务"""
        return self.history[-limit:]


class GoalTracker:
    """目标追踪器"""

    def __init__(self):
        self.goals: List[Dict] = []
        self.current_goal: Optional[Dict] = None

    def set_goal(self, description: str, milestones: List[str] = None):
        """设置目标"""
        goal = {
            "description": description,
            "milestones": milestones or [],
            "progress": 0,
            "started_at": time.time(),
            "steps": []
        }
        self.current_goal = goal
        self.goals.append(goal)
        return goal

    def update_progress(self, step: str, progress: float = None):
        """更新进度"""
        if self.current_goal:
            self.current_goal["steps"].append({
                "step": step,
                "time": time.time()
            })
            if progress is not None:
                self.current_goal["progress"] = progress

    def complete_goal(self):
        """完成目标"""
        if self.current_goal:
            self.current_goal["completed_at"] = time.time()
            self.current_goal = None


class Analytics:
    """分析统计"""

    def __init__(self):
        self.stats = {
            "total_requests": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "successful_tasks": 0,
            "failed_tasks": 0,
            "models_used": {},
            "start_time": time.time()
        }

    def record_request(self, model: str, tokens: int, cost: float):
        """记录请求"""
        self.stats["total_requests"] += 1
        self.stats["total_tokens"] += tokens
        self.stats["total_cost"] += cost

        if model not in self.stats["models_used"]:
            self.stats["models_used"][model] = {"requests": 0, "tokens": 0}
        self.stats["models_used"][model]["requests"] += 1
        self.stats["models_used"][model]["tokens"] += tokens

    def record_task(self, success: bool):
        """记录任务"""
        if success:
            self.stats["successful_tasks"] += 1
        else:
            self.stats["failed_tasks"] += 1

    def get_stats(self) -> Dict:
        """获取统计"""
        uptime = time.time() - self.stats["start_time"]
        return {
            **self.stats,
            "uptime_seconds": uptime,
            "success_rate": (
                self.stats["successful_tasks"] /
                max(1, self.stats["successful_tasks"] + self.stats["failed_tasks"])
            )
        }

    def format_report(self) -> str:
        """格式化报告"""
        stats = self.get_stats()
        return f"""
📊 Hermes 分析报告
==================
运行时间: {stats['uptime_seconds']:.0f} 秒
总请求数: {stats['total_requests']}
总 Token: {stats['total_tokens']:,}
总费用: ${stats['total_cost']:.4f}
成功率: {stats['success_rate']*100:.1f}%

模型使用:
{''.join(f"  - {m}: {v['requests']} 次\n" for m, v in stats['models_used'].items())}
"""


class ConfigManager:
    """配置管理器 - 支持环境变量和配置文件"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        """初始化"""
        self.config = {}
        self._load_env()
        self._load_config_file()

    def _load_env(self):
        """从环境变量加载"""
        for key in ["ZHIPU_API_KEY", "MOONSHOT_API_KEY", "DEEPSEEK_API_KEY",
                    "QWEN_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"]:
            if key in os.environ:
                provider = key.lower().replace("_api_key", "")
                if "zhipu" in provider:
                    provider = "zhipu"
                elif "moonshot" in provider or "kimi" in provider:
                    provider = "kimi"
                elif "deepseek" in provider:
                    provider = "deepseek"
                elif "qwen" in provider:
                    provider = "qwen"
                self.config.setdefault("providers", {})
                self.config["providers"].setdefault(provider, {})
                self.config["providers"][provider]["key"] = os.environ[key]

    def _load_config_file(self):
        """从配置文件加载"""
        config_paths = [
            os.path.expanduser("~/.fr_cli/config.json"),
            os.path.expanduser("~/.hermes/config.json"),
            "./config.json"
        ]

        for path in config_paths:
            if os.path.exists(path):
                try:
                    with open(path) as f:
                        data = json.load(f)
                        self.config.update(data)
                except:
                    pass

    def get(self, key: str, default=None):
        """获取配置"""
        keys = key.split(".")
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default

    def set(self, key: str, value: Any):
        """设置配置"""
        keys = key.split(".")
        config = self.config
        for k in keys[:-1]:
            config = config.setdefault(k, {})
        config[keys[-1]] = value

    def save(self):
        """保存配置"""
        path = os.path.expanduser("~/.fr_cli/config.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(self.config, f, indent=2)


class CronScheduler:
    """定时任务调度器"""

    def __init__(self):
        self.jobs: List[Dict] = []
        self.running = False

    def add_job(self, name: str, schedule: str, command: str):
        """添加定时任务"""
        job = {
            "name": name,
            "schedule": schedule,
            "command": command,
            "last_run": None,
            "next_run": None,
            "enabled": True
        }
        self.jobs.append(job)
        return job

    def remove_job(self, name: str) -> bool:
        """移除定时任务"""
        self.jobs = [j for j in self.jobs if j["name"] != name]
        return True

    def list_jobs(self) -> List[Dict]:
        """列出所有任务"""
        return self.jobs

    def run_job(self, name: str) -> bool:
        """运行任务"""
        for job in self.jobs:
            if job["name"] == name:
                job["last_run"] = time.time()
                return True
        return False


# 全局实例
_task_manager = None
_analytics = None
_config = None
_cron = None

def get_task_manager() -> TaskManager:
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager

def get_analytics() -> Analytics:
    global _analytics
    if _analytics is None:
        _analytics = Analytics()
    return _analytics

def get_config_manager() -> ConfigManager:
    return ConfigManager()

def get_cron_scheduler() -> CronScheduler:
    global _cron
    if _cron is None:
        _cron = CronScheduler()
    return _cron