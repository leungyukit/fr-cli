"""
主控 Agent（MasterAgent）—— 自我进化型全能助手
类似 OpenClaw 的中央控制器，负责理解用户意图、规划执行、调用工具、反思进化。
"""
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

MASTER_DIR = Path.home() / ".fr_cli_master"
EVOLUTION_FILE = MASTER_DIR / "evolution.json"
MEMORY_FILE = MASTER_DIR / "memory.json"


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
        self.evolution = _load_json(EVOLUTION_FILE, {"success": [], "failure": [], "prompt_addon": ""})
        self.memory = _load_json(MEMORY_FILE, {"interactions": []})
        self._step_count = 0

    # ---------- 工具描述生成 ----------

    def _build_tools_desc(self):
        """从注册表动态生成工具描述文本"""
        from fr_cli.command.registry import get_registry
        reg = get_registry()
        lines = []
        for t in reg.get_tools():
            params_str = ", ".join(f"{k}:{v.__name__ if hasattr(v, '__name__') else str(v)}"
                                    for k, v in t.get("params", {}).items())
            lines.append(f"- {t['name']}: {t['description']}  参数: {params_str or '无'}")
        return "\n".join(lines)

    # ---------- 核心 ReAct 循环 ----------

    def handle(self, user_input):
        """
        处理用户输入的主入口。
        返回 (assistant_reply, should_continue)
        """
        self._step_count = 0
        lang = self.state.lang

        # 组装 system prompt
        tools_desc = self._build_tools_desc()
        from fr_cli.agent.master_prompt import MASTER_SYSTEM_PROMPT_ZH, MASTER_SYSTEM_PROMPT_EN
        base_prompt = MASTER_SYSTEM_PROMPT_ZH if lang == "zh" else MASTER_SYSTEM_PROMPT_EN
        system_content = base_prompt.format(tools_desc=tools_desc)
        if self.evolution.get("prompt_addon"):
            system_content += f"\n\n[进化补充提示]\n{self.evolution['prompt_addon']}"

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

        # 保存到 state.messages 以便会话连贯
        self.state.messages.append({"role": "user", "content": user_input})
        self.state.messages.append({"role": "assistant", "content": final_answer})

        # 触发反思与进化（异步感，实际同步执行）
        self._reflect_and_evolve(user_input, observations, final_answer)

        return final_answer, True

    # ---------- 工具调用解析 ----------

    @staticmethod
    def _extract_tool_calls(text):
        """从 assistant 回复中提取 ```tool 代码块"""
        calls = []
        pattern = r'```tool\s*\n(.*?)\n```'
        for m in re.finditer(pattern, text, re.DOTALL):
            try:
                data = json.loads(m.group(1).strip())
                if "tool" in data:
                    calls.append(data)
            except Exception:
                pass
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

    # ---------- 状态管理 ----------

    def toggle(self, enabled=None):
        """启用/禁用 MasterAgent"""
        if enabled is None:
            enabled = not self.state.cfg.get("master_agent_enabled", False)
        self.state.cfg["master_agent_enabled"] = enabled
        self.state.save_cfg()
        return enabled

    def is_enabled(self):
        return self.state.cfg.get("master_agent_enabled", False)

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
            "evolution_addon": addon + "..." if len(addon) > 80 else addon,
        }
