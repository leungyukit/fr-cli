"""
法宝图谱加载器
从统一注册表获取工具信息，替代 WEAPON.MD 的文本解析。
保留 WEAPON.MD 作为人类可读文档，程序逻辑不再依赖其解析。
"""
from fr_cli.command.registry import get_registry


# 旧类别到注册表工具名的映射（用于兼容旧接口）
_LEGACY_CATEGORIES = {
    "file_operations": (["write_file", "read_file", "list_files", "change_dir", "append_file", "delete_file"], "fr_cli/weapon/fs.py"),
    "image_analysis": (["analyze_image", "generate_image"], "fr_cli/weapon/vision.py"),
    "email_management": (["mail_inbox", "mail_read", "mail_send"], "fr_cli/weapon/mail.py"),
    "web_search": (["search_web", "fetch_web"], "fr_cli/weapon/web.py"),
    "scheduled_tasks": (["cron_add", "cron_list", "cron_del"], "fr_cli/weapon/cron.py"),
    "cloud_storage": (["disk_ls", "disk_up", "disk_down"], "fr_cli/weapon/disk.py"),
    "session_management": (["save_session", "list_sessions", "export_session"], "fr_cli/memory/history.py"),
    "configuration": (["set_model", "set_key", "set_limit", "set_lang"], "fr_cli/conf/config.py"),
    "launcher_system": (["open_file", "launch_app", "list_apps"], "fr_cli/weapon/launcher.py"),
    "agent_system": (["agent_create", "agent_run"], "fr_cli/agent/"),
    "data_scroll": (["read_excel", "read_csv"], "fr_cli/weapon/dataframe.py"),
}


def load_weapon_md(mcp_tools=None):
    """
    从统一注册表获取法宝图谱。
    保持返回格式兼容旧接口：(tools:list, trigger_map:dict)
    :param mcp_tools: MCP 外部神通列表，可选
    """
    reg = get_registry()
    reg_tools = {t["name"]: t for t in reg.get_available_tools(plugins={})}

    tools = []
    trigger_map = {}

    for cat_name, (tool_names, path) in _LEGACY_CATEGORIES.items():
        commands = []
        triggers = []
        descriptions = []
        for tn in tool_names:
            if tn in reg_tools:
                commands.append(tn)
                info = reg_tools[tn]
                if info.get("description"):
                    descriptions.append(info["description"])
                if info.get("triggers"):
                    triggers.extend(info["triggers"])
        if commands:
            tools.append({
                "name": cat_name,
                "description": ", ".join(descriptions) if descriptions else cat_name,
                "commands": commands,
                "path": path,
            })
            # 去重 triggers
            seen = set()
            unique_triggers = []
            for t in triggers:
                if t not in seen:
                    seen.add(t)
                    unique_triggers.append(t)
            trigger_map[cat_name] = unique_triggers

    # 注入 MCP 外部神通
    if mcp_tools:
        mcp_commands = [t["name"] for t in mcp_tools]
        tools.append({
            "name": "mcp_tools",
            "description": "MCP 外部神通: " + ", ".join([t["name"] for t in mcp_tools]),
            "commands": mcp_commands,
            "path": "fr_cli/weapon/mcp.py",
        })
        trigger_map["mcp_tools"] = ["mcp", "外部工具"]

    return tools, trigger_map


def get_available_tools(weapon_tools, plugins):
    """
    获取当前可用的工具列表（从传入的 weapon_tools 追加插件）
    保持与旧接口完全兼容。
    """
    tools = [t.copy() for t in weapon_tools]
    if plugins:
        for plugin_name in plugins.keys():
            tools.append({
                "name": f"plugin_{plugin_name}",
                "description": f"自定义插件: {plugin_name}",
                "commands": [f"/{plugin_name}"],
            })
    return tools


# should_inject_tools 已移除：
# 主程序逻辑中从未调用此函数（main.py 使用 _should_force_tool + _classify_intent 做意图判定）。
# MasterAgent 模式下直接注入全部工具列表，无需触发词匹配。
# 保留 load_weapon_md 和 get_available_tools 作为兼容层。
