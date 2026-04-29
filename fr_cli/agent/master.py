"""
主控 Agent（MasterAgent）—— 自我进化型全能助手
类似 OpenClaw 的中央控制器，负责理解用户意图、规划执行、调用工具、反思进化。

配置文件体系（~/.fr_cli_master/）：
  persona.md     — 人设文件（自定义系统人设，覆盖默认 prompt）
  skills.md      — 技能装备文件（特殊能力、高级用法描述）
  memory.json    — 交互记忆（成功/失败记录）
  evolution.json — 进化记录（prompt 追加、成功/失败模式统计）
  session.json   — 会话状态（当前任务、上下文延续）
  status.json    — 状态文件（启用状态、统计、时间戳）
"""
import json
import re
from datetime import datetime
from pathlib import Path

# 上下文记忆与会话存档
from fr_cli.memory.context import extract_recent_turns, build_context_summary, save_context
from fr_cli.memory.session import create_session, update_session
from fr_cli.addon.plugin import extract_code, PLUGIN_DIR
from fr_cli.ui.ui import RED, YELLOW, GREEN, DIM, RESET
from fr_cli.lang.i18n import T

MASTER_DIR = Path.home() / ".fr_cli_master"
PERSONA_FILE = MASTER_DIR / "persona.md"
SKILLS_FILE = MASTER_DIR / "skills.md"
MEMORY_FILE = MASTER_DIR / "memory.json"
EVOLUTION_FILE = MASTER_DIR / "evolution.json"
SESSION_FILE = MASTER_DIR / "session.json"
STATUS_FILE = MASTER_DIR / "status.json"

# ---------- 默认配置内容 ----------

_DEFAULT_PERSONA = """# MasterAgent 人设

你是 凡人打字机 的【主控Agent】——一位全能的AI助手兼系统指挥官。

## 核心职责
1. 深入理解用户需求，将复杂任务拆解为可执行的步骤
2. 调用系统工具完成用户的请求（文件、搜索、邮件、画图、定时任务等）
3. 观察工具执行结果，必要时进行多轮修正
4. 用中文向用户汇报最终结果

## 执行原则
- 优先使用已验证成功的工具组合
- 如果工具调用失败，分析原因并尝试替代方案
- 禁止执行 rm -rf、格式化磁盘等危险操作
- 不在 Thought 中编造不存在的信息
- 每次 Action 后等待 Observation 再继续
"""

