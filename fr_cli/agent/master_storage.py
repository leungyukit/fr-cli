"""
MasterAgent 存储层：配置文件路径、默认值、文件 I/O、错误分类

将 master.py 中的工具方法抽出来，让主类 MasterAgent 只关注 ReAct 循环。
"""
import json
import threading
from datetime import datetime
from pathlib import Path

from fr_cli.conf.paths import MASTER_DIR

# ---------- 配置文件路径 ----------
PERSONA_FILE = MASTER_DIR / "persona.md"
SKILLS_FILE = MASTER_DIR / "skills.md"
MEMORY_FILE = MASTER_DIR / "memory.json"
EVOLUTION_FILE = MASTER_DIR / "evolution.json"
SESSION_FILE = MASTER_DIR / "session.json"
STATUS_FILE = MASTER_DIR / "status.json"

# ---------- 默认配置内容 ----------

_DEFAULT_PERSONA = """# MasterAgent 人设

你是用户的【个人电脑 AI 助手】，常驻于终端，像一位高效的私人助理兼技术搭档。

## 核心职责
1. **日常整理**：帮用户管理文件、整理笔记、归档资料、设置提醒/定时任务
2. **代码开发**：协助编写、审查、重构代码；管理项目文件；运行测试与构建
3. **信息获取**：搜索网络、读取文档、总结内容、对比方案
4. **系统操作**：在虚拟文件系统沙盒内安全地读写文件、执行 shell 命令（经用户确认）
5. **汇报结果**：用简洁清晰的中文向用户汇报执行结果，避免冗长

## 执行原则
- 优先使用已验证成功的工具组合
- 如果工具调用失败，分析原因并尝试替代方案
- 禁止执行 rm -rf、格式化磁盘等危险操作
- 不在 Thought 中编造不存在的信息
- 每次 Action 后等待 Observation 再继续
- 处理用户文件前先确认路径，避免误操作
"""

_DEFAULT_SKILLS = """# MasterAgent 技能装备

## 日常工作整理
- 文件管理：列出目录、读取文件内容、写入/追加/删除文件、批量重命名
- 笔记整理：将零散内容汇总为 Markdown 文档，自动添加标题和目录
- 资料归档：按日期或主题分类移动文件，创建结构化目录
- 定时任务：使用 cron_add 帮用户设置周期性提醒或脚本执行
- 邮件处理：读取收件箱、发送邮件、整理邮件摘要

## 代码开发协助
- 代码编写：根据需求生成代码并写入指定文件，保持项目结构清晰
- 代码审查：读取目标文件，分析潜在 bug、性能问题、安全漏洞，输出带行号的审查报告
- 重构优化：先搜索相关文件确认影响范围，制定最小侵入性修改方案，执行后验证
- 项目导航：快速定位关键文件（如 main.py、package.json、README 等），理解项目架构
- 调试辅助：读取日志、分析报错信息、建议修复方案

## 高级规划
- 可将复杂任务分解为最多8步的ReAct循环
- 支持多工具串联调用（如：搜索→整理→写入文件）
- 支持条件分支：根据中间结果调整后续步骤

## 自我进化
- 自动记录每次工具调用的成功/失败模式
- 每10次交互自动反思并生成进化提示词
- 优先使用高频成功工具，规避高频失败路径
- 进化提示词自动追加到 system prompt 中

## 状态感知
- 读取当前工作目录、可用工具列表
- 感知用户语言偏好（zh/en）
- 跟踪任务执行上下文，支持多轮修正
- 从 session.json 中恢复未完成的任务上下文
"""

_DEFAULT_SESSION = {
    "current_task": None,
    "task_history": [],
    "context_notes": "",
    "last_task_id": 0,
}

_DEFAULT_STATUS = {
    "enabled": True,  # v2.5+: 默认启用 MasterAgent,启动时自动接管普通对话
    "total_interactions": 0,
    "evolution_count": 0,
    "created_at": datetime.now().isoformat(),
    "last_active": None,
}

_DEFAULT_MEMORY = {"interactions": []}

_DEFAULT_EVOLUTION = {
    "success": [],
    "failure": [],
    "failure_hints": [],
    "prompt_addon": "",
}


def _classify_error(error: str) -> str:
    """将错误信息归类为简单的错误类型，用于失败模式统计。"""
    if not error:
        return "Unknown"
    error = str(error).lower()
    if "not found" in error or "不存在" in error or "file" in error and ("not" in error or "no such" in error):
        return "FileNotFound"
    if "permission" in error or "权限" in error:
        return "PermissionDenied"
    if "timeout" in error or "超时" in error:
        return "Timeout"
    if "network" in error or "连接" in error or "connection" in error:
        return "NetworkError"
    if "invalid" in error or "不合法" in error or "非法" in error:
        return "InvalidArgument"
    if "missing" in error or "缺少" in error:
        return "MissingParameter"
    return "ExecutionError"


# ---------- 文件 I/O ----------

_master_io_lock = threading.Lock()


def _ensure_master_dir():
    MASTER_DIR.mkdir(parents=True, exist_ok=True)


def _load_json(path: Path, default=None):
    with _master_io_lock:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                raise RuntimeError(f"读取 {path} 失败: {e}") from e
        return default if default is not None else {}


def _save_json(path: Path, data):
    with _master_io_lock:
        _ensure_master_dir()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            raise RuntimeError(f"写入 {path} 失败: {e}") from e


def _load_text(path: Path, default: str = ""):
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass
    return default


def _save_text(path: Path, content: str):
    _ensure_master_dir()
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        pass


def _ensure_all_master_files():
    """初始化所有 MasterAgent 配置文件（有漏即补）"""
    _ensure_master_dir()
    if not PERSONA_FILE.exists():
        _save_text(PERSONA_FILE, _DEFAULT_PERSONA)
    if not SKILLS_FILE.exists():
        _save_text(SKILLS_FILE, _DEFAULT_SKILLS)
    if not MEMORY_FILE.exists():
        _save_json(MEMORY_FILE, _DEFAULT_MEMORY)
    if not EVOLUTION_FILE.exists():
        _save_json(EVOLUTION_FILE, _DEFAULT_EVOLUTION)
    if not SESSION_FILE.exists():
        _save_json(SESSION_FILE, _DEFAULT_SESSION)
    if not STATUS_FILE.exists():
        _save_json(STATUS_FILE, _DEFAULT_STATUS)
