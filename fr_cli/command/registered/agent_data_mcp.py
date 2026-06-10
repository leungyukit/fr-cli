"""
注册表分组：Agent 分身 / 数据卷轴 / MCP / 快速工具
- agent_create / agent_run / agent_call
- read_excel / read_csv
- mcp_list / mcp_call
- voice / screenshot / drag / ide / init_project / pref / recent / cache / local_llm
"""
import json
from fr_cli.command.registry import register
from fr_cli.ui.ui import GREEN, RED, RESET


# ============== Agent 分身 ==============

def _make_compat_state(deps):
    """将 SimpleNamespace deps 包装为兼容 AppState 的对象，供 Agent executor 使用"""
    class _CompatState:
        def __init__(self, d):
            for k, v in d.__dict__.items():
                setattr(self, k, v)
    compat = _CompatState(deps)
    compat.executor = getattr(deps, 'executor', None)
    return compat


@register(
    name="agent_create",
    triggers=["创建Agent", "新建Agent", "生成Agent", "create agent", "new agent"],
    description="根据需求自动生成 Agent 分身",
    params={"name": str, "description": str},
    aliases=["/agent_create"],
)
def _agent_create(deps, **kwargs):
    from fr_cli.agent.generator import generate_agent
    from fr_cli.agent.manager import save_persona, save_skills, save_agent_code, create_agent_dir
    name = kwargs["name"]
    desc = kwargs["description"]
    d = create_agent_dir(name)
    result = generate_agent(deps.client, deps.model_name, name, desc, deps.lang)
    if result["persona"]:
        save_persona(name, result["persona"])
    if result["skills"]:
        save_skills(name, result["skills"])
    if result["code"]:
        save_agent_code(name, result["code"])
    return f"Agent [{name}] 创建完成！路径: {d}", None


@register(
    name="agent_run",
    triggers=["运行Agent", "调用Agent", "执行Agent", "run agent"],
    description="运行指定本地 Agent",
    params={"name": str},
    security="sec_exec",
    aliases=["/agent_run"],
)
def _agent_run(deps, **kwargs):
    from fr_cli.agent.executor import run_agent
    result, err = run_agent(kwargs["name"], _make_compat_state(deps))
    return (result, None) if not err else (None, err)


@register(
    name="agent_call",
    triggers=["调用Agent", "协作Agent", "agent_call", "召唤Agent"],
    description="调用Agent（本地或远程）并传入任务描述，实现MasterAgent与其他Agent协作",
    params={"name": str, "user_input": str},
    security="sec_exec",
    aliases=["/agent_call"],
)
def _agent_call(deps, **kwargs):
    """MasterAgent 调用其他 Agent（支持本地和远程）"""
    from fr_cli.agent.client import call_agent
    result, err = call_agent(kwargs["name"], _make_compat_state(deps), user_input=kwargs.get("user_input", ""))
    return (result, None) if not err else (None, err)


# ============== 数据卷轴 ==============

@register(
    name="read_excel",
    triggers=["Excel", "表格", "xlsx", "读取Excel", "分析表格"],
    description="读取 Excel 文件并返回数据摘要",
    params={"path": str},
    security="sec_read",
    aliases=["/read_excel"],
)
def _read_excel(deps, **kwargs):
    from fr_cli.weapon.dataframe import read_excel
    res, err = read_excel(kwargs["path"], lang=deps.lang)
    return (res, None) if not err else (None, err)


@register(
    name="read_csv",
    triggers=["CSV", "csv", "读取CSV", "分析CSV"],
    description="读取 CSV 文件并返回数据摘要",
    params={"path": str},
    security="sec_read",
    aliases=["/read_csv"],
)
def _read_csv(deps, **kwargs):
    from fr_cli.weapon.dataframe import read_csv
    res, err = read_csv(kwargs["path"], lang=deps.lang)
    return (res, None) if not err else (None, err)


# ============== MCP ==============

@register(
    name="mcp_list",
    description="列出已配置的 MCP 服务器及其可用工具",
    params={},
    aliases=["/mcp_list"],
)
def _mcp_list(deps, **kwargs):
    mcp = getattr(deps, "mcp", None)
    if not mcp:
        return None, "MCP 管理器未初始化"
    servers = mcp.list_servers()
    if not servers:
        return "暂无 MCP 服务器配置。", None
    lines = ["📡 MCP 服务器列表:"]
    for s in servers:
        status = f"{GREEN}● 启用{RESET}" if s.get("enabled", True) else f"{RED}● 禁用{RESET}"
        lines.append(f"  [{s['name']}] {status} | 传输: {s.get('transport', 'stdio')} | 命令: {s.get('command', 'N/A')}")
    return "\n".join(lines), None


