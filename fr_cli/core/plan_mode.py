"""
Plan mode 入口 —— 类似 Claude Code 的 EnterPlanMode/ExitPlanMode

流程:
  1. AI 调用 EnterPlanMode 工具 → 进入 plan 模式
  2. 系统调 LLM 生成执行计划
  3. 把计划展示给用户,等待用户输入:
     - y / enter → 批准,自动 ExitPlanMode → 顺序执行步骤
     - n → 拒绝,回到普通对话
     - e → 编辑(让用户修改计划)
  4. 用户批准后,ExitPlanMode 触发,自动按步骤执行

这样把分散在 /mode plan 和 Plan 模块的功能串成一个完整流程。
"""
import os
import sys
import json
from typing import Optional, Dict, Any, List

from fr_cli.core.result import Result


_PLAN_PENDING_KEY = "_plan_pending"


def _plan_file_for_session(session_id: str) -> str:
    """把 plan 临时存放在 context 文件旁边"""
    from fr_cli.conf.paths import CONTEXT_FILE
    parent = CONTEXT_FILE.parent
    return str(parent / f"plan_pending_{session_id}.json")


def save_pending_plan(session_id: str, plan: Dict[str, Any]) -> bool:
    """保存待审批的计划"""
    try:
        path = _plan_file_for_session(session_id)
        from fr_cli.core.store import JsonStore
        JsonStore(path, default=dict).write(plan)
        return True
    except Exception:
        return False


def load_pending_plan(session_id: str) -> Optional[Dict[str, Any]]:
    """加载待审批的计划"""
    try:
        path = _plan_file_for_session(session_id)
        from fr_cli.core.store import JsonStore
        data = JsonStore(path, default=None).read()
        return data if data else None
    except Exception:
        return None


def clear_pending_plan(session_id: str) -> bool:
    """清除待审批的计划(批准/拒绝后)"""
    try:
        path = _plan_file_for_session(session_id)
        if os.path.exists(path):
            os.remove(path)
        return True
    except Exception:
        return False


def enter_plan_mode(state, user_input: str) -> Result:
    """EnterPlanMode 工具实现。

    调用 LLM 生成执行计划,保存到 pending 文件,提示用户审批。
    """
    from fr_cli.core.plan.generator import generate_plan
    from fr_cli.core.plan.storage import save_plan

    plan = generate_plan(state, user_input, lang=state.lang if hasattr(state, "lang") else "zh")
    if plan is None:
        return Result.fail("计划生成失败:LLM 返回的内容无法解析")

    session_id = getattr(state, "session_id", None) or "default"
    if not save_pending_plan(session_id, plan):
        return Result.fail("计划保存失败")

    # 也保存到正式 plan 文件,便于后续加载
    try:
        save_plan(state, plan)
    except Exception:
        pass

    # 渲染展示
    from fr_cli.core.plan.generator import render_plan
    text = render_plan(plan, lang=state.lang if hasattr(state, "lang") else "zh")
    text += "\n\n" + "=" * 50 + "\n"
    text += "📋 计划已生成。请审批:\n"
    text += "  y / 回车 = 批准并执行\n"
    text += "  n = 拒绝,继续普通对话\n"
    text += "  e = 编辑计划\n"

    # 把 plan pending 标记到 state(让 main loop 知道进入审批)
    state._plan_pending = True
    state._plan_user_input = user_input

    return Result.ok(text)


def exit_plan_mode(state, approved: bool, edited_plan: Optional[Dict[str, Any]] = None) -> Result:
    """ExitPlanMode 工具实现。

    Args:
        approved: True=批准并执行,False=拒绝
        edited_plan: 用户编辑后的计划(可选)
    """
    session_id = getattr(state, "session_id", None) or "default"
    plan = edited_plan or load_pending_plan(session_id)
    if plan is None:
        return Result.fail("未找到待执行的计划")

    if not approved:
        clear_pending_plan(session_id)
        # 清理 state 标记
        state._plan_pending = False
        return Result.ok("计划已拒绝,继续普通对话")

    # 批准:执行计划
    from fr_cli.core.plan.executor import execute_plan
    results = execute_plan(state, plan, lang=state.lang if hasattr(state, "lang") else "zh")

    # 清理 pending
    clear_pending_plan(session_id)
    state._plan_pending = False

    # 汇总结果
    summary = "\n".join(f"步骤 {i+1}: {'✅' if ok else '❌'} {result[:80]}"
                        for i, (ok, result) in enumerate(results))
    success_count = sum(1 for ok, _ in results if ok)
    return Result.ok(
        f"计划执行完成 ({success_count}/{len(results)} 步成功):\n{summary}"
    )