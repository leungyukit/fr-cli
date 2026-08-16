"""
REPL 命令路由处理器
从 main.py 提取的所有 / 命令实现，减轻主模块负担。
"""

from fr_cli.lang.i18n import T
from fr_cli.ui.ui import (
    CYAN, GREEN, YELLOW, DIM, RESET
)

# 最近新加的命令(显示在默认 /help 顶部 / /help new)
# 格式: (命令, 简短说明, 类别)
# 类别用 emoji + 标签: 🆕新功能 | ⭐推荐 | 🧪实验
_NEW_COMMANDS = [
    ("/insight", "选品洞察提炼(从历史数据提炼爆款规律)", "🆕新功能"),
    ("/insight extract", "立即跑一次选品洞察提炼", "🆕新功能"),
    ("/insight show / history / sources", "查看 / 历史 / 数据源", "🆕新功能"),
    ("/competitor_gaps", "竞品监控能力缺口扫描(dynamic_builder 主动扫领域)", "🆕新功能"),
    ("/competitor_gaps scan / show / add", "扫 / 看 / 推 review", "🆕新功能"),
    ("/dream", "梦境整理(空闲时自动整理长期记忆)", "🆕新功能"),
    ("/mcp_*", "MCP 外部神通(连接外部工具)", "🆕新功能"),
]


def _print_new_commands(state, lang):
    """打印'新功能 / 推荐'区,带 emoji 标记"""
    is_zh = (lang == "zh")
    title = "🆕 最近新功能 / 试用推荐" if is_zh else "🆕 Recent features / try these"
    print()
    print(f"{CYAN}{title}{RESET}")
    for cmd, desc, badge in _NEW_COMMANDS:
        if is_zh:
            line = f"  {GREEN}{cmd:<28}{RESET}  {DIM}{desc}{RESET}  {YELLOW}{badge}{RESET}"
        else:
            line = f"  {GREEN}{cmd:<28}{RESET}  {DIM}{desc}{RESET}  {YELLOW}{badge}{RESET}"
        print(line)
    if is_zh:
        print(f"  {DIM}提示: 输 /help new 只看新功能;输 /help <命令> 看具体命令的用法{RESET}")
    else:
        print(f"  {DIM}Tip: /help new to see only new commands; /help <cmd> for details{RESET}")
    print()


# 单个命令的简短说明(用于 /help <command>)
_COMMAND_BRIEF = {
    "/insight": "选品洞察提炼 — 跑 /insight extract 从数据源提炼爆款规律,自动注入 MasterAgent prompt",
    "/insight_extract": "立即提炼(等价于 /insight extract)",
    "/insight show": "查看最新洞察",
    "/insight history": "查看历史快照",
    "/insight sources": "列出可用数据源",
    "/competitor_gaps": "竞品监控能力缺口扫描 — 主动发现 dynamic_builder 能力缺口",
    "/competitor_gaps scan": "立即跑扫描",
    "/competitor_gaps show": "看最近报告",
    "/competitor_gaps add": "把指定缺口推到 /hermes review 队列",
    "/competitor_gaps model": "看能力模型",
    "/dream": "立即跑一次梦境整理",
    "/master": "MasterAgent 主控开关",
    "/model": "切换/配置模型",
    "/key": "设置 API Key",
    "/providers": "管理模型提供商",
    "/mcp_list": "列出 MCP 服务器",
    "/mcp_call": "调用 MCP 工具",
}


def _print_command_detail(state, command, lang):
    """输出单个命令的详细帮助

    优先用 _COMMAND_BRIEF 静态说明;fallback 用 handler docstring 截取。
    """
    is_zh = (lang == "zh")
    brief = _COMMAND_BRIEF.get(command)
    if brief:
        print()
        print(f"{CYAN}{command}{RESET}")
        print(f"  {DIM}{brief}{RESET}")
        print()
        # 加一句用法提示
        if is_zh:
            print(f"  {DIM}直接输 {command} 看实际运行结果,或加子命令(用 /help 列出){RESET}")
        else:
            print(f"  {DIM}Type {command} to try, or add sub-args (see /help for full list){RESET}")
        return

    # fallback:从 handler docstring 拿
    try:
        from fr_cli.repl.router import COMMAND_ROUTES
        handler = COMMAND_ROUTES.get(command)
        if handler and handler.__doc__:
            print()
            print(f"{CYAN}{command}{RESET}")
            print(f"  {DIM}{handler.__doc__.strip()}{RESET}")
            return
    except Exception:
        pass

    # 兜底
    if is_zh:
        print(f"{CYAN}{command}{RESET}  {DIM}— 暂无详细说明,直接输入试试看{RESET}")
    else:
        print(f"{CYAN}{command}{RESET}  {DIM}— no details, just try it{RESET}")



