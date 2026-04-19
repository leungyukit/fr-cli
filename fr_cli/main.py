"""
凡人打字机 - 主脑控制台
负责状态初始化、命令路由与 AI 交互循环
"""
import sys, os, re, subprocess
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from fr_cli.conf.config import init_config
from fr_cli.lang.i18n import T
from fr_cli.ui.ui import enable_win_ansi, print_banner, print_bye, CYAN, RED, YELLOW, GREEN, DIM, RESET
from fr_cli.core.stream import stream_cnt
from fr_cli.memory.history import save_sess, load_sess, del_sess, get_sessions
from fr_cli.memory.context import extract_recent_turns, build_context_summary, save_context, load_context
from fr_cli.addon.plugin import extract_code, PLUGIN_DIR
from fr_cli.core.recommender import recommend_features
from fr_cli.core.sysmon import get_sys_stats
from fr_cli.core.core import AppState


def _sync_manual_to_workspace(vfs):
    """将项目根目录的 MANUAL.md 复制到工作空间，使 AI 可通过 read_file 读取"""
    if not vfs.cwd:
        return
    try:
        manual_src = Path(__file__).parent.parent / "MANUAL.md"
        if not manual_src.exists():
            return
        manual_dst = Path(vfs.cwd) / "MANUAL.md"
        if not manual_dst.exists():
            import shutil
            shutil.copy2(manual_src, manual_dst)
    except Exception:
        pass


def _print_help(state, topic):
    """打印修仙指南"""
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
        "all": "all",
    }
    mapped = topic_map.get(topic, "")
    lang = state.lang

    if not mapped:
        print(f"{CYAN}{T('help_title', lang)}{RESET}")
        print(f"  {T('help_cfg', lang)} /model /key /limit /alias /export /update")
        print(f"  {T('help_fs', lang)} /ls /cat /cd /write /append /delete")
        print(f"  {T('help_sess', lang)} /save /load /del /undo")
        print(f"  {T('help_plugin', lang)} /skills (自动进化)")
        print(f"  {T('help_extra', lang)} /mail_* /cron_* /web /fetch /disk_* /see")
        print(f"  {DIM}  Agent: /agent_create /agent_list /agent_run /agent_show /agent_edit /agent_delete{RESET}")
        print(f"  {DIM}  Agent API: /agent_server start [port] | stop | status{RESET}")
        print(f"  {DIM}  本机应用: /open <路径/URL> | /launch <应用> [目标] | /apps{RESET}")
        print(f"  {DIM}  内置Agent: @local <需求> | @remote [IP] <需求> | @spider <URL> [深度] | @db <需求> | @RAG <问题>{RESET}")
        print(f"  {DIM}  数据: /read_excel <文件> | /read_csv <文件>{RESET}")
        print(f"  {T('help_shell', lang)} {T('shell_tip', lang)}\n                {T('pipe_tip', lang)}")
        print(f"\n{T('help_usage', lang)}")
    elif mapped == "all":
        for t in ["config", "fs", "session", "plugin", "mail", "cron", "web", "disk", "vision", "shell", "tools", "security", "app"]:
            print(T(f"help_detail_{t}", lang))
            print()
    else:
        detail = T(f"help_detail_{mapped}", lang)
        if detail:
            print(detail)
        else:
            print(T("help_not_found", lang, topic))


