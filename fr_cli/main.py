"""
凡人打字机 - 主脑控制台
负责状态初始化、命令路由与 AI 交互循环
"""
import sys, os, subprocess, platform, shutil
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from fr_cli.conf.config import init_config, ConfigError
from fr_cli.lang.i18n import T
from fr_cli.ui.ui import enable_win_ansi, print_banner, print_bye, CYAN, RED, YELLOW, DIM, RESET
from fr_cli.core.stream import stream_cnt
from fr_cli.memory.history import load_sess
from fr_cli.memory.context import load_context
from fr_cli.core.core import AppState
from fr_cli.core.chat import handle_ai_chat


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


# ------------------------------------------------------------------
# 命令路由函数（将 main() 中巨大的 if-elif 链提取为字典映射）
# 返回 True 表示应退出主循环
# ------------------------------------------------------------------

from fr_cli.repl.commands import (
    _cmd_exit,
    _cmd_help,
    _cmd_model,
    _cmd_key,
    _cmd_limit,
    _cmd_lang,
    _cmd_dir,
    _cmd_dirs,
    _cmd_rmdir,
    _cmd_save,
    _cmd_load,
    _cmd_del,
    _cmd_session_list,
    _cmd_session_load,
    _cmd_session_del,
    _cmd_see,
    _cmd_update,
    _cmd_agent_server,
    _cmd_mode,
    _cmd_gatekeeper,
    _cmd_open,
    _cmd_launch,
    _cmd_apps,
    _cmd_agent_create,
    _cmd_agent_list,
    _cmd_agent_delete,
    _cmd_agent_show,
    _cmd_agent_run,
    _cmd_agent_edit,
    _cmd_agent_forge,
    _cmd_remote_agent_add,
    _cmd_remote_agent_list,
    _cmd_remote_agent_del,
    _cmd_agent_publish,
    _cmd_remote_agent_scan,
    _cmd_remote_agent_import,
    _cmd_remote_setup,
    _cmd_db_setup,
    _cmd_agent_cron_add,
    _cmd_agent_cron_list,
    _cmd_agent_cron_del,
    _cmd_rag_dir,
    _cmd_rag_watch,
    _cmd_rag_sync,
    _cmd_read_excel,
    _cmd_read_csv,
    _cmd_master,
    _cmd_providers,
    _cmd_mcp_list,
    _cmd_mcp_add,
    _cmd_mcp_del,
    _cmd_mcp_enable,
    _cmd_mcp_disable,
    _cmd_mcp_refresh,
)


_COMMAND_ROUTES = {
    "/exit": _cmd_exit,
    "/quit": _cmd_exit,
    "/help": _cmd_help,
    "/model": _cmd_model,
    "/key": _cmd_key,
    "/limit": _cmd_limit,
    "/lang": _cmd_lang,
    "/mode": _cmd_mode,
    "/dir": _cmd_dir,
    "/dirs": _cmd_dirs,
    "/rmdir": _cmd_rmdir,
    "/save": _cmd_save,
    "/load": _cmd_load,
    "/del": _cmd_del,
    "/session_list": _cmd_session_list,
    "/session_load": _cmd_session_load,
    "/session_del": _cmd_session_del,
    "/see": _cmd_see,
    "/update": _cmd_update,
    "/agent_server": _cmd_agent_server,
    "/gatekeeper": _cmd_gatekeeper,
    "/open": _cmd_open,
    "/launch": _cmd_launch,
    "/apps": _cmd_apps,
    "/agent_create": _cmd_agent_create,
    "/agent_list": _cmd_agent_list,
    "/agent_delete": _cmd_agent_delete,
    "/agent_show": _cmd_agent_show,
    "/agent_run": _cmd_agent_run,
    "/agent_edit": _cmd_agent_edit,
    "/agent_forge": _cmd_agent_forge,
    "/remote_agent_add": _cmd_remote_agent_add,
    "/remote_agent_list": _cmd_remote_agent_list,
    "/remote_agent_del": _cmd_remote_agent_del,
    "/agent_publish": _cmd_agent_publish,
    "/remote_agent_scan": _cmd_remote_agent_scan,
    "/remote_agent_import": _cmd_remote_agent_import,
    "/remote_setup": _cmd_remote_setup,
    "/db_setup": _cmd_db_setup,
    "/agent_cron_add": _cmd_agent_cron_add,
    "/agent_cron_list": _cmd_agent_cron_list,
    "/agent_cron_del": _cmd_agent_cron_del,
    "/rag_dir": _cmd_rag_dir,
    "/rag_watch": _cmd_rag_watch,
    "/rag_sync": _cmd_rag_sync,
    "/read_excel": _cmd_read_excel,
    "/read_csv": _cmd_read_csv,
    "/master": _cmd_master,
    "/providers": _cmd_providers,
    "/mcp_list": _cmd_mcp_list,
    "/mcp_add": _cmd_mcp_add,
    "/mcp_del": _cmd_mcp_del,
    "/mcp_enable": _cmd_mcp_enable,
    "/mcp_disable": _cmd_mcp_disable,
    "/mcp_refresh": _cmd_mcp_refresh,
}


def main():
    enable_win_ansi()
    try:
        cfg = init_config()
    except ConfigError:
        print(f"{RED}配置初始化失败，退出。{RESET}")
        return
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
    print_banner(state.model_name, state.limit, cfg.get("allowed_dirs", [""]), state.sn, state.lang, state.provider)

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
            parts = u.split()
            cmd = parts[0].lower()
            arg1 = parts[1] if len(parts) > 1 else ""

            if cmd in _COMMAND_ROUTES:
                if _COMMAND_ROUTES[cmd](state, parts):
                    break
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
                    if platform.system() == "Windows":
                        ps_exe = shutil.which("pwsh") or shutil.which("powershell")
                        if ps_exe:
                            res = subprocess.run([ps_exe, "-Command", shell_cmd], capture_output=True, text=True, timeout=15)
                        else:
                            res = subprocess.run(shell_cmd, shell=True, capture_output=True, text=True, timeout=15)
                    else:
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

                        # 自动执行 AI 响应中的命令（与 handle_ai_chat 保持一致）
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
            try:
                from fr_cli.agent.builtins.local import handle_local
                handle_local(u, state)
            except Exception as e:
                print(f"{RED}@local Agent 执行失败: {e}{RESET}")

        elif u.startswith("@remote "):
            try:
                from fr_cli.agent.builtins.remote import handle_remote
                handle_remote(u, state)
            except Exception as e:
                print(f"{RED}@remote Agent 执行失败: {e}{RESET}")

        elif u.startswith("@spider "):
            try:
                from fr_cli.agent.builtins.spider import handle_spider
                handle_spider(u, state)
            except Exception as e:
                print(f"{RED}@spider Agent 执行失败: {e}{RESET}")

        elif u.startswith("@db "):
            try:
                from fr_cli.agent.builtins.db import handle_db
                handle_db(u, state)
            except Exception as e:
                print(f"{RED}@db Agent 执行失败: {e}{RESET}")

        elif u.startswith("@RAG ") or u.startswith("@rag "):
            try:
                from fr_cli.agent.builtins.rag import handle_rag
                handle_rag(u, state)
            except Exception as e:
                print(f"{RED}@RAG Agent 执行失败: {e}{RESET}")

        # ----------------- AI 正常对话 -----------------
        else:
            if state.master_agent.is_enabled():
                reply, _ = state.master_agent.handle(u)
                print(f"\n{CYAN}{reply}{RESET}")
            else:
                handle_ai_chat(state, u)


if __name__ == "__main__":
    main()
