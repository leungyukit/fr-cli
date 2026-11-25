"""
pipeline.py —— 直接对话模式主流程(传统 ReAct/CoT/普通对话)

handle_ai_chat 编排:
  1. _route_mode        入口路由(plan / master / direct)
  2. _resolve_intent     工具加载 + 思维推演 + intent 判定
  3. _assemble_prompt    system prompt 组装 + 工具/Agent/MCP 注入
  4. _stream_and_respond 流式调用 + 错误处理 + 命令自动执行
  5. _multi_source_blend 多源信息汇总第二轮
  6. _post_process       统计 / 推荐 / 产物检测 / 记忆 / 存档

模块拆分(原单文件 488 行,按阶段拆为 3 个文件):
- pipeline_intent.py:  阶段 1+2(_resolve_intent / _assemble_prompt / _build_tools_info)
- pipeline_respond.py: 阶段 3+4(_maybe_run_local_plugin / _stream_and_respond / _multi_source_blend)
- pipeline_post.py:    阶段 5(_post_process)
- pipeline.py:         本文件——路由 + _direct_chat 编排 + 各阶段符号 re-export

公开入口不变: from fr_cli.core.chat import handle_ai_chat
"""
from __future__ import annotations

import copy

from fr_cli.core.headless import is_headless
from fr_cli.core.errors import report_error
from fr_cli.lang.i18n import T
from fr_cli.ui.ui import CYAN, RESET, YELLOW, print_styled

from fr_cli.core.chat.helpers import auto_compress_messages
from fr_cli.core.chat.pipeline_intent import (  # noqa: F401 (re-export,旧导入路径兼容)
    _assemble_prompt,
    _build_tools_info,
    _resolve_intent,
)
from fr_cli.core.chat.pipeline_respond import (  # noqa: F401 (re-export,旧导入路径兼容)
    _maybe_run_local_plugin,
    _multi_source_blend,
    _stream_and_respond,
)
from fr_cli.core.chat.pipeline_post import _post_process  # noqa: F401 (re-export)


# ============================================================
# 路由
# ============================================================


def handle_ai_chat(state, u):
    """处理 AI 正常对话流程

    v2.8.7+:无头模式(bot / 服务端进程)下不向 stdout 输出,
    回复正文通过 ``state.last_reply`` 回传。
    """
    headless = is_headless(state)
    # 模型未配置时阻止调用
    if not state.model_name:
        if not headless:
            print_styled(
                f"{YELLOW}[!] 模型未配置,请使用 {CYAN}/model <模型名>{YELLOW} 或 {CYAN}/model config{YELLOW} 选择模型。{RESET}"
            )
        return

    return _route_mode(state, u)


def _route_mode(state, u):
    """根据 thinking_mode / master_agent 状态路由到不同模式"""
    # Agent Team 协作模式（/agent_team on）—— 显式开关，优先级最高。
    # 用户主动开的团队协作（拆解 → 多成员并行 → 汇总）不该被计划模式或
    # MasterAgent 主控静默接管；关掉 /agent_team 即恢复原有路由顺序。
    from fr_cli.agent.team import is_team_enabled

    if is_team_enabled(state):
        from fr_cli.agent.team import handle_team_chat
        return handle_team_chat(state, u)

    # 计划模式:LLM 先制定结构化计划,用户确认后逐步执行
    if getattr(state, "thinking_mode", "direct") == "plan":
        from fr_cli.core.chat.plan_mode import handle_plan_mode
        return handle_plan_mode(state, u)

    # MasterAgent 自我进化主控模式接管(ReAct 循环 + 自主工具调用)
    if getattr(state, "master_agent", None) and state.master_agent.is_enabled():
        # 交互模式下 master_loop 已流式输出(markdown 实时渲染),这里不再重复打印;
        # Hermes 后台隔离运行走 silent,返回值由调用方存入任务结果
        result = state.master_agent.handle(u)
        # v2.8.7+:捕获回复正文(无头模式下 master_loop 不打印,必须从这里取)
        if isinstance(result, tuple) and result:
            try:
                state.last_reply = result[0] or ""
            except Exception:
                pass
        elif isinstance(result, str):
            state.last_reply = result
        return

    return _direct_chat(state, u)


# ============================================================
# 直接对话主流程
# ============================================================


def _direct_chat(state, u):
    """直接对话:工具加载 → system prompt → 流式调用 → 命令执行 → 多源汇总 → 收尾"""
    lang = state.lang
    prompt = u
    if state.vfs.cwd:
        prompt += T("ctx_dir", lang, state.vfs.cwd)

    intent, tools, reasoning_text = _resolve_intent(state, u, prompt, lang)
    system_content = _assemble_prompt(state, u, intent, tools, reasoning_text, lang)

    # 更新系统提示词
    # v2.8.7+:走加锁访问器,避免与后台 worker 线程竞态
    updated_messages = copy.deepcopy(state.get_messages())
    if not updated_messages or updated_messages[0]["role"] != "system":
        updated_messages.insert(0, {"role": "system", "content": system_content})
    else:
        updated_messages[0]["content"] = system_content
    updated_messages.append({"role": "user", "content": prompt})

    # 长会话自动压缩
    auto_compress_messages(state, updated_messages)

    # 插件命令前置拦截(以 /plugin_name 开头的输入)
    triggered = _maybe_run_local_plugin(state, prompt, lang, updated_messages)
    if triggered:
        return

    # 流式调用 + 命令执行 + 多源汇总
    txt, usage, response_time = _stream_and_respond(state, updated_messages, u, lang)
    if txt is None:
        # 流式调用失败:pipeline_respond 已广播 llm.failed,
        # 这里再补一条 error.occurred,让错误账本(ErrorLedger)也能收单
        report_error(RuntimeError("LLM 流式调用失败"), source="chat", stage="stream")
        return  # 流式调用失败

    # 收尾:统计 / 推荐 / 产物检测 / 记忆 / 存档
    try:
        return _post_process(state, updated_messages, txt, usage, response_time, u, lang)
    except Exception as exc:
        # v3.0+:错误集中上报(error.occurred)—— 异常照旧向上抛,只多一条事件
        report_error(exc, source="chat", stage="post_process")
        raise
