"""
动态构建命令
/build —— 根据需求自主安装依赖并构建新工具
"""
from fr_cli.ui.ui import CYAN, GREEN, RED, RESET, DIM, YELLOW
from fr_cli.dynamic_builder import build_tool, list_built_tools, remove_built_tool
from fr_cli.dynamic_builder.gap_analyzer import CapabilityGapAnalyzer
from fr_cli.command.registry import get_registry


def _cmd_build(state, parts):
    """
    动态构建工具

    用法:
      /build <需求描述>          — 根据需求构建新工具
      /build check <需求描述>    — 仅分析能力缺口，不构建
      /build list                — 列出已构建的动态工具
      /build del <工具名>        — 删除指定动态工具
      /build help                — 查看帮助
    """
    sub = parts[1] if len(parts) > 1 else ""

    if sub == "help":
        print(_cmd_build.__doc__)
        return False

    if sub == "check":
        requirement = " ".join(parts[2:]) if len(parts) > 2 else ""
        if not requirement:
            print(f"{RED}❌ 用法: /build check <需求描述>{RESET}")
            return False
        tools = get_registry().get_available_tools(state.plugins)
        analyzer = CapabilityGapAnalyzer()
        report = analyzer.analyze(requirement, tools, state=state, lang=state.lang)
        if report.get("gap"):
            print(f"{YELLOW}⚠️ 发现能力缺口{RESET}")
            print(f"  {DIM}建议工具名: {report.get('suggested_tool_name') or '-'}{RESET}")
        else:
            print(f"{GREEN}✅ 现有工具已覆盖该需求{RESET}")
        print(f"  {DIM}置信度: {report.get('confidence', 0):.2f}{RESET}")
        print(f"  {DIM}理由: {report.get('reasoning', '')}{RESET}")
        return False

    if sub == "list":
        tools = list_built_tools()
        if not tools:
            print(f"{DIM}暂无动态构建的工具。{RESET}")
            return False
        print(f"{CYAN}🛠️ 已构建的动态工具 ({len(tools)}):{RESET}")
        for t in tools:
            print(f"  • {GREEN}{t['name']}{RESET}: {DIM}{t.get('description', '')}{RESET}")
            aliases = t.get("aliases", [])
            if aliases:
                print(f"    别名: {', '.join(aliases)}")
        return False

    if sub == "del":
        name = parts[2] if len(parts) > 2 else ""
        if not name:
            print(f"{RED}❌ 用法: /build del <工具名>{RESET}")
            return False
        result = remove_built_tool(name)
        if result.is_ok():
            print(f"{GREEN}✅ {result.unwrap()}{RESET}")
        else:
            print(f"{RED}❌ {result.error}{RESET}")
        return False

    # 构建新工具
    requirement = " ".join(parts[1:]) if len(parts) > 1 else ""
    if not requirement:
        print(f"{RED}❌ 用法: /build <需求描述>{RESET}")
        print(f"{DIM}示例: /build 生成一个二维码识别工具{RESET}")
        return False

    result = build_tool(requirement, state, lang=state.lang, confirm=True)
    if result.is_ok():
        print(f"{GREEN}✅ {result.unwrap()}{RESET}")
    else:
        print(f"{RED}❌ {result.error}{RESET}")
    return False
