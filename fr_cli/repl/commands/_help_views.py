"""
/help 渲染 —— 新功能区 / 单命令详情 / 完整帮助

从 fr_cli.repl.commands._common 拆出(原文件 420 行)。
数据在 _help_data.py,本文件只负责排版输出。
"""
from __future__ import annotations

import re

from fr_cli.lang.i18n import T
from fr_cli.ui.ui import (
    CYAN, GREEN, YELLOW, DIM, RESET
)

from fr_cli.repl.commands._help_data import (
    _COMMAND_BRIEF,
    _NEW_COMMANDS,
    HELP_ALL_TOPICS,
    HELP_GROUPS_EN,
    HELP_GROUPS_ZH,
    HELP_TOPIC_MAP,
)


def _print_new_commands(state, lang):
    """打印'新功能 / 推荐'区,带 emoji 标记"""
    is_zh = (lang == "zh")
    title = "[NEW] 最近新功能 / 试用推荐" if is_zh else "[NEW] Recent features / try these"
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


def _print_help(state, topic):
    """打印帮助指南（现代 CLI 风格：分组 + 固定宽度对齐）

    支持的 topic:
      - /help              默认帮助(顶部显示新功能,下面是分类命令)
      - /help new          只看新功能列表
      - /help all          完整所有分类详情
      - /help <category>   单个分类(config / fs / agent / ...)
      - /help <command>    精确查单个命令(/insight, /competitor_gaps 等)
    """
    topic_map = HELP_TOPIC_MAP
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
            for t in HELP_ALL_TOPICS:
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

    # 顶部:[NEW] 新功能(让用户先看到最近加的)
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
    def _plain_len(s):
        return len(re.sub(r'\033\[[0-9;]*m', '', s))

    def _pad(s, width):
        return s + " " * max(width - _plain_len(s), 0)

    # 命令分组（cmd, desc, example）
    groups = HELP_GROUPS_ZH if is_zh else HELP_GROUPS_EN

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
