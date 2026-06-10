"""命令处理器 —— system"""

from fr_cli.command.registry import register

@register(
    name="debug",
    description="切换调试模式：显示完整 traceback、详细日志",
    params={},
    aliases=["/debug"],
)
def _debug(deps, **kwargs):
    from fr_cli.core.errors import is_debug, set_debug
    on = not is_debug()
    set_debug(on)
    state = "开" if on else "关"
    return f"🔧 调试模式：{state}\n   错误日志：~/.fr_cli/logs/errors.log", None


@register(
    name="why",
    description="解释 AI 上一步为什么这么做（基于历史 tool call）",
    params={},
    aliases=["/why"],
)
def _why(deps, **kwargs):
    """从最近一次 AI 回复中提取工具调用并展示"""
    from fr_cli.ui.ui import CYAN, DIM, YELLOW, RESET
    msgs = deps.cfg.get("_last_messages") or []
    # 这里 deps 拿不到 state.messages，所以 /why 是占位实现
    # 用户用 e (edit) 或 r (retry) 可以重新生成
    return (
        f"💡 /why 命令占位\n"
        f"   查看完整 trace：~/.fr_cli/logs/errors.log\n"
        f"   编辑上一条 AI 回答：按 e 键\n"
        f"   重试上一条：按 r 键\n"
        f"   撤销：按 u 键"
    ), None


# ------------------------------------------------------------------
# P3 工具：语音 / 截屏 / 拖文件 / IDE 集成
# ------------------------------------------------------------------


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
    # list_sessions 返回 sorted；取最近 5 个
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
    # 拿 state：通过 _make_compat_state 风格包装
    class _S:
        pass
    s = _S()
    s.cfg = deps.cfg
    s.reinit_client = lambda: None  # 简化：不让它真的改 deps.client
    return cmd_local_llm(s, []), None
def _agent_call(deps, **kwargs):
    """MasterAgent 调用其他 Agent（支持本地和远程）"""
    from fr_cli.agent.client import call_agent
    result, err = call_agent(kwargs["name"], _make_compat_state(deps), user_input=kwargs.get("user_input", ""))
    return (result, None) if not err else (None, err)


# ------------------------------------------------------------------

