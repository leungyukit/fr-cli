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
import json
from typing import Optional, Dict, Any

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
    text = render_plan_for_user(plan, lang=state.lang if hasattr(state, "lang") else "zh")

    # 把 plan pending 标记到 state(让 main loop 知道进入审批)
    state._plan_pending = True
    state._plan_user_input = user_input

    return Result.ok(text)


def render_plan_for_user(plan: dict, lang: str = "zh") -> str:
    """渲染计划并附带审批指引"""
    from fr_cli.core.plan.generator import render_plan
    # 使用增强版 UI(颜色 + 进度条 + 估算)
    try:
        from fr_cli.core.plan_ui import render_plan_beautiful
        return render_plan_beautiful(plan, lang=lang)
    except Exception:
        # 回退到原版
        text = render_plan(plan, lang=lang)
        text += "\n\n" + "=" * 50 + "\n"
        text += "📋 计划已生成。请审批:\n"
        text += "  y / 回车 = 批准并执行\n"
        text += "  n = 拒绝,继续普通对话\n"
        text += "  e = 编辑计划(用自然语言描述修改)\n"
        text += "  s = 展示完整 JSON\n"
        return text


def edit_pending_plan(state, edit_instruction: str) -> Result:
    """让用户用自然语言修改计划

    Args:
        edit_instruction: 用户的修改指令(如"加一步:搜索最新 fr-cli 文档")
    """
    from fr_cli.core.plan.generator import generate_plan

    session_id = getattr(state, "session_id", None) or "default"
    current = load_pending_plan(session_id)
    if current is None:
        return Result.fail("未找到待编辑的计划")

    # 把当前计划 + 修改指令 一起发给 LLM,让它重新生成
    user_input = getattr(state, "_plan_user_input", "")
    edit_prompt = f"""原始需求: {user_input}

当前计划:
{json.dumps(current, ensure_ascii=False, indent=2)}

用户的修改指令: {edit_instruction}

请基于当前计划应用用户的修改,返回完整的新计划(包含原有步骤 + 修改)。
保持原有步骤,只修改必要的部分。"""

    new_plan = generate_plan(state, edit_prompt, lang=state.lang if hasattr(state, "lang") else "zh")
    if new_plan is None:
        return Result.fail("编辑后计划生成失败")

    save_pending_plan(session_id, new_plan)
    text = render_plan_for_user(new_plan, lang=state.lang if hasattr(state, "lang") else "zh")
    text = f"✅ 计划已根据指令更新。\n\n{text}"
    return Result.ok(text)


def show_pending_plan_json(state) -> Result:
    """展示完整 JSON 给用户看"""
    session_id = getattr(state, "session_id", None) or "default"
    current = load_pending_plan(session_id)
    if current is None:
        return Result.fail("未找到待查看的计划")
    return Result.ok(json.dumps(current, ensure_ascii=False, indent=2))


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

    # 使用增强版 UI 汇总(进度条 + 颜色 + 步骤详情)
    try:
        from fr_cli.core.plan_ui import render_execution_summary
        lang = state.lang if hasattr(state, "lang") else "zh"
        return Result.ok(render_execution_summary(results, plan, lang=lang))
    except Exception:
        # 回退
        summary = "\n".join(f"步骤 {i+1}: {'✅' if ok else '❌'} {result[:80]}"
                            for i, (ok, result) in enumerate(results))
        success_count = sum(1 for ok, _ in results if ok)
        return Result.ok(
            f"计划执行完成 ({success_count}/{len(results)} 步成功):\n{summary}"
        )