def _provider_has_key(state, provider_id):
    """检查指定提供商是否已配置 API Key（zhipu 向后兼容顶层 key）"""
    providers_cfg = state.cfg.get("providers", {})
    pcfg = providers_cfg.get(provider_id, {})
    has_key = bool(pcfg.get("key"))
    if not has_key and provider_id == "zhipu":
        has_key = bool(state.cfg.get("key", ""))
    return has_key



def _print_help(state, topic):
    """打印帮助指南（现代 CLI 风格：分组 + 固定宽度对齐）

    支持的 topic:
      - /help              默认帮助(顶部显示新功能,下面是分类命令)
      - /help new          只看新功能列表
      - /help all          完整所有分类详情
      - /help <category>   单个分类(config / fs / agent / ...)
      - /help <command>    精确查单个命令(/insight, /competitor_gaps 等)
    """
    topic_map = {
        "config": "config", "model": "config",
        "fs": "fs", "file": "fs", "files": "fs",
        "session": "session", "sess": "session",
        "plugin": "plugin", "plugins": "plugin", "skill": "plugin", "skills": "plugin",
        "mail": "mail", "email": "mail",
        "m365": "m365", "microsoft365": "m365", "office365": "m365",
        "cron": "cron", "timer": "cron", "schedule": "cron",
        "web": "web", "search": "web",
        "disk": "disk", "cloud": "disk",
        "vision": "vision", "image": "vision", "see": "vision", "img": "vision",
        "shell": "shell", "matrix": "shell", "cmd": "shell",
        "tools": "tools", "tool": "tools", "invoke": "tools",
        "security": "security", "safe": "security", "sec": "security",
        "app": "app", "launcher": "app", "launch": "app", "open": "app",
        "agent": "agent", "agents": "agent",
        "builtin": "builtin", "builtins": "builtin",
        "dataframe": "dataframe", "data": "dataframe",
        "gatekeeper": "gatekeeper",
        "hermes": "hermes",
        "build": "build", "dynamic": "build",
        "context": "context", "compress": "context",
        "status": "status",
        "stock": "stock",
        "all": "all",
        "new": "_new",  # 特殊:列出新功能
    }
    mapped = topic_map.get(topic, "")
    lang = state.lang

    # ---------- /help new: 只看新功能 ----------
    if mapped == "_new":
        _print_new_commands(state, lang)
        return

    # ---------- /help <command>: 精确查单个命令 ----------
    if topic.startswith("/") and topic not in topic_map and topic != "all":
        from fr_cli.repl.router import COMMAND_ROUTES
        if topic in COMMAND_ROUTES:
            _print_command_detail(state, topic, lang)
            return
        # 也不是已知命令,fallthrough 到默认

    # ---------- 主题详细帮助（保持原有逻辑）----------
    if mapped:
        if mapped == "all":
            for t in ["config", "fs", "session", "plugin", "mail", "m365", "cron", "web", "disk", "vision", "shell", "tools", "security", "app", "agent", "builtin", "dataframe", "gatekeeper", "mcp", "hermes", "build", "context", "status", "stock"]:
                print(T(f"help_detail_{t}", lang))
                print()
        else:
            detail = T(f"help_detail_{mapped}", lang)
            if detail:
                print(detail)
            else:
                print(T("help_not_found", lang, topic))
        return

    # ---------- 默认帮助（现代简洁风格）----------
    is_zh = lang == "zh"

    # 标题 + 当前状态
    _h = lambda s: f"{CYAN}{s}{RESET}"
    _cmd = lambda s: f"{GREEN}{s}{RESET}"
    _dim = lambda s: f"{DIM}{s}{RESET}"

    from fr_cli import __version__
    title = f"fr-cli {__version__} — 凡人打字机" if is_zh else f"fr-cli {__version__}"
    cur = f"当前: {state.provider}/{state.display_model}" if is_zh else f"Current: {state.provider}/{state.display_model}"

    print()
    print(f"{_h(title)}")
    print(f"{_dim(cur)}")
    print()

    # 顶部:🆕 新功能(让用户先看到最近加的)
    _print_new_commands(state, lang)

    # 快速用法
    usage_label = "用法" if is_zh else "Usage"
    print(f"{_h(usage_label)}")
    u_msg = "<message>    与 AI 对话" if is_zh else "<message>    Chat with AI"
    u_sh = "!<cmd>       执行 Shell 命令" if is_zh else "!<cmd>       Run shell command"
    u_ag = "@<agent>     调用内置 Agent" if is_zh else "@<agent>     Invoke built-in agent"
    print(f"  {_cmd('<msg>')}      {_dim(u_msg.split('  ')[-1])}")
    print(f"  {_cmd('!<cmd>')}     {_dim(u_sh.split('  ')[-1])}")
    print(f"  {_cmd('@<agent>')}   {_dim(u_ag.split('  ')[-1])}")
    print()

    # 表格辅助函数（处理 ANSI 颜色码宽度）
    import re
    def _plain_len(s):
        return len(re.sub(r'\033\[[0-9;]*m', '', s))

    def _pad(s, width):
        return s + " " * max(width - _plain_len(s), 0)

    # 命令分组（cmd, desc, example）
    groups = []
    if is_zh:
        groups = [
            ("模型", [
                ("/model", "切换模型", "/model 3  或  /model deepseek:deepseek-chat"),
                ("/model config", "交互式配置向导", "/model config"),
                ("/model list", "列出模型", "/model list"),
                ("/model current", "显示当前", "/model current"),
                ("/model default", "恢复默认", "/model default"),
                ("/providers", "管理提供商", "/providers"),
                ("/key", "设置 Key", "/key sk-xxx"),
            ]),
            ("文件", [
                ("/dir", "列出文件", "/dir"),
                ("/open <file>", "读取文件", "/open README.md"),
                ("/dirs", "挂载目录", "/dirs"),
                ("/rmdir <idx>", "移除挂载", "/rmdir 1"),
                ("/write <file>", "写入文件", '/write a.md "内容"'),
                ("/append <file>", "追加内容", '/append a.md "追加"'),
                ("/delete <file>", "删除文件", "/delete tmp.txt"),
            ]),
            ("会话", [
                ("/new", "新开会话", "/new"),
                ("/save <name>", "保存会话", "/save proj_v1"),
                ("/load <name>", "加载会话", "/load proj_v1"),
                ("/session_list", "列出存档", "/session_list"),
                ("/session_load <n>", "加载存档", "/session_load 2"),
                ("/export", "导出 Markdown", "/export"),
            ]),
            ("Agent", [
                ("/agent_create <n> <desc>", "创建 Agent", "/agent_create coder 编写Python"),
                ("/agent_list", "列出 Agent", "/agent_list"),
                ("/agent_show <name>", "查看 Agent", "/agent_show coder"),
                ("/agent_edit <name> <type>", "编辑设定", "/agent_edit coder persona"),
                ("/agent_run <name>", "运行 Agent", "/agent_run coder"),
                ("/agent_forge <name>", "代码铸造", "/agent_forge coder"),
                ("/agent_model <name> [cfg]", "专属模型", "/agent_model coder deepseek:deepseek-chat"),
                ("/master on|off|status", "主控开关", "/master on"),
                ("@local <cmd>", "本地操作", "@local 查看磁盘"),
                ("@remote <srv>", "远程 SSH", "@remote myserver df -h"),
                ("@spider <URL>", "网页爬虫", "@spider https://example.com"),
                ("@db [alias] <q>", "数据库助手", "@db mydb 查询用户"),
                ("@RAG <q>", "知识库问答", "@RAG 部署流程是什么"),
                ("@stock <q>", "股票量化", "@stock 查询茅台股价"),
            ]),
            ("邮件", [
                ("/mail setup", "邮件配置", "/mail setup"),
                ("/mail inbox", "查看收件箱", "/mail inbox"),
                ("/mail read <id>", "读取邮件", "/mail read 1"),
                ("/mail send", "发送邮件", '/mail send a@b.com "主题" "正文"'),
                ("/m365_config", "M365 配置", "/m365_config setup"),
                ("/m365_inbox", "M365 收件箱", "/m365_inbox"),
                ("/m365_read <id>", "M365 读邮件", "/m365_read <message_id>"),
                ("/m365_send", "M365 发邮件", '/m365_send a@b.com "主题" "正文"'),
            ]),
            ("工具", [
                ("/web <query>", "网页搜索", "/web Python 异步"),
                ("/see <img>", "图片分析", "/see photo.jpg"),
                ("/rag_dir <dir>", "设置知识库", "/rag_dir ./docs"),
                ("/rag_sync", "同步知识库", "/rag_sync"),
                ("/rag_watch start", "监控知识库", "/rag_watch start"),
                ("/mcp_list", "列出 MCP", "/mcp_list"),
                ("/read_excel <f>", "读取 Excel", "/read_excel data.xlsx"),
                ("/read_csv <f>", "读取 CSV", "/read_csv data.csv"),
                ("/build <需求>", "动态构建", "/build 生成二维码工具"),
                ("/ocr_config", "OCR 配置", "/ocr_config setup"),
            ]),
            ("系统", [
                ("/shell", "Shell 模式", "/shell"),
                ("/mode direct|cot|tot|react|plan", "思维模式", "/mode cot"),
                ("/hermes status", "Hermes 任务", "/hermes status"),
                ("/context [sub]", "上下文压缩", "/context status"),
                ("/status [json|errors]", "系统状态", "/status errors"),
                ("/usage [days]", "用量统计", "/usage 7"),
                ("/cron_add <s> <cmd>", "定时任务", "/cron_add 300 df -h"),
                ("/gatekeeper status", "守护进程", "/gatekeeper status"),
                ("/autostart", "开机自启", "/autostart"),
                ("/queue", "查看队列", "/queue"),
                ("/tutorial", "交互教程", "/tutorial"),
                ("/help <topic>", "主题帮助", "/help agent"),
                ("/exit", "退出程序", "/exit"),
            ]),
        ]
    else:
        groups = [
            ("Model", [
                ("/model", "Switch model", "/model 3  or  /model deepseek:deepseek-chat"),
                ("/model config", "Interactive config wizard", "/model config"),
                ("/model list", "List models", "/model list"),
                ("/model current", "Show current", "/model current"),
                ("/model default", "Reset default", "/model default"),
                ("/providers", "Manage providers", "/providers"),
                ("/key", "Set API Key", "/key sk-xxx"),
            ]),
            ("File", [
                ("/dir", "List files", "/dir"),
                ("/open <file>", "Read file", "/open README.md"),
                ("/dirs", "Mounted dirs", "/dirs"),
                ("/rmdir <idx>", "Remove mount", "/rmdir 1"),
                ("/write <file>", "Write file", '/write a.md "content"'),
                ("/append <file>", "Append", '/append a.md "more"'),
                ("/delete <file>", "Delete file", "/delete tmp.txt"),
            ]),
            ("Session", [
                ("/new", "New session", "/new"),
                ("/save <name>", "Save session", "/save proj_v1"),
                ("/load <name>", "Load session", "/load proj_v1"),
                ("/session_list", "List archives", "/session_list"),
                ("/session_load <n>", "Load archive", "/session_load 2"),
                ("/export", "Export Markdown", "/export"),
            ]),
            ("Agent", [
                ("/agent_create <n> <desc>", "Create agent", "/agent_create coder write Python"),
                ("/agent_list", "List agents", "/agent_list"),
                ("/agent_show <name>", "Show agent", "/agent_show coder"),
                ("/agent_edit <name> <type>", "Edit agent", "/agent_edit coder persona"),
                ("/agent_run <name>", "Run agent", "/agent_run coder"),
                ("/agent_forge <name>", "Forge agent", "/agent_forge coder"),
                ("/agent_model <name> [cfg]", "Bind model", "/agent_model coder deepseek:deepseek-chat"),
                ("/master on|off|status", "Master toggle", "/master on"),
                ("@local <cmd>", "Local ops", "@local show disks"),
                ("@remote <srv>", "Remote SSH", "@remote myserver df -h"),
                ("@spider <URL>", "Web crawler", "@spider https://example.com"),
                ("@db [alias] <q>", "DB assistant", "@db mydb query users"),
                ("@RAG <q>", "Knowledge Q&A", "@RAG deployment process"),
                ("@stock <q>", "Stock quant", "@stock quote 600519"),
            ]),
            ("Mail", [
                ("/mail setup", "Mail setup", "/mail setup"),
                ("/mail inbox", "Inbox", "/mail inbox"),
                ("/mail read <id>", "Read mail", "/mail read 1"),
                ("/mail send", "Send mail", '/mail send a@b.com "Subject" "Body"'),
                ("/m365_config", "M365 config", "/m365_config setup"),
                ("/m365_inbox", "M365 inbox", "/m365_inbox"),
                ("/m365_read <id>", "M365 read", "/m365_read <message_id>"),
                ("/m365_send", "M365 send", '/m365_send a@b.com "Subject" "Body"'),
            ]),
            ("Tools", [
                ("/web <query>", "Web search", "/web Python async"),
                ("/see <img>", "Image analysis", "/see photo.jpg"),
                ("/rag_dir <dir>", "Set RAG dir", "/rag_dir ./docs"),
                ("/rag_sync", "Sync RAG", "/rag_sync"),
                ("/rag_watch start", "Watch RAG", "/rag_watch start"),
                ("/mcp_list", "List MCP", "/mcp_list"),
                ("/read_excel <f>", "Read Excel", "/read_excel data.xlsx"),
                ("/read_csv <f>", "Read CSV", "/read_csv data.csv"),
                ("/build <req>", "Dynamic build", "/build generate qr tool"),
                ("/ocr_config", "OCR config", "/ocr_config setup"),
            ]),
            ("System", [
                ("/shell", "Shell mode", "/shell"),
                ("/mode direct|cot|tot|react|plan", "Thinking mode", "/mode cot"),
                ("/hermes status", "Hermes tasks", "/hermes status"),
                ("/context [sub]", "Context compress", "/context status"),
                ("/status [json|errors]", "System status", "/status errors"),
                ("/usage [days]", "Usage stats", "/usage 7"),
                ("/cron_add <s> <cmd>", "Cron task", "/cron_add 300 df -h"),
                ("/gatekeeper status", "Daemon", "/gatekeeper status"),
                ("/autostart", "Auto start", "/autostart"),
                ("/queue", "View queue", "/queue"),
                ("/tutorial", "Tutorial", "/tutorial"),
                ("/help <topic>", "Topic help", "/help agent"),
                ("/exit", "Exit", "/exit"),
            ]),
        ]

    CMD_W, DESC_W = 20, 16
    sep = f"  {_dim('─' * CMD_W + '┬' + '─' * DESC_W + '┬' + '─' * 30)}"

    for group_name, rows in groups:
        print(f"{_h(group_name)}")
        print(sep)
        for cmd, desc, example in rows:
            c = _pad(_cmd(cmd), CMD_W)
            d = _pad(_dim(desc), DESC_W)
            e = _dim(example)
            print(f"  {c} {d} {e}")
        print()

    # 快捷键
    shortcut_label = "快捷键" if is_zh else "Shortcuts"
    print(f"{_h(shortcut_label)}")
    if is_zh:
        print(f"  {_dim('Ctrl+C')}  清空输入   {_dim('Ctrl+L')}  清屏   {_dim('Ctrl+D')}  退出")
        print(f"  {_dim('e')}        编辑上条   {_dim('r')}        重试   {_dim('u')}        撤销")
    else:
        print(f"  {_dim('Ctrl+C')}  Clear   {_dim('Ctrl+L')}  Clear screen   {_dim('Ctrl+D')}  Exit")
        print(f"  {_dim('e')}        Edit    {_dim('r')}            Retry          {_dim('u')}        Undo")
    print()

    # 底部提示
    if is_zh:
        print(f"{_dim('详情: /help <主题>  主题: config, fs, session, plugin, mail, m365, cron, web, disk, vision, shell, tools, security, app, agent, builtin, dataframe, gatekeeper, mcp, hermes, build, context, status, stock, all')}")
    else:
        print(f"{_dim('Details: /help <topic>  Topics: config, fs, session, plugin, mail, m365, cron, web, disk, vision, shell, tools, security, app, agent, builtin, dataframe, gatekeeper, mcp, hermes, build, context, status, stock, all')}")
    print()


