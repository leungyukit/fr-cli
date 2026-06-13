"""
REPL 命令路由处理器
从 main.py 提取的所有 / 命令实现，减轻主模块负担。
"""

from fr_cli.lang.i18n import T
from fr_cli.ui.ui import (
    CYAN, GREEN, DIM, RESET
)



def _provider_has_key(state, provider_id):
    """检查指定提供商是否已配置 API Key（zhipu 向后兼容顶层 key）"""
    providers_cfg = state.cfg.get("providers", {})
    pcfg = providers_cfg.get(provider_id, {})
    has_key = bool(pcfg.get("key"))
    if not has_key and provider_id == "zhipu":
        has_key = bool(state.cfg.get("key", ""))
    return has_key



def _print_help(state, topic):
    """打印帮助指南（现代 CLI 风格：分组 + 固定宽度对齐）"""
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
        "all": "all",
    }
    mapped = topic_map.get(topic, "")
    lang = state.lang

    # ---------- 主题详细帮助（保持原有逻辑）----------
    if mapped:
        if mapped == "all":
            for t in ["config", "fs", "session", "plugin", "mail", "m365", "cron", "web", "disk", "vision", "shell", "tools", "security", "app", "agent", "builtin", "dataframe", "gatekeeper", "mcp"]:
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
                ("/ls", "列出文件", "/ls"),
                ("/cat <file>", "读取文件", "/cat README.md"),
                ("/cd <dir>", "切换目录", "/cd src"),
                ("/write <file>", "写入文件", '/write a.md "内容"'),
                ("/append <file>", "追加内容", '/append a.md "追加"'),
                ("/delete <file>", "删除文件", "/delete tmp.txt"),
            ]),
            ("会话", [
                ("/new", "新开会话", "/new"),
                ("/save <name>", "保存会话", "/save proj_v1"),
                ("/load <name>", "加载会话", "/load proj_v1"),
                ("/session list", "列出存档", "/session list"),
                ("/session load <n>", "加载存档", "/session load 2"),
                ("/undo [N]", "撤销对话", "/undo 2"),
            ]),
            ("Agent", [
                ("/agent create", "创建 Agent", "/agent create coder"),
                ("/agent list", "列出 Agent", "/agent list"),
                ("/agent run <name>", "运行 Agent", "/agent run coder"),
                ("/master on|off", "主控开关", "/master on"),
                ("@local <cmd>", "本地操作", "@local 查看磁盘"),
                ("@remote <srv>", "远程 SSH", "@remote myserver df -h"),
                ("@spider <URL>", "网页爬虫", "@spider https://example.com"),
                ("@RAG <q>", "知识库问答", "@RAG 部署流程是什么"),
                ("@stock <query>", "股票量化", "@stock 查询茅台股价"),
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
                ("/rag sync", "同步知识库", "/rag sync"),
                ("/mcp list", "列出 MCP", "/mcp list"),
                ("/read_excel <f>", "读取 Excel", "/read_excel data.xlsx"),
                ("/read_csv <f>", "读取 CSV", "/read_csv data.csv"),
            ]),
            ("系统", [
                ("/shell", "Shell 模式", "/shell"),
                ("/mode <mode>", "思维模式", "/mode cot"),
                ("/queue", "查看队列", "/queue"),
                ("/usage [days]", "用量统计", "/usage 7"),
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
                ("/ls", "List files", "/ls"),
                ("/cat <file>", "Read file", "/cat README.md"),
                ("/cd <dir>", "Change dir", "/cd src"),
                ("/write <file>", "Write file", '/write a.md "content"'),
                ("/append <file>", "Append", '/append a.md "more"'),
                ("/delete <file>", "Delete file", "/delete tmp.txt"),
            ]),
            ("Session", [
                ("/new", "New session", "/new"),
                ("/save <name>", "Save session", "/save proj_v1"),
                ("/load <name>", "Load session", "/load proj_v1"),
                ("/session list", "List archives", "/session list"),
                ("/session load <n>", "Load archive", "/session load 2"),
                ("/undo [N]", "Undo turns", "/undo 2"),
            ]),
            ("Agent", [
                ("/agent create", "Create agent", "/agent create coder"),
                ("/agent list", "List agents", "/agent list"),
                ("/agent run <name>", "Run agent", "/agent run coder"),
                ("/master on|off", "Master toggle", "/master on"),
                ("@local <cmd>", "Local ops", "@local show disks"),
                ("@remote <srv>", "Remote SSH", "@remote myserver df -h"),
                ("@spider <URL>", "Web crawler", "@spider https://example.com"),
                ("@RAG <q>", "Knowledge Q&A", "@RAG deployment process"),
                ("@stock <query>", "Stock quant", "@stock quote 600519"),
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
                ("/rag sync", "Sync RAG", "/rag sync"),
                ("/mcp list", "List MCP", "/mcp list"),
                ("/read_excel <f>", "Read Excel", "/read_excel data.xlsx"),
                ("/read_csv <f>", "Read CSV", "/read_csv data.csv"),
            ]),
            ("System", [
                ("/shell", "Shell mode", "/shell"),
                ("/mode <mode>", "Thinking mode", "/mode cot"),
                ("/queue", "View queue", "/queue"),
                ("/usage [days]", "Usage stats", "/usage 7"),
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
        print(f"{_dim('详情: /help <主题>  主题: config, model, fs, session, agent, mail, m365, tools, mcp, all')}")
    else:
        print(f"{_dim('Details: /help <topic>  Topics: config, model, fs, session, agent, mail, m365, tools, mcp, all')}")
    print()


