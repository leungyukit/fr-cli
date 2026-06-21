"""
主控 Agent（MasterAgent）—— 自我进化型全能助手
类似 OpenClaw 的中央控制器，负责理解用户意图、规划执行、调用工具、反思进化。

通过 mixin 模式将不同职责拆分到独立子模块：
  master_storage.py        配置文件路径、默认值、文件 I/O、错误分类
  master_prompt.py         默认 system prompt 模板（中文/英文/规划/反思）
  master_prompt_builder.py  System Prompt 组装 mixin
  master_loop.py           ReAct 主循环 mixin
  master_reflect.py        反思进化 mixin

配置文件体系（~/.fr_cli/master/）：
  persona.md     — 人设文件（自定义系统人设，覆盖默认 prompt）
  skills.md      — 技能装备文件（特殊能力、高级用法描述）
  memory.json    — 交互记忆（成功/失败记录）
  evolution.json — 进化记录（prompt 追加、成功/失败模式统计）
  session.json   — 会话状态（当前任务、上下文延续）
  status.json    — 状态文件（启用状态、统计、时间戳）
"""
from fr_cli.agent.master_storage import (
    EVOLUTION_FILE,
    MEMORY_FILE,
    PERSONA_FILE,
    SESSION_FILE,
    SKILLS_FILE,
    STATUS_FILE,
    _classify_error,
    _DEFAULT_EVOLUTION,
    _DEFAULT_MEMORY,
    _DEFAULT_PERSONA,
    _DEFAULT_SESSION,
    _DEFAULT_SKILLS,
    _DEFAULT_STATUS,
    _ensure_all_master_files,
    _load_json,
    _load_text,
    _save_json,
)

# 旧式兼容：保留模块级 MASTER_DIR 引用，便于测试 monkeypatch.setattr(master, "MASTER_DIR", ...)
from fr_cli.conf.paths import MASTER_DIR  # noqa: E402,F401

# Mixin 组件
from fr_cli.agent.master_loop import MasterAgentLoopMixin
from fr_cli.agent.master_prompt_builder import MasterAgentPromptMixin
from fr_cli.agent.master_reflect import MasterAgentReflectMixin


class MasterAgent(
    MasterAgentLoopMixin,
    MasterAgentReflectMixin,
    MasterAgentPromptMixin,
):
    """
    主控 Agent —— 统一入口，自我进化

    核心循环（见 master_loop.MasterAgentLoopMixin.handle）：
      1. 接收用户输入
      2. 分析意图 → 判断是否需要工具
      3. 如需工具：规划 → 执行 → 观察 → 综合回答
      4. 记录交互 → 反思 → 进化
    """

    def __init__(self, state):
        self.state = state
        # 确保所有配置文件存在（有漏即补）
        _ensure_all_master_files()
        self.persona = _load_text(PERSONA_FILE, _DEFAULT_PERSONA)
        self.skills = _load_text(SKILLS_FILE, _DEFAULT_SKILLS)
        self.evolution = _load_json(EVOLUTION_FILE, _DEFAULT_EVOLUTION)
        self.memory = _load_json(MEMORY_FILE, _DEFAULT_MEMORY)
        self.session = _load_json(SESSION_FILE, _DEFAULT_SESSION)
        self._status_data = _load_json(STATUS_FILE, _DEFAULT_STATUS)
        self._step_count = 0

    # ---------- 状态管理 ----------

    def toggle(self, enabled=None):
        """启用/禁用 MasterAgent"""
        if enabled is None:
            enabled = not self._status_data.get("enabled", False)
        self._status_data["enabled"] = enabled
        # 同步到配置文件（兼容旧逻辑）
        self.state.cfg["master_agent_enabled"] = enabled
        self.state.save_cfg()
        _save_json(STATUS_FILE, self._status_data)
        return enabled

    def is_enabled(self):
        # 优先从 status.json 读取，兼容旧配置
        return self._status_data.get("enabled", self.state.cfg.get("master_agent_enabled", False))

    def status(self):
        """返回当前状态摘要"""
        total = len(self.memory.get("interactions", []))
        success = sum(1 for i in self.memory.get("interactions", []) if i["success"])
        failure = total - success
        addon = self.evolution.get("prompt_addon", "")[:80]
        return {
            "enabled": self.is_enabled(),
            "total_interactions": total,
            "success": success,
            "failure": failure,
            "evolution_count": self._status_data.get("evolution_count", 0),
            "evolution_addon": addon + "..." if len(addon) > 80 else addon,
            "last_active": self._status_data.get("last_active"),
            "created_at": self._status_data.get("created_at"),
            "current_task": self.session.get("current_task"),
        }