"""
动态构建 —— 主流程编排

根据用户需求，自主规划、安装依赖、生成代码、保存并注册动态工具。
"""
from typing import Tuple

from fr_cli.ui.ui import CYAN, GREEN, RESET, YELLOW, DIM
from fr_cli.core.result import Result
from fr_cli.dynamic_builder.planner import plan_build
from fr_cli.dynamic_builder.dependency_manager import ensure_dependencies
from fr_cli.dynamic_builder.code_generator import generate_tool_code, extract_tool_name
from fr_cli.dynamic_builder.registry_manager import (
    save_dynamic_tool,
    register_dynamic_tool,
    list_dynamic_tools,
    delete_dynamic_tool,
    load_and_register_all_dynamic_tools,
)


def _type_from_str(type_name: str) -> type:
    mapping = {
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list": list,
        "dict": dict,
    }
    return mapping.get(type_name.lower(), str)


def build_tool(requirement: str, state, lang: str = "zh", confirm: bool = True) -> Result:
    """
    根据需求动态构建工具的主流程，返回 Result。

    Args:
        requirement: 用户需求描述
        state: AppState
        lang: 界面语言
        confirm: 安装依赖/保存前是否询问用户
    """
    if not state.model_name:
        return Result.fail("模型未配置，无法动态构建")

    print(f"{CYAN}🛠️ 正在分析需求: {requirement}{RESET}")

    # 1. 规划
    plan = plan_build(requirement, state, lang)
    if "error" in plan:
        return False, f"规划失败: {plan['error']}"

    need_build = plan.get("need_build", False)
    reasoning = plan.get("reasoning", "")

    if reasoning:
        print(f"{DIM}💡 {reasoning}{RESET}")

    if not need_build:
        suggestion = plan.get("suggestion") or "该需求可由现有能力覆盖，请直接使用相关命令或工具。"
        print(f"{GREEN}✅ {suggestion}{RESET}")
        return Result.ok(suggestion)

    tool_name = plan.get("tool_name", "")
    if not tool_name:
        return Result.fail("规划结果缺少工具名")

    # 验证工具名
    import re
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', tool_name):
        return Result.fail(f"非法工具名: {tool_name}")

    print(f"{CYAN}📋 构建计划:{RESET}")
    print(f"  工具名: {DIM}{tool_name}{RESET}")
    print(f"  描述:   {DIM}{plan.get('description', '')}{RESET}")
    deps = plan.get("dependencies", []) or []
    if deps:
        print(f"  依赖:   {DIM}{', '.join(deps)}{RESET}")

    # 2. 用户确认
    if confirm:
        try:
            ans = input(f"\n{YELLOW}👉 是否继续构建 [{tool_name}]? [Y/n]: {RESET}").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return Result.fail("用户取消构建")
        if ans and ans not in ("y", "yes"):
            return Result.fail("用户取消构建")

    # 3. 安装依赖
    if deps:
        dep_result = ensure_dependencies(deps, lang=lang, confirm=confirm)
        if dep_result.is_fail():
            return Result.fail(dep_result.error)

    # 4. 生成代码
    print(f"{CYAN}🤖 正在生成工具代码...{RESET}")
    code = generate_tool_code(requirement, state, lang)
    if not code or "def run(" not in code:
        return Result.fail("代码生成失败或缺少 run(deps, **kwargs) 入口")

    # 如果 LLM 生成的函数名与 tool_name 不一致，重命名
    generated_name = extract_tool_name(code)
    if generated_name != "run":
        code = code.replace(f"def {generated_name}(", "def run(")

    # 5. 保存并注册
    params = {k: _type_from_str(v) for k, v in plan.get("params", {}).items()}
    aliases = plan.get("aliases", [])
    triggers = plan.get("triggers", [])

    save_result = save_dynamic_tool(
        name=tool_name,
        code=code,
        description=plan.get("description", ""),
        params=params,
        aliases=aliases,
        triggers=triggers,
    )
    if save_result.is_fail():
        return Result.fail(f"保存工具失败: {save_result.error}")

    meta = {
        "description": plan.get("description", ""),
        "params": {k: v.__name__ for k, v in params.items()},
        "aliases": aliases,
        "triggers": triggers,
    }
    reg_result = register_dynamic_tool(tool_name, code, meta)
    if reg_result.is_fail():
        return Result.fail(f"注册工具失败: {reg_result.error}")

    # 6. 更新 state.plugins 或 weapon_tools（注册表已更新，这里可选刷新）
    # 重新加载 weapon_tools 可能不必要，因为注册表已是单一真相源

    print(f"{GREEN}✅ 工具 [{tool_name}] 构建完成！{RESET}")
    usage = f"【调用：{tool_name}({plan.get('params', {})})】"
    if aliases:
        usage += f" 或 {aliases[0]}"
    print(f"{DIM}用法: {usage}{RESET}")

    return Result.ok(f"工具 [{tool_name}] 构建完成")


def list_built_tools() -> list:
    """列出已构建的动态工具"""
    return list_dynamic_tools()


def remove_built_tool(name: str) -> Result:
    """删除已构建的动态工具，返回 Result"""
    return delete_dynamic_tool(name)


def bootstrap_dynamic_tools() -> Tuple[int, list]:
    """启动时加载所有持久化的动态工具"""
    return load_and_register_all_dynamic_tools()