def _handle_ai_chat(state, u):
    """处理 AI 正常对话流程"""
    from fr_cli.weapon.loader import get_available_tools, should_inject_tools
    from fr_cli.weapon.vision import prep_see_msg
    from fr_cli.addon.plugin import exec_plugin

    lang = state.lang
    prompt = u
    if state.vfs.cwd:
        prompt += T("ctx_dir", lang, state.vfs.cwd)

    # 程序层面判定是否需要注入工具信息
    tools = get_available_tools(state.weapon_tools, state.plugins)
    if should_inject_tools(u, state.weapon_triggers):
        tools_info = "\n\n当前可用的工具列表：\n"
        for i, tool in enumerate(tools, 1):
            tools_info += f"{i}. {tool['name']}: {tool['description']}\n   可用命令: {', '.join(tool['commands'])}\n"
        sp = T("sys_prompt", lang)
        system_content = sp + tools_info + state.context_summary
    else:
        sp = T("sys_prompt", lang)
        system_content = sp + state.context_summary

    # 更新系统提示词
    updated_messages = state.messages.copy()
    if not updated_messages or updated_messages[0]["role"] != "system":
        updated_messages.insert(0, {"role": "system", "content": system_content})
    else:
        updated_messages[0]["content"] = system_content

    updated_messages.append({"role": "user", "content": prompt})

    # 检测是否调用了本地技能
    triggered_plugin = None
    for pk in state.plugins:
        if prompt.startswith(f"/{pk} "):
            triggered_plugin = pk
            p_args = prompt[len(f"/{pk} "):].strip()
            break

    if triggered_plugin:
        if state.security.check("sec_exec", f"/{triggered_plugin}"):
            exec_plugin(triggered_plugin, state.plugins[triggered_plugin], p_args, lang)
        updated_messages.append({"role": "assistant", "content": f"[Executed /{triggered_plugin}]"})
        state.messages = updated_messages
        return

    # 流式调用 AI
    txt, usage, response_time = stream_cnt(
        state.client, state.model_name, updated_messages, lang,
        max_tokens=state.limit
    )
    updated_messages.append({"role": "assistant", "content": txt})

    # 自动执行 AI 响应中的命令
    clean_txt, cmd_results = state.executor.process_ai_commands(txt, updated_messages)

    # 显示 AI 响应（去除命令标记后的内容）
    if clean_txt.strip():
        print(clean_txt)

    # 显示命令执行结果，并再次调用 AI
    if cmd_results:
        print(f"\n{CYAN}🤖 自动执行命令:{RESET}")
        for result in cmd_results:
            print(f"{DIM}{result}{RESET}")

        updated_messages[-1]["content"] = clean_txt if clean_txt.strip() else "[已执行命令]"
        updated_messages.append({
            "role": "system",
            "content": f"命令执行结果:\n" + "\n".join(cmd_results)
        })

        sys.stdout.write(f"{CYAN}{T('prompt_ai', lang)}{RESET} ")
        sys.stdout.flush()
        final_txt, final_usage, final_response_time = stream_cnt(
            state.client, state.model_name, updated_messages, lang,
            custom_prefix="", max_tokens=state.limit
        )
        updated_messages.append({"role": "assistant", "content": final_txt})

        if final_usage:
            usage = final_usage
        response_time += final_response_time

    # 显示模型信息和 token 使用情况
    sys_stats = get_sys_stats(lang)
    stats_extra = f" | {sys_stats}" if sys_stats else ""
    if usage:
        input_tokens = usage.get('prompt_tokens', 0)
        output_tokens = usage.get('completion_tokens', 0)
        total_tokens = usage.get('total_tokens', 0)
        print(f"{DIM}📊 模型: {state.model_name} | 输入: {input_tokens} tokens | 输出: {output_tokens} tokens | 总计: {total_tokens} tokens | 耗时: {response_time:.2f}秒{stats_extra}{RESET}")
    else:
        print(f"{DIM}📊 模型: {state.model_name} | 耗时: {response_time:.2f}秒{stats_extra}{RESET}")

    # 智能功能推荐
    recommendations = recommend_features(u)
    if recommendations:
        print(f"{CYAN}💡 推荐功能:{RESET}")
        for i, rec in enumerate(recommendations[:5], 1):
            print(f"  {DIM}[{i}]{RESET} {CYAN}{rec['cmd']}{RESET} - {rec['desc']}")

    # 智能法宝进化检测
    if "def run(args='')" in txt and "```python" in txt:
        code = extract_code(txt)
        if code and "def run" in code and len(code) > 50:
            pname = input(f"{YELLOW}{T('artifact_detect', lang)}{RESET}").strip()
            if pname:
                safe_name = "".join(c for c in pname if c.isalnum() or c == '_')
                if state.security.check("sec_write", f"/{safe_name}"):
                    PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
                    p_path = PLUGIN_DIR / f"{safe_name}.py"
                    p_path.write_text(code, encoding='utf-8')
                    state.plugins[safe_name] = str(p_path)
                    print(f"{GREEN}{T('ok_forged', lang, safe_name)}{RESET}")

    # 更新记忆上下文
    recent = extract_recent_turns(updated_messages, 5)
    state.context_summary = build_context_summary(recent, lang)
    save_context(state.sn, state.context_summary)

    # 更新主消息列表
    state.messages = updated_messages


