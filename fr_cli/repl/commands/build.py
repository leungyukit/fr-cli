"""
动态构建命令
/build —— 根据需求自主安装依赖并构建新工具
"""
from fr_cli.ui.ui import CYAN, GREEN, RED, RESET, DIM
from fr_cli.dynamic_builder import build_tool, list_built_tools, remove_built_tool


def _cmd_build(state, parts):
    """
    动态构建工具

    用法:
      /build <需求描述>          — 根据需求构建新工具
      /build list                — 列出已构建的动态工具
      /build del <工具名>        — 删除指定动态工具
      /build help                — 查看帮助
    """
    sub = parts[1] if len(parts) > 1 else ""

    if sub == "help":
        print(_cmd_build.__doc__)
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
