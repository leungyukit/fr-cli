"""
REPL 命令路由处理器
从 main.py 提取的所有 / 命令实现，减轻主模块负担。
"""
import sys

from fr_cli.lang.i18n import T
from fr_cli.ui.ui import (
    CYAN, RED, YELLOW, GREEN, DIM, RESET,
    print_bye
)
from fr_cli.agent.shell_mode import ShellMode
from fr_cli.memory.history import save_sess, load_sess, del_sess, get_sessions
from fr_cli.memory.context import load_context, extract_recent_turns, build_context_summary, save_context
from fr_cli.memory.session import (
    list_sessions as list_auto_sessions,
    load_session as load_auto_session,
    delete_session as delete_auto_session,
)
from fr_cli.addon.plugin import extract_code
from fr_cli.core.stream import stream_cnt
from fr_cli.core.sysmon import get_sys_stats
from fr_cli.agent.manager import (
    create_agent_dir, save_agent_code, save_persona, save_skills,
    save_memory, agent_exists, list_agents, delete_agent,
    load_persona, load_memory, load_skills,
)
from fr_cli.agent.executor import run_agent



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
        "config": "config",
        "fs": "fs", "file": "fs", "files": "fs",
        "session": "session", "sess": "session",
        "plugin": "plugin", "plugins": "plugin", "skill": "plugin", "skills": "plugin",
        "mail": "mail", "email": "mail",
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
            for t in ["config", "fs", "session", "plugin", "mail", "cron", "web", "disk", "vision", "shell", "tools", "security", "app", "agent", "builtin", "dataframe", "gatekeeper", "mcp"]:
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
    cur = f"当前: {state.provider}/{state.model_name}" if is_zh else f"Current: {state.provider}/{state.model_name}"

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
                ("/tutorial", "交互教程", "/tutorial"),
                ("/help <topic>", "主题帮助", "/help agent"),
                ("/exit", "退出程序", "/exit"),
            ]),
        ]
    else:
        groups = [
            ("Model", [
                ("/model", "Switch model", "/model 3  or  /model deepseek:deepseek-chat"),
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
        print(f"{_dim('详情: /help <主题>  主题: config, fs, session, agent, tools, mcp, all')}")
    else:
        print(f"{_dim('Details: /help <topic>  Topics: config, fs, session, agent, tools, mcp, all')}")
    print()


