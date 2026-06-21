"""
计划模式 —— 运筹帷幄

让 LLM 先识别用户意图、自主生成结构化可执行计划，
经用户确认后按步骤调用现有工具（读/写文件、搜索、Agent 等）完成任务，
最后汇总执行结果。

模块拆分：
- prompts: PLAN_PROMPT_ZH / PLAN_PROMPT_EN / SUMMARY_PROMPT_*
- generator: generate_plan / render_plan / _get_tools_text / _clean_json_text / _try_parse_json
- executor: execute_step / execute_plan / _resolve_step_params / _fold_text / summarize_execution
- storage: PLANS_DIR / save_plan / load_plan / list_saved_plans
"""
from fr_cli.core.plan.prompts import (
    PLAN_PROMPT_EN,
    PLAN_PROMPT_ZH,
    SUMMARY_PROMPT_EN,
    SUMMARY_PROMPT_ZH,
)
from fr_cli.core.plan.generator import (
    _clean_json_text,
    _get_tools_text,
    _try_parse_json,
    generate_plan,
    render_plan,
)
from fr_cli.core.plan.executor import (
    _fold_text,
    _resolve_step_params,
    execute_plan,
    execute_step,
    summarize_execution,
)
from fr_cli.core.plan.storage import (
    PLANS_DIR,
    list_saved_plans,
    load_plan,
    save_plan,
)

# 旧式兼容：保留旧模块顶层引用（测试 patch 用）
from fr_cli.core.stream import stream_cnt

# 修复测试 patch 路径不命中：让 generator / executor 等子模块使用本包的 stream_cnt，
# 从而 `patch("fr_cli.core.plan.stream_cnt")` 能替换它们实际调用的对象。
from fr_cli.core.plan import generator as _generator_mod
from fr_cli.core.plan import executor as _executor_mod
_generator_mod.stream_cnt = stream_cnt
_executor_mod.stream_cnt = stream_cnt
del _generator_mod, _executor_mod