@register(
    name="mcp_call",
    description="调用指定 MCP 服务器的工具",
    params={"server": str, "tool": str, "arguments": dict},
    aliases=["/mcp_call"],
)
def _mcp_call(deps, **kwargs):
    mcp = getattr(deps, "mcp", None)
    if not mcp:
        return None, "MCP 管理器未初始化"
    server = kwargs.get("server", "")
    tool = kwargs.get("tool", "")
    arguments = kwargs.get("arguments", {})
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except Exception:
            arguments = {}
    result, err = mcp.call_tool_sync(server, tool, arguments)
    return (result, None) if not err else (None, err)


# ============== P3 快速工具 ==============

@register(
    name="voice",
    description="语音输入（macOS Dictation / Win+H / Linux arecord+vosk）",
    params={},
    aliases=["/voice"],
)
def _voice(deps, **kwargs):
    from fr_cli.repl.quick_actions import cmd_voice
    return cmd_voice(deps, []), None


@register(
    name="screenshot",
    description="截屏（macOS），自动保存到 ~/.fr_cli/screenshots/，可 /see 分析",
    params={"region": str},
    aliases=["/screenshot", "/shot"],
)
def _screenshot(deps, **kwargs):
    from fr_cli.repl.quick_actions import cmd_screenshot
    region = kwargs.get("region", "")
    return cmd_screenshot(deps, ["/screenshot", region] if region else ["/screenshot"]), None


@register(
    name="drag",
    description="显示拖文件到 TUI 的使用提示",
    params={},
    aliases=["/drag"],
)
def _drag(deps, **kwargs):
    from fr_cli.repl.quick_actions import cmd_drag_hint
    return cmd_drag_hint(deps, []), None


@register(
    name="ide",
    description="写编辑器集成模板（vscode/zed）",
    params={"ide": str},
    aliases=["/ide"],
)
def _ide(deps, **kwargs):
    from fr_cli.repl.quick_actions import cmd_ide_template
    ide = kwargs.get("ide", "vscode")
    return cmd_ide_template(deps, ["/ide", ide]), None


@register(
    name="init_project",
    description="在当前目录创建 .fr-cli/ 项目配置（persona + agents + config）",
    params={},
    aliases=["/init_project"],
)
def _init_project(deps, **kwargs):
    from fr_cli.core.project import init_project
    msg = init_project()
    return msg, None


@register(
    name="pref",
    description="查看个人偏好（最常用命令 / 模型 / 目录）",
    params={},
    aliases=["/pref", "/preferences"],
)
def _pref(deps, **kwargs):
    from fr_cli.core.preferences import get_top_commands, _load_pref
    p = _load_pref()
    lines = ["📊 个人偏好统计："]
    if p.get("provider") or p.get("model"):
        lines.append(f"  默认提供商/模型: {p.get('provider', '?')}/{p.get('model', '?')}")
    top = get_top_commands(10)
    if top:
        lines.append("  最常用命令:")
        for cmd, count in top:
            lines.append(f"    /{cmd}: {count} 次")
    else:
        lines.append("  还没有记录（命令会被自动统计）")
    return "\n".join(lines), None


@register(
    name="recent",
    description="显示最近 5 个自动会话（用于快速切换）",
    params={},
    aliases=["/recent"],
)
def _recent(deps, **kwargs):
    from fr_cli.memory.session import list_sessions
    sessions = list_sessions()
    if not sessions:
        return "📂 暂无自动会话存档", None
    lines = ["📚 最近会话（按日期倒序）："]
    for s in sessions[:5]:
        lines.append(f"  📁 {s.get('path', '?').split('/')[-1]}  ({s.get('size_kb', 0):.1f} KB)")
    lines.append(f"\n  切换: /session_load <N>")
    return "\n".join(lines), None


@register(
    name="cache",
    description="查看/清空 LLM 响应缓存",
    params={},
    aliases=["/cache"],
)
def _cache(deps, **kwargs):
    from fr_cli.core.cache import cache_stats, cache_clear
    s = cache_stats()
    if "clear" in str(kwargs):
        cache_clear()
        return "🗑️  缓存已清空", None
    return (
        f"💾 响应缓存统计：\n"
        f"  条目: {s['entries']} / 100\n"
        f"  命中: {s['hits']}\n"
        f"  未命中: {s['misses']}\n"
        f"  命中率: {s['hit_rate']}\n"
        f"  TTL: 5 分钟"
    ), None


@register(
    name="local_llm",
    description="检测并切换到本地 ollama（无需 API key）",
    params={},
    aliases=["/local_llm", "/ollama"],
)
def _local_llm(deps, **kwargs):
    from fr_cli.core.optimizations import cmd_local_llm
    class _S:
        pass
    s = _S()
    s.cfg = deps.cfg
    s.reinit_client = lambda: None
    return cmd_local_llm(s, []), None