def main():
    enable_win_ansi()
    cfg = init_config()
    state = AppState(cfg)

    # 将 MANUAL.md 同步到工作空间
    _sync_manual_to_workspace(state.vfs)

    # 加载历史会话或初始化系统提示词
    sp = T("sys_prompt", state.lang)
    if state.sn:
        ok, m, _ = load_sess(0, sp)
        if ok:
            state.messages = m
    if not state.messages:
        state.messages = [{"role": "system", "content": sp}]

    # 加载当前会话的记忆上下文
    state.context_summary = load_context(state.sn)

    # 启动动画
    print_banner(state.model_name, state.limit, cfg.get("allowed_dirs", [""]), state.sn, state.lang)

    # ================= 主循环 =================
    while True:
        try:
            u = input(f"{CYAN}>>> {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print_bye()
            break

        if not u:
            continue

        # 替换别名
        if u in state.aliases:
            u = state.aliases[u]

        # ----------------- 内置指令路由 -----------------
        if u.startswith("/"):
            parts = u.split(maxsplit=2)
            cmd = parts[0].lower()
            arg1 = parts[1] if len(parts) > 1 else ""

            if cmd in ("/exit", "/quit"):
                print_bye()
                break

            elif cmd == "/help":
                _print_help(state, arg1.lower())

            elif cmd == "/model" and arg1:
                state.update_model(arg1)
                print(f"{GREEN}{T('ok_model', state.lang, arg1)}{RESET}")

            elif cmd == "/key" and arg1:
                state.update_key(arg1)
                print(f"{GREEN}{T('ok_key', state.lang)}{RESET}")

            elif cmd == "/limit" and arg1:
                try:
                    v = int(arg1)
                    if v < 1000:
                        raise ValueError
                    state.update_limit(v)
                    print(f"{GREEN}{T('ok_limit', state.lang, v)}{RESET}")
                except ValueError:
                    print(f"{RED}{T('err_limit', state.lang)}{RESET}")

            elif cmd == "/lang" and arg1:
                if arg1 in ["zh", "en"]:
                    state.update_lang(arg1)
                    print(f"{GREEN}语言已切换为: {'中文' if arg1 == 'zh' else 'English'}{RESET}")
                else:
                    print(f"{RED}支持的语言: zh (中文), en (English){RESET}")

            elif cmd == "/dir" and arg1:
                ok, m = state.vfs.add(arg1, state.lang)
                if ok:
                    state.cfg["allowed_dirs"] = state.vfs.ds
                    state.save_cfg()
                print(m)

            elif cmd == "/save" and arg1:
                state.update_session_name(arg1)
                if save_sess(arg1, state.messages):
                    print(f"{GREEN}{T('ok_sess_save', state.lang, arg1)}{RESET}")
                    recent = extract_recent_turns(state.messages, 5)
                    ctx = build_context_summary(recent, state.lang)
                    save_context(arg1, ctx)

            elif cmd == "/load":
                ss = get_sessions()
                if not ss:
                    print(T("no_sess", state.lang))
                    continue
                for i, s in enumerate(ss):
                    print(f"  [{i}] {s['name']}")
                idx = input(f"{YELLOW}ID: {RESET}").strip()
                if idx.isdigit():
                    ok, m, name = load_sess(int(idx), sp)
                    if ok:
                        state.messages = m
                        state.update_session_name(name)
                        state.context_summary = load_context(name)
                        print(f"{GREEN}{T('ok_sess_load', state.lang, name)}{RESET}")

            elif cmd == "/del":
                ss = get_sessions()
                if not ss:
                    print(T("no_sess", state.lang))
                    continue
                for i, s in enumerate(ss):
                    print(f"  [{i}] {s['name']}")
                idx = input(f"{YELLOW}ID: {RESET}").strip()
                if idx.isdigit() and del_sess(int(idx)):
                    print(GREEN + T("ok_sess_del", state.lang) + RESET)

            elif cmd == "/see" and arg1:
                from fr_cli.weapon.vision import prep_see_msg
                if state.model_name != "glm-4v-plus":
                    print(f"{YELLOW}{T('see_warn', state.lang)}{RESET}")
                print(f"{CYAN}{T('see_ing', state.lang)}{RESET}")
                prep_see_msg(state.messages, arg1, parts[2] if len(parts) > 2 else "")
                txt, _, response_time = stream_cnt(
                    state.client, state.model_name, state.messages, state.lang,
                    max_tokens=state.limit
                )
                state.messages.append({"role": "assistant", "content": txt})
                sys_stats = get_sys_stats(state.lang)
                stats_extra = f" | {sys_stats}" if sys_stats else ""
                print(f"{DIM}📊 {T('stats_model', state.lang)}: {state.model_name} | {T('stats_time', state.lang)}: {response_time:.2f}{T('stats_seconds', state.lang)}{stats_extra}{RESET}")

            elif cmd == "/update":
                from fr_cli.breakthrough.update import update_check, update_and_restart
                if arg1 == "check":
                    ok, info, err = update_check(verbose=False)
                    if err:
                        print(f"{RED}[更新] 检查失败: {err}{RESET}")
                    elif not ok:
                        print(f"{GREEN}[更新] 当前已是最新版本。{RESET}")
                    else:
                        ver = info.get("version", "?")
                        note = info.get("release_note", "")
                        print(f"{YELLOW}[更新] 发现新版本: {ver}{RESET}")
                        if note:
                            print(f"{DIM}更新说明:\n{note}{RESET}")
                        print(f"{DIM}输入 /update run 执行更新{RESET}")
                elif arg1 == "run":
                    print(f"{YELLOW}[更新] 正在连接天道获取最新法器...{RESET}")
                    ok, msg = update_and_restart(verbose=True, allow_restart=True)
                    if ok:
                        print(f"{GREEN}{msg}{RESET}")
                    else:
                        print(f"{RED}{msg}{RESET}")
                else:
                    print(f"{DIM}用法: /update check (检查) | /update run (执行更新){RESET}")

            elif cmd == "/agent_server":
                from fr_cli.agent.server import AgentHTTPServer
                if arg1 == "start":
                    port = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 17890
                    if state.agent_server is None:
                        state.agent_server = AgentHTTPServer(state, port=port)
                    ok, msg = state.agent_server.start()
                    color = GREEN if ok else YELLOW
                    print(f"{color}{msg}{RESET}")
                elif arg1 == "stop":
                    if state.agent_server is None:
                        print(f"{YELLOW}服务未运行{RESET}")
                    else:
                        ok, msg = state.agent_server.stop()
                        color = GREEN if ok else YELLOW
                        print(f"{color}{msg}{RESET}")
                elif arg1 == "status":
                    if state.agent_server is None:
                        print(f"{DIM}未运行{RESET}")
                    else:
                        print(f"{CYAN}{state.agent_server.status()}{RESET}")
                else:
                    print(f"{DIM}用法: /agent_server start [port] | /agent_server stop | /agent_server status{RESET}")

            elif cmd == "/open" and arg1:
                from fr_cli.weapon.launcher import open_file
                ok, msg = open_file(arg1, state.lang)
                color = GREEN if ok else RED
                print(f"{color}{msg}{RESET}")

            elif cmd == "/launch" and arg1:
                from fr_cli.weapon.launcher import launch_app
                target = parts[2] if len(parts) > 2 else None
                ok, msg = launch_app(arg1, target, state.lang)
                color = GREEN if ok else RED
                print(f"{color}{msg}{RESET}")

            elif cmd == "/apps":
                from fr_cli.weapon.launcher import list_apps
                res, err = list_apps(state.lang)
                if err:
                    print(f"{RED}{err}{RESET}")
                else:
                    print(f"{CYAN}{res}{RESET}")

            elif cmd == "/agent_create" and arg1:
                from fr_cli.agent.generator import generate_agent
                from fr_cli.agent.manager import save_persona, save_skills, save_agent_code, create_agent_dir
                desc = parts[2] if len(parts) > 2 else ""
                if not desc:
                    print(f"{YELLOW}用法: /agent_create <名称> <需求描述>{RESET}")
                    continue
                d = create_agent_dir(arg1)
                result = generate_agent(state.client, state.model_name, arg1, desc, state.lang)
                if result["persona"]:
                    save_persona(arg1, result["persona"])
                if result["skills"]:
                    save_skills(arg1, result["skills"])
                if result["code"]:
                    save_agent_code(arg1, result["code"])
                print(f"{GREEN}✅ Agent [{arg1}] 铸造完成！{RESET}")
                print(f"{DIM}  人设: {'已生成' if result['persona'] else '未生成'}{RESET}")
                print(f"{DIM}  技能: {'已生成' if result['skills'] else '未生成'}{RESET}")
                print(f"{DIM}  代码: {'已生成' if result['code'] else '未生成'}{RESET}")
                print(f"{DIM}  路径: {d}{RESET}")

            elif cmd == "/agent_list":
                from fr_cli.agent.manager import list_agents
                agents = list_agents()
                if not agents:
                    print(f"{YELLOW}暂无 Agent 分身。使用 /agent_create <名称> <描述> 创建。{RESET}")
                else:
                    print(f"{CYAN}已创建的 Agent 分身:{RESET}")
                    for a in agents:
                        flags = []
                        if a["has_persona"]: flags.append("人设")
                        if a["has_memory"]: flags.append("记忆")
                        if a["has_skills"]: flags.append("技能")
                        flag_str = f" ({', '.join(flags)})" if flags else ""
                        print(f"  {a['name']}{flag_str}")

            elif cmd == "/agent_delete" and arg1:
                from fr_cli.agent.manager import delete_agent
                if delete_agent(arg1):
                    print(f"{GREEN}✅ Agent [{arg1}] 已抹除。{RESET}")
                else:
                    print(f"{RED}Agent [{arg1}] 不存在。{RESET}")

            elif cmd == "/agent_show" and arg1:
                from fr_cli.agent.manager import agent_exists, load_persona, load_memory, load_skills, load_agent_code
                from fr_cli.agent.workflow import load_workflow
                if not agent_exists(arg1):
                    print(f"{RED}Agent [{arg1}] 不存在。{RESET}")
                else:
                    print(f"{CYAN}═══ Agent: {arg1} ═══{RESET}")
                    p = load_persona(arg1)
                    m = load_memory(arg1)
                    s = load_skills(arg1)
                    c = load_agent_code(arg1)
                    w = load_workflow(arg1)
                    if p: print(f"\n{DIM}[人设]{RESET}\n{p[:500]}{'...' if len(p) > 500 else ''}")
                    if s: print(f"\n{DIM}[技能]{RESET}\n{s[:500]}{'...' if len(s) > 500 else ''}")
                    if m: print(f"\n{DIM}[记忆]{RESET}\n{m[:300]}{'...' if len(m) > 300 else ''}")
                    if c: print(f"\n{DIM}[代码]{RESET}\n{c[:300]}{'...' if len(c) > 300 else ''}")
                    if w: print(f"\n{DIM}[工作流]{RESET}\n{w[:300]}{'...' if len(w) > 300 else ''}")

            elif cmd == "/agent_run" and arg1:
                from fr_cli.agent.executor import run_agent
                run_args = parts[2] if len(parts) > 2 else ""
                kwargs = {"user_input": run_args} if run_args else {}
                result, err = run_agent(arg1, state, **kwargs)
                if err:
                    print(f"{RED}{err}{RESET}")
                else:
                    print(f"{GREEN}{result}{RESET}")

            elif cmd == "/agent_edit" and arg1:
                from fr_cli.agent.manager import agent_exists, save_persona, save_memory, save_skills, save_agent_code
                from fr_cli.agent.workflow import save_workflow
                if not agent_exists(arg1):
                    print(f"{RED}Agent [{arg1}] 不存在。{RESET}")
                    continue
                file_type = parts[2] if len(parts) > 2 else ""
                valid_types = {"persona", "memory", "skills", "agent", "workflow"}
                if file_type not in valid_types:
                    print(f"{YELLOW}用法: /agent_edit <名称> <类型>，类型: persona/memory/skills/agent/workflow{RESET}")
                    continue
                print(f"{CYAN}请输入新的 {file_type} 内容（Ctrl+D 结束）:{RESET}")
                try:
                    new_content = sys.stdin.read().strip()
                except (EOFError, KeyboardInterrupt):
                    new_content = ""
                if not new_content:
                    print(f"{YELLOW}内容为空，未保存。{RESET}")
                    continue
                if file_type == "persona":
                    save_persona(arg1, new_content)
                elif file_type == "memory":
                    save_memory(arg1, new_content)
                elif file_type == "skills":
                    save_skills(arg1, new_content)
                elif file_type == "agent":
                    save_agent_code(arg1, new_content)
                elif file_type == "workflow":
                    save_workflow(arg1, new_content)
                print(f"{GREEN}✅ {file_type} 已更新。{RESET}")

            elif cmd == "/remote_setup":
                from fr_cli.agent.builtins.remote import _setup_wizard
                _setup_wizard(state.lang)

            elif cmd == "/db_setup":
                from fr_cli.agent.builtins.db import _setup_wizard as db_setup
                db_setup(state.lang)

            elif cmd == "/rag_dir" and arg1:
                from pathlib import Path as _Path
                p = _Path(arg1)
                if not p.exists():
                    print(f"{RED}目录不存在: {arg1}{RESET}")
                else:
                    state.cfg["rag_dir"] = str(p.resolve())
                    state.save_cfg()
                    print(f"{GREEN}✅ 知识库目录已设置: {p.resolve()}{RESET}")
                    from fr_cli.agent.builtins.rag import get_rag_manager
                    mgr = get_rag_manager(str(p.resolve()))
                    ok, msg = mgr.sync_directory()
                    print(f"{GREEN if ok else YELLOW}{msg}{RESET}")
                    if ok:
                        mgr.start_watcher()

            elif cmd == "/read_excel" and arg1:
                from fr_cli.weapon.dataframe import read_excel
                res, err = read_excel(arg1, lang=state.lang)
                if err:
                    print(f"{RED}{err}{RESET}")
                else:
                    print(f"{CYAN}{res[:2000]}{RESET}")
                    if len(res) > 2000:
                        print(f"{DIM}... (共 {len(res)} 字符，使用 AI 对话进行分析){RESET}")

            elif cmd == "/read_csv" and arg1:
                from fr_cli.weapon.dataframe import read_csv
                res, err = read_csv(arg1, lang=state.lang)
                if err:
                    print(f"{RED}{err}{RESET}")
                else:
                    print(f"{CYAN}{res[:2000]}{RESET}")
                    if len(res) > 2000:
                        print(f"{DIM}... (共 {len(res)} 字符，使用 AI 对话进行分析){RESET}")

            else:
                # 其余命令统一委托给执行引擎
                result, error = state.executor.execute(u, state.messages)
                if error:
                    print(f"{RED}{error}{RESET}")
                elif result is not None:
                    # 根据命令类型做简单格式化
                    if cmd == "/cat" and arg1:
                        print(f"\n{DIM}--- {arg1} ---{RESET}\n{result}\n{DIM}--- EOF ---{RESET}")
                    elif cmd == "/fetch" and arg1:
                        print(f"{DIM}--- Fetch ---{RESET}\n{result}\n{DIM}--- EOF ---{RESET}")
                    elif cmd == "/skills":
                        print("\n".join([f"{CYAN}{line}{RESET}" for line in result.split("\n")]))
                    else:
                        print(result)

        # ----------------- 破壁指令 -----------------
        elif u.startswith("!"):
            is_pipe = "|" in u
            shell_cmd = u[1:].split("|")[0].strip()

            if state.security.check("sec_shell", shell_cmd):
                try:
                    res = subprocess.run(shell_cmd, shell=True, capture_output=True, text=True, timeout=15)
                    out = res.stdout + res.stderr
                    if is_pipe:
                        pipe_prompt = u.split("|", 1)[1].strip()
                        final_prompt = f"{T('pipe_prefix', state.lang)}{out}\n\n{pipe_prompt}"
                        if state.vfs.cwd:
                            final_prompt += T("ctx_dir", state.lang, state.vfs.cwd)
                        state.messages.append({"role": "user", "content": final_prompt})
                        txt, _, response_time = stream_cnt(
                            state.client, state.model_name, state.messages, state.lang,
                            max_tokens=state.limit
                        )
                        state.messages.append({"role": "assistant", "content": txt})

                        # 自动执行 AI 响应中的命令（与 _handle_ai_chat 保持一致）
                        clean_txt, cmd_results = state.executor.process_ai_commands(txt, state.messages)
                        if cmd_results:
                            print(f"\n{CYAN}🤖 自动执行命令:{RESET}")
                            for result in cmd_results:
                                print(f"{DIM}{result}{RESET}")
                            state.messages[-1]["content"] = clean_txt if clean_txt.strip() else "[已执行命令]"
                            state.messages.append({
                                "role": "system",
                                "content": f"命令执行结果:\n" + "\n".join(cmd_results)
                            })
                            sys.stdout.write(f"{CYAN}{T('prompt_ai', state.lang)}{RESET} ")
                            sys.stdout.flush()
                            final_txt, _, final_response_time = stream_cnt(
                                state.client, state.model_name, state.messages, state.lang,
                                custom_prefix="", max_tokens=state.limit
                            )
                            state.messages.append({"role": "assistant", "content": final_txt})
                            response_time += final_response_time

                        print(f"{DIM}📊 {T('stats_model', state.lang)}: {state.model_name} | {T('stats_time', state.lang)}: {response_time:.2f}{T('stats_seconds', state.lang)}{RESET}")
                    else:
                        if out.strip():
                            print(out.strip()[:2000])
                except subprocess.TimeoutExpired:
                    print(f"{RED}Timeout{RESET}")
                except Exception as e:
                    print(f"{RED}{e}{RESET}")

        # ----------------- 内置 Agent 前缀拦截 -----------------
        elif u.startswith("@local "):
            from fr_cli.agent.builtins.local import handle_local
            handle_local(u, state)

        elif u.startswith("@remote "):
            from fr_cli.agent.builtins.remote import handle_remote
            handle_remote(u, state)

        elif u.startswith("@spider "):
            from fr_cli.agent.builtins.spider import handle_spider
            handle_spider(u, state)

        elif u.startswith("@db "):
            from fr_cli.agent.builtins.db import handle_db
            handle_db(u, state)

        elif u.startswith("@RAG ") or u.startswith("@rag "):
            from fr_cli.agent.builtins.rag import handle_rag
            handle_rag(u, state)

        # ----------------- AI 正常对话 -----------------
        else:
            _handle_ai_chat(state, u)


if __name__ == "__main__":
    main()