_DEFAULT_SKILLS = """# MasterAgent 技能装备

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
    "enabled": False,
    "total_interactions": 0,
    "evolution_count": 0,
    "created_at": datetime.now().isoformat(),
    "last_active": None,
}

_DEFAULT_MEMORY = {"interactions": []}

_DEFAULT_EVOLUTION = {
    "success": [],
    "failure": [],
    "prompt_addon": "",
}


# ---------- 文件工具 ----------

def _ensure_master_dir():
    MASTER_DIR.mkdir(parents=True, exist_ok=True)


def _load_json(path, default=None):
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default if default is not None else {}


def _save_json(path, data):
    _ensure_master_dir()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _load_text(path, default=""):
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            pass
    return default


def _save_text(path, content):
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


class MasterAgent:
    """
    主控 Agent —— 统一入口，自我进化

    核心循环：
      1. 接收用户输入
      2. 分析意图 → 判断是否需要工具
      3. 如需工具：规划 → 执行 → 观察 → 综合回答
      4. 记录交互 → 反思 → 进化
    """

    MAX_STEPS = 8  # 单次任务最大工具调用步数

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

    # ---------- 工具描述生成 ----------

    def _build_tools_desc(self):
        """从注册表动态生成工具描述文本，同时包含可用Agent列表"""
        from fr_cli.command.registry import get_registry
        from fr_cli.agent.client import discover_all_agents
        reg = get_registry()
        lines = []
        for t in reg.get_tools():
            params_str = ", ".join(f"{k}:{v.__name__ if hasattr(v, '__name__') else str(v)}"
                                    for k, v in t.get("params", {}).items())
            lines.append(f"- {t['name']}: {t['description']}  参数: {params_str or '无'}")

        # 追加 MCP 外部神通
        mcp_manager = getattr(self.state, "mcp", None)
        if mcp_manager:
            try:
                mcp_tools = mcp_manager.list_all_tools()
                if mcp_tools:
                    lines.append("\n=== MCP 外部神通 ===")
                    for t in mcp_tools:
                        lines.append(f"- {t['name']}: {t['description']}  (服务器: {t['server']})")
                    lines.append("\n调用方式: mcp_call({\"server\": \"服务器名\", \"tool\": \"工具名\", \"arguments\": {...}})")
            except Exception:
                pass

        # 追加可用 Agent 列表（本地 + 远程）
        agents = discover_all_agents()
        if agents:
            lines.append("\n=== 可协作的独立Agent ===")
            for a in agents:
                lines.append(f"- [{a['type']}] {a['name']}: {a['description']}")
            lines.append("\n调用方式: agent_call({\"name\": \"Agent名\", \"user_input\": \"任务描述\"})")
        return "\n".join(lines)

    # ---------- System Prompt 组装 ----------

    def _build_system_prompt(self, lang):
        """组装完整的 system prompt：人设 + 技能 + 工具 + 进化追加"""
        from fr_cli.agent.master_prompt import MASTER_SYSTEM_PROMPT_ZH, MASTER_SYSTEM_PROMPT_EN
        base_prompt = MASTER_SYSTEM_PROMPT_ZH if lang == "zh" else MASTER_SYSTEM_PROMPT_EN

        parts = [base_prompt.format(tools_desc=self._build_tools_desc())]

        # 自定义人设（去重：如果 persona.md 内容与默认不同才追加）
        custom_persona = self.persona.strip()
        if custom_persona and custom_persona != _DEFAULT_PERSONA.strip():
            parts.append(f"\n[自定义人设]\n{custom_persona}")

        # 技能装备
        skills_text = self.skills.strip()
        if skills_text and skills_text != _DEFAULT_SKILLS.strip():
            parts.append(f"\n[技能装备]\n{skills_text}")

        # 进化追加
        if self.evolution.get("prompt_addon"):
            parts.append(f"\n[进化补充提示]\n{self.evolution['prompt_addon']}")

        # 会话上下文延续
        if self.session.get("context_notes"):
            parts.append(f"\n[会话上下文]\n{self.session['context_notes']}")

        return "\n".join(parts)

    # ---------- 核心 ReAct 循环 ----------

    def handle(self, user_input):
        """
        处理用户输入的主入口。
        返回 (assistant_reply, should_continue)
        """
        self._step_count = 0
        lang = self.state.lang

        # 更新状态
        self._status_data["last_active"] = datetime.now().isoformat()
        self._status_data["total_interactions"] = self._status_data.get("total_interactions", 0) + 1
        _save_json(STATUS_FILE, self._status_data)

        # 更新当前任务
        self.session["current_task"] = {
            "input": user_input,
            "started_at": datetime.now().isoformat(),
            "steps": [],
        }

        # 组装 system prompt
        system_content = self._build_system_prompt(lang)

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_input},
        ]

        # 追加短期记忆（最近5条成功/失败记录）
        recent_memory = self._get_recent_memory()
        if recent_memory:
            messages.insert(1, {"role": "system", "content": f"[近期记忆]\n{recent_memory}"})

        # ReAct 循环
        final_answer = None
        observations = []

        while self._step_count < self.MAX_STEPS:
            self._step_count += 1
            from fr_cli.core.stream import stream_cnt

            # 调用 LLM 获取 Thought + Action
            txt, usage, _ = stream_cnt(
                self.state.client, self.state.model_name, messages, lang,
                custom_prefix="", max_tokens=2048, silent=True
            )

            # 解析工具调用
            tool_calls = self._extract_tool_calls(txt)

            if not tool_calls:
                # 没有工具调用 → 直接作为最终答案
                final_answer = txt.strip()
                break

            # 有工具调用 → 执行并观察
            observation_lines = []
            for call in tool_calls:
                result, error = self._execute_tool(call["tool"], call.get("params", {}))
                step_info = {
                    "tool": call["tool"],
                    "params": call.get("params", {}),
                    "success": error is None,
                    "time": datetime.now().isoformat(),
                }
                self.session["current_task"]["steps"].append(step_info)
                if error:
                    observation_lines.append(f"❌ 工具 {call['tool']} 失败: {error}")
                    self._record_interaction(user_input, call["tool"], False, error)
                else:
                    observation_lines.append(f"✅ 工具 {call['tool']} 结果: {str(result)[:500]}")
                    self._record_interaction(user_input, call["tool"], True, str(result)[:200])

            observation_text = "\n".join(observation_lines)
            observations.append(observation_text)

            # 将观察和之前的 assistant 回复加入 messages
            messages.append({"role": "assistant", "content": txt})
            messages.append({"role": "user", "content": f"[系统观察结果]\n{observation_text}\n\n请基于以上结果继续思考或给出最终回答。"})

        if final_answer is None:
            # 达到最大步数仍未收敛，强制要求总结
            messages.append({"role": "user", "content": "已达到最大执行步数，请基于已有观察结果直接给出最终回答，不要再调用工具。"})
            from fr_cli.core.stream import stream_cnt
            final_answer, _, _ = stream_cnt(
                self.state.client, self.state.model_name, messages, lang,
                custom_prefix="", max_tokens=2048, silent=True
            )

        # 保存会话结果
        task = self.session["current_task"]
        task["finished_at"] = datetime.now().isoformat()
        task["final_answer"] = final_answer[:500]
        task["step_count"] = self._step_count
        self.session["task_history"].append(task)
        # 只保留最近 20 个任务历史
        self.session["task_history"] = self.session["task_history"][-20:]
        self.session["current_task"] = None
        # 提取上下文笔记（供下次对话延续）
        if final_answer and len(final_answer) > 50:
            self.session["context_notes"] = f"上一轮任务摘要：{user_input[:50]}... → {final_answer[:100]}..."
        _save_json(SESSION_FILE, self.session)

        # 保存到 state.messages 以便会话连贯
        self.state.messages.append({"role": "user", "content": user_input})
        self.state.messages.append({"role": "assistant", "content": final_answer})

        # 触发反思与进化（异步感，实际同步执行）
        self._reflect_and_evolve(user_input, observations, final_answer)

        # ---------- 后处理：与传统模式对齐体验 ----------

        # 1. 更新上下文摘要（与传统模式共享同一套记忆系统）
        recent = extract_recent_turns(self.state.messages, 5)
        self.state.context_summary = build_context_summary(recent, lang)
        save_context(self.state.sn, self.state.context_summary)

        # 2. 自动按日期存档会话
        if not self.state.auto_session_path:
            path = create_session(self.state.messages)
            if path:
                self.state.auto_session_path = path
                print(f"{DIM}📁 自动会话已创建: {Path(path).name}{RESET}")
        else:
            update_session(self.state.auto_session_path, self.state.messages)

        # 3. 智能法宝/Agent 检测
        self._detect_artifacts(final_answer, lang)

        # 4. 自动总结和知识库更新
        try:
            from fr_cli.agent.autosummary import get_knowledge_base
            from fr_cli.agent.autolearn import get_learner
            kb = get_knowledge_base()
            learner = get_learner()
            kb.update_from_conversation(user_input, final_answer)
            learner.learn_from_conversation(user_input, final_answer)
        except Exception:
            pass

        return final_answer, True

    # ---------- 工具调用解析 ----------

    @staticmethod
    def _extract_tool_calls(text):
        """
        从 assistant 回复中提取工具调用。
        同时支持两种格式：
          1. ```tool 代码块（MasterAgent 原生格式）
          2. 【调用：tool_name({...})】（传统流式对话兼容格式）
        """
        calls = []

        # 格式 1：```tool 代码块
        pattern = r'```tool\s*\n(.*?)\n```'
        for m in re.finditer(pattern, text, re.DOTALL):
            try:
                data = json.loads(m.group(1).strip())
                if "tool" in data:
                    calls.append(data)
            except Exception:
                pass

        # 格式 2：【调用：tool_name({...})】（兼容传统模式）
        i = 0
        while True:
            start = text.find('【调用：', i)
            if start == -1:
                break
            paren = text.find('(', start)
            if paren == -1:
                break
            tool_name = text[start + 4:paren].strip()
            # 匹配嵌套括号
            depth = 1
            end = paren + 1
            while end < len(text) and depth > 0:
                if text[end] == '(' and (end == 0 or text[end - 1] != '\\'):
                    depth += 1
                elif text[end] == ')' and (end == 0 or text[end - 1] != '\\'):
                    depth -= 1
                end += 1
            if depth != 0:
                break
            arg_str = text[paren + 1:end - 1]
            try:
                params = json.loads(arg_str)
                calls.append({"tool": tool_name, "params": params})
            except Exception:
                pass
            i = end

        return calls

    def _execute_tool(self, tool_name, params):
        """通过注册表执行工具"""
        from fr_cli.command.executor import _build_deps
        from fr_cli.command.registry import get_registry
        reg = get_registry()
        deps = _build_deps(self.state)
        return reg.dispatch(deps, tool_name, **params)

    # ---------- 记忆与进化 ----------

    def _record_interaction(self, user_input, tool_name, success, detail):
        """记录单次交互到内存"""
        self.memory.setdefault("interactions", []).append({
            "time": datetime.now().isoformat(),
            "input": user_input[:100],
            "tool": tool_name,
            "success": success,
            "detail": detail[:200],
        })
        # 只保留最近 100 条
        self.memory["interactions"] = self.memory["interactions"][-100:]
        _save_json(MEMORY_FILE, self.memory)

    def _get_recent_memory(self):
        """获取最近 5 条关键记忆摘要"""
        interactions = self.memory.get("interactions", [])
        if not interactions:
            return ""
        recent = interactions[-5:]
        lines = []
        for item in recent:
            status = "✅" if item["success"] else "❌"
            lines.append(f"{status} [{item['tool']}] {item['input']} → {item['detail'][:80]}")
        return "\n".join(lines)

    def _reflect_and_evolve(self, task, observations, result):
        """反思并触发自我进化（仅在积累足够数据时执行）"""
        interactions = self.memory.get("interactions", [])
        if len(interactions) < 5:
            return

        # 每 10 次交互触发一次进化
        if len(interactions) % 10 != 0:
            return

        # 统计成功/失败模式
        success_patterns = {}
        failure_patterns = {}
        for item in interactions[-50:]:
            tool = item["tool"]
            if item["success"]:
                success_patterns[tool] = success_patterns.get(tool, 0) + 1
            else:
                failure_patterns[tool] = failure_patterns.get(tool, 0) + 1

        # 更新进化数据
        self.evolution["success"] = sorted(success_patterns.items(), key=lambda x: x[1], reverse=True)[:5]
        self.evolution["failure"] = sorted(failure_patterns.items(), key=lambda x: x[1], reverse=True)[:5]

        # 生成进化提示词追加
        from fr_cli.agent.master_prompt import SELF_EVOLVE_PROMPT_ZH
        prompt = SELF_EVOLVE_PROMPT_ZH.format(
            success_patterns="\n".join(f"- {k}: {v}次" for k, v in self.evolution["success"]),
            failure_patterns="\n".join(f"- {k}: {v}次" for k, v in self.evolution["failure"]),
        )

        messages = [{"role": "user", "content": prompt}]
        from fr_cli.core.stream import stream_cnt
        addon, _, _ = stream_cnt(
            self.state.client, self.state.model_name, messages, self.state.lang,
            custom_prefix="", max_tokens=512, silent=True
        )
        addon = addon.strip()
        if addon and len(addon) < 500:
            self.evolution["prompt_addon"] = addon
            _save_json(EVOLUTION_FILE, self.evolution)

        # 更新进化计数
        self._status_data["evolution_count"] = self._status_data.get("evolution_count", 0) + 1
        _save_json(STATUS_FILE, self._status_data)

    # ---------- 法宝 / Agent 自动检测 ----------

    def _detect_artifacts(self, txt, lang):
        """检测 AI 回复中的插件/Agent 代码结构，提示用户保存"""
        if not txt:
            return

        # 智能法宝进化检测（插件）
        if "def run(args='')" in txt and "```python" in txt:
            code = extract_code(txt)
            if code and "def run" in code and len(code) > 50:
                try:
                    pname = input(f"{YELLOW}{T('artifact_detect', lang)}{RESET}").strip()
                    if pname:
                        safe_name = "".join(c for c in pname if c.isalnum() or c == '_')
                        if not safe_name:
                            print(f"{RED}名称无效，仅允许字母/数字/下划线{RESET}")
                        elif self.state.security.check("sec_write", f"/{safe_name}"):
                            PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
                            p_path = PLUGIN_DIR / f"{safe_name}.py"
                            p_path.write_text(code, encoding='utf-8')
                            self.state.plugins[safe_name] = str(p_path)
                            print(f"{GREEN}{T('ok_forged', lang, safe_name)}{RESET}")
                except EOFError:
                    pass

        # 智能 Agent 分身检测
        if "def run(context," in txt and "```python" in txt:
            code = extract_code(txt)
            if code and "def run(context," in code and len(code) > 50:
                try:
                    aname = input(f"{YELLOW}⚡ 检测到 Agent 分身结构，赐名 (回车放弃): {RESET}").strip()
                    if aname:
                        safe_name = "".join(c for c in aname if c.isalnum() or c == '_')
                        if not safe_name:
                            print(f"{RED}名称无效，仅允许字母/数字/下划线{RESET}")
                        else:
                            from fr_cli.agent.manager import create_agent_dir, save_agent_code, save_persona, save_skills, agent_exists
                            if agent_exists(safe_name):
                                confirm = input(f"{YELLOW}Agent [{safe_name}] 已存在，是否覆盖? [y/N]: {RESET}").strip().lower()
                                if confirm not in ("y", "yes"):
                                    print(f"{DIM}已取消。{RESET}")
                                else:
                                    d = create_agent_dir(safe_name)
                                    save_agent_code(safe_name, code)
                                    print(f"{GREEN}✅ Agent [{safe_name}] 已覆盖更新。{RESET}")
                                    print(f"{DIM}  路径: {d}{RESET}")
                            else:
                                d = create_agent_dir(safe_name)
                                save_agent_code(safe_name, code)
                                save_persona(safe_name, f"#{safe_name}\n\n由 AI 对话铸造的 Agent 分身。")
                                save_skills(safe_name, "## 技能\n\n- 执行自定义 Python 逻辑\n- 入口: run(context, **kwargs)")
                                print(f"{GREEN}✅ Agent [{safe_name}] 铸造完成！{RESET}")
                                print(f"{DIM}  路径: {d}{RESET}")
                                print(f"{DIM}  运行: /agent_run {safe_name} [参数]{RESET}")
                except EOFError:
                    pass

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
