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
from fr_cli.ui.ui import DIM, RESET, print_styled

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
            # REPL 的 AI 对话跑在 patch_stdout 代理里, 裸 print 打色只会得到
            # ?[93m 乱码(StdoutProxy 非 raw 模式把 ESC 换成 '?'), 走 print_styled
            print_styled(f"{YELLOW}[!] 模型未配置，请使用 {CYAN}/model <模型名>{YELLOW} 或 {CYAN}/model config{YELLOW} 选择模型。{RESET}")
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

        # ---------- 强制规划步: 任务型输入先出 N 步计划, 再逐步执行 ----------
        # 门控是本地启发式(零成本): 短问候/纯咨询直接答; 任务型输入先让 LLM
        # 产出结构化计划并渲染展示, 再把计划(纯文本)作为 system 消息播种进
        # 下面的 ReAct 循环 —— 循环机制不变(工具调用/观察/记忆/反思全复用),
        # 只是每一步都在计划上下文里决策, 不再静默退化成一问一答。
        # 规划失败只打印一行提示后原样继续, 无回归。
        if self._needs_planning(user_input):
            plan = self._plan_for_task(user_input, lang)
            if plan:
                from fr_cli.core.plan.generator import render_plan
                from fr_cli.ui.ansi import strip_ansi

                plan_display = render_plan(plan, lang)
                print()
                print_styled(plan_display)
                print()
                # 播种: 剥掉 ANSI(省 token, 也避免模型模仿颜色码)
                messages.append({"role": "system", "content": (
                    "已为用户制定以下执行计划, 请严格按步骤推进:\n"
                    f"{strip_ansi(plan_display)}\n"
                    "每一步: 需要工具时, 只输出一个 JSON 对象描述工具调用"
                    "(可以用代码围栏包住), 形如 "
                    '{"tool": "工具名", "params": {参数}}, '
                    "拿到观察结果后进入下一步; 所有步骤完成后给出最终回答。"
                )})
                # 记入会话(中断恢复/复盘用)
                if isinstance(self.session.get("current_task"), dict):
                    self.session["current_task"]["plan"] = plan

        # 交互运行(REPL 对话)流式输出,让用户实时看到思考与最终回答;
        # Hermes 后台隔离运行保持 silent(输出进任务日志而非终端)
        isolated_run = context_messages is not None

        # ReAct 循环
        final_answer = None
        observations = []

        while self._step_count < self.MAX_STEPS:
            self._step_count += 1
            from fr_cli.core.stream import stream_cnt

            # 调用 LLM 获取 Thought + Action
            txt, usage, _, _ = stream_cnt(
                self.state.client, self.state.model_name, messages, lang,
                custom_prefix="", max_tokens=2048, silent=isolated_run
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
                    observation_lines.append(f"[x] 工具 {call['tool']} 失败: {error}")
                    self._record_interaction(user_input, call["tool"], False, error, tool_params=call.get("params", {}))
                else:
                    observation_lines.append(f"[OK] 工具 {call['tool']} 结果: {str(result)[:500]}")
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
                custom_prefix="", max_tokens=2048, silent=isolated_run
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
                    # 同上门控: patch_stdout 代理下打 DIM 只会得到 ?[2m...?[0m
                    print_styled(f"{DIM}自动会话已创建: {Path(path).name}{RESET}")
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
        格式 1（主路径，容错多形态）：见 toolcalls.extract_tool_calls ——
          认 tool_call XML 标签 / ```tool 等代码围栏 / 裸 JSON / 对象数组，
          键位兼容 tool+params、tool+arguments、name+arguments。
          旧实现只认 ```tool 围栏，live 实测 step-5-preview 的
          tool_call XML 形态被当成"最终答案"，工具从未执行（静默失败）。
        格式 2：【调用：tool_name({...})】（传统流式对话兼容格式）
        """
        calls = []

        # 格式 1：工具调用代码块（容错多形态，见 toolcalls.extract_tool_calls）
        # live 实测 step-5-preview 吐的是 tool_call XML 标签包裹的 JSON /
        # 裸 JSON / 普通围栏，旧实现只认 ```tool 围栏，导致工具调用被当成
        # "最终答案"、ReAct 循环一步退出、工具从未执行（静默失败）。
        from fr_cli.core.plan.toolcalls import extract_tool_calls
        for call in extract_tool_calls(text):
            calls.append({"tool": call["tool"], "params": call.get("params", {})})

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
