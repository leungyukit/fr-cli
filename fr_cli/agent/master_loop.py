"""
MasterAgent ReAct 主循环 Mixin

从 master.py 抽离出来，负责：
  - handle() 主入口（ReAct 循环）
  - _extract_tool_calls() 解析 assistant 回复中的工具调用
  - _execute_tool() 通过注册表执行工具

通过 mixin 模式挂载到 MasterAgent 类。

依赖：
  - MasterAgentReflectMixin 提供 _get_recent_memory / _get_failure_hint / _maybe_compress_messages
  - MasterAgentPromptMixin 提供 _build_system_prompt / _detect_artifacts
  - MasterAgent.__init__ 提供 self.state / self.session / self._status_data / self._step_count
"""
import json
import re
from datetime import datetime
from pathlib import Path

from fr_cli.memory.context import extract_recent_turns, build_context_summary, save_context
from fr_cli.memory.session import create_session, update_session
from fr_cli.ui.ui import DIM, RESET

from fr_cli.agent.master_storage import (
    SESSION_FILE,
    STATUS_FILE,
    _save_json,
)


class MasterAgentLoopMixin:
    """ReAct 主循环 mixin。

    需要 MasterAgent 提供：
      - self.state / self.session / self._status_data / self._step_count
      - self._build_system_prompt(lang)       （由 MasterAgentPromptMixin 提供）
      - self._get_recent_memory()             （由 MasterAgentReflectMixin 提供）
      - self._get_failure_hint(tool)          （由 MasterAgentReflectMixin 提供）
      - self._maybe_compress_messages(msgs)   （由 MasterAgentReflectMixin 提供）
      - self._reflect_and_evolve(...)         （由 MasterAgentReflectMixin 提供）
      - self._detect_artifacts(txt, lang, background)  （由 MasterAgentPromptMixin 提供）
    """

    MAX_STEPS = 8  # 单次任务最大工具调用步数

    # ---------- 核心 ReAct 循环 ----------

    def handle(self, user_input, context_messages=None, background=False, memory_hints=None):
        """
        处理用户输入的主入口。
        返回 (assistant_reply, should_continue)

        :param context_messages: 可选的独立消息列表。传入时，MasterAgent 不会把本轮对话
                                 追加到 state.messages，也不会更新用户主会话的上下文摘要
                                 和自动存档。用于 Hermes 后台任务隔离。
        :param background: 是否为后台任务。True 时禁用交互式产物检测，改为进入审核队列。
        :param memory_hints: 可选的跨任务历史摘要文本，会作为 system 消息注入。
        """
        # 模型未配置时阻止调用
        if not self.state.model_name:
            from fr_cli.ui.ui import YELLOW, CYAN
            print(f"{YELLOW}⚠️ 模型未配置，请使用 {CYAN}/model <模型名>{YELLOW} 或 {CYAN}/model config{YELLOW} 选择模型。{RESET}")
            return None, False

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

        if memory_hints:
            messages.insert(1, {"role": "system", "content": memory_hints})

        # 长上下文自动压缩（后台任务也受益）
        self._maybe_compress_messages(messages)

        # ReAct 循环
        final_answer = None
        observations = []

        while self._step_count < self.MAX_STEPS:
            self._step_count += 1
            from fr_cli.core.stream import stream_cnt

            # 调用 LLM 获取 Thought + Action
            txt, usage, _, _ = stream_cnt(
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
                # 注入历史失败提示，帮助模型规避已知错误
                hint = self._get_failure_hint(call["tool"])
                if hint:
                    messages.append({"role": "system", "content": f"[历史失败提示]\n{hint}"})

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
                    self._record_interaction(user_input, call["tool"], False, error, tool_params=call.get("params", {}))
                else:
                    observation_lines.append(f"✅ 工具 {call['tool']} 结果: {str(result)[:500]}")
                    self._record_interaction(user_input, call["tool"], True, str(result)[:200], tool_params=call.get("params", {}))

            observation_text = "\n".join(observation_lines)
            observations.append(observation_text)

            # 将观察和之前的 assistant 回复加入 messages
            messages.append({"role": "assistant", "content": txt})
            messages.append({"role": "user", "content": f"[系统观察结果]\n{observation_text}\n\n请基于以上结果继续思考或给出最终回答。"})

        if final_answer is None:
            # 达到最大步数仍未收敛，强制要求总结
            messages.append({"role": "user", "content": "已达到最大执行步数，请基于已有观察结果直接给出最终回答，不要再调用工具。"})
            self._maybe_compress_messages(messages)
            from fr_cli.core.stream import stream_cnt
            final_answer, _, _, _ = stream_cnt(
                self.state.client, self.state.model_name, messages, lang,
                custom_prefix="", max_tokens=2048, silent=True
            )
            # 将 assistant 的最终回答加入消息历史，保证会话连续性
            messages.append({"role": "assistant", "content": final_answer})

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

        # 触发反思与进化（异步感，实际同步执行）
        self._reflect_and_evolve(user_input, observations, final_answer)

        # ---------- 后处理：与传统模式对齐体验 ----------
        isolated_run = context_messages is not None
        target_messages = context_messages if isolated_run else self.state.messages

        # 保存到消息列表以便会话连贯（后台任务使用独立列表）
        target_messages.append({"role": "user", "content": user_input})
        target_messages.append({"role": "assistant", "content": final_answer})

        if not isolated_run:
            # 1. 更新上下文摘要（与传统模式共享同一套记忆系统）
            recent = extract_recent_turns(self.state.messages, 5)
            self.state.context_summary = build_context_summary(recent, lang)
            save_context(self.state.sn, self.state.context_summary)

            # 2. 自动按日期存档会话
            if not self.state.auto_session_path:
                path = create_session(self.state.messages, session_id=getattr(self.state, "session_id", None))
                if path:
                    self.state.auto_session_path = path
                    print(f"{DIM}📁 自动会话已创建: {Path(path).name}{RESET}")
            else:
                update_session(self.state.auto_session_path, self.state.messages)

            # 3. 智能插件/Agent 检测
            self._detect_artifacts(final_answer, lang, background=background)


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