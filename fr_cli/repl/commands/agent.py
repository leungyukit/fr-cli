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



def _cmd_agent_create(state, parts):
    from fr_cli.agent.generator import generate_agent
    from fr_cli.agent.manager import save_persona, save_skills, save_agent_code, create_agent_dir
    arg1 = parts[1] if len(parts) > 1 else ""
    desc = parts[2] if len(parts) > 2 else ""
    if not arg1 or not desc:
        print(f"{YELLOW}用法: /agent_create <名称> <需求描述>{RESET}")
        return False
    d = create_agent_dir(arg1)
    result = generate_agent(state.client, state.model_name, arg1, desc, state.lang)
    if result["persona"]:
        save_persona(arg1, result["persona"])
    if result["skills"]:
        save_skills(arg1, result["skills"])
    if result["code"]:
        save_agent_code(arg1, result["code"])
    print(f"{GREEN}✅ Agent [{arg1}] 创建完成！{RESET}")
    print(f"{DIM}  人设: {'已生成' if result['persona'] else '未生成'}{RESET}")
    print(f"{DIM}  技能: {'已生成' if result['skills'] else '未生成'}{RESET}")
    print(f"{DIM}  代码: {'已生成' if result['code'] else '未生成'}{RESET}")
    print(f"{DIM}  路径: {d}{RESET}")
    return False



def _cmd_agent_list(state, parts):
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
    return False



def _cmd_agent_delete(state, parts):
    from fr_cli.agent.manager import delete_agent
    arg1 = parts[1] if len(parts) > 1 else ""
    if arg1:
        if delete_agent(arg1):
            print(f"{GREEN}✅ Agent [{arg1}] 已删除。{RESET}")
        else:
            print(f"{RED}Agent [{arg1}] 不存在。{RESET}")
    return False



def _cmd_agent_show(state, parts):
    from fr_cli.agent.manager import agent_exists, load_persona, load_memory, load_skills, load_agent_code
    from fr_cli.agent.workflow import load_workflow
    arg1 = parts[1] if len(parts) > 1 else ""
    if not arg1:
        return False
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
    return False



def _cmd_agent_run(state, parts):
    from fr_cli.agent.executor import run_agent
    arg1 = parts[1] if len(parts) > 1 else ""
    if not arg1:
        return False
    run_args = parts[2] if len(parts) > 2 else ""
    kwargs = {"user_input": run_args} if run_args else {}
    result, err = run_agent(arg1, state, **kwargs)
    if err:
        print(f"{RED}{err}{RESET}")
    else:
        print(f"{GREEN}{result}{RESET}")
    return False



def _cmd_agent_edit(state, parts):
    from fr_cli.agent.manager import agent_exists, save_persona, save_memory, save_skills, save_agent_code
    from fr_cli.agent.workflow import save_workflow
    arg1 = parts[1] if len(parts) > 1 else ""
    if not arg1:
        return False
    if not agent_exists(arg1):
        print(f"{RED}Agent [{arg1}] 不存在。{RESET}")
        return False
    file_type = parts[2] if len(parts) > 2 else ""
    valid_types = {"persona", "memory", "skills", "agent", "workflow"}
    if file_type not in valid_types:
        print(f"{YELLOW}用法: /agent_edit <名称> <类型>，类型: persona/memory/skills/agent/workflow{RESET}")
        return False
    print(f"{CYAN}请输入新的 {file_type} 内容（Ctrl+D 结束）:{RESET}")
    try:
        new_content = sys.stdin.read().strip()
    except (EOFError, KeyboardInterrupt):
        new_content = ""
    if not new_content:
        print(f"{YELLOW}内容为空，未保存。{RESET}")
        return False
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
    return False



def _cmd_agent_forge(state, parts):
    """从最近一次 AI 回复中提取 Python 代码块，创建为 Agent 分身。"""
    from fr_cli.agent.manager import create_agent_dir, save_agent_code, save_persona, save_skills, agent_exists
    from fr_cli.addon.plugin import extract_code
    arg1 = parts[1] if len(parts) > 1 else ""
    if not arg1:
        print(f"{YELLOW}用法: /agent_forge <名称>{RESET}")
        print(f"{DIM}  从最近一次 AI 回复中提取 Python 代码块，创建 Agent 分身。{RESET}")
        return False

    safe_name = "".join(c for c in arg1 if c.isalnum() or c == '_')
    if not safe_name:
        print(f"{RED}名称无效，仅允许字母/数字/下划线{RESET}")
        return False

    # 从历史消息中倒序查找最近包含 def run 的 Python 代码块
    code = ""
    for msg in reversed(state.messages):
        if msg.get("role") == "assistant":
            c = extract_code(msg.get("content", ""))
            if c and "def run" in c:
                code = c
                break

    if not code:
        print(f"{YELLOW}未在最近 AI 回复中找到包含 def run 的 Python 代码块。{RESET}")
        print(f"{DIM}提示：先让 AI 生成一段包含 def run(context, **kwargs) 的代码，再执行此命令。{RESET}")
        return False

    if agent_exists(safe_name):
        confirm = input(f"{YELLOW}Agent [{safe_name}] 已存在，是否覆盖? [y/N]: {RESET}").strip().lower()
        if confirm not in ("y", "yes"):
            print(f"{DIM}已取消。{RESET}")
            return False

    d = create_agent_dir(safe_name)
    save_agent_code(safe_name, code)

    print(f"{GREEN}✅ Agent [{safe_name}] 创建完成！{RESET}")
    print(f"{DIM}  路径: {d}{RESET}")
    print(f"{DIM}  运行: /agent_run {safe_name} [参数]{RESET}")
    return False



def _cmd_agent_model(state, parts):
    """
    设置/查看 Agent 专属模型配置
    用法:
      /agent_model <agent>                  — 查看该 Agent 的模型配置
      /agent_model <agent> <provider>:<model> — 设置专属模型
      /agent_model <agent> clear            — 清除专属配置
      /agent_model <agent> --key <key>      — 设置独立 API Key
    """
    from fr_cli.agent.manager import agent_exists, load_agent_config, save_agent_config
    from fr_cli.core.llm import get_provider_info, list_providers

    arg1 = parts[1] if len(parts) > 1 else ""  # agent_name
    arg2 = parts[2] if len(parts) > 2 else ""  # provider:model 或 subcommand

    if not arg1:
        print(f"{YELLOW}用法:{RESET}")
        print(f"  /agent_model <agent>                    — 查看配置")
        print(f"  /agent_model <agent> <provider>:<model> — 设置专属模型")
        print(f"  /agent_model <agent> clear              — 清除专属配置")
        print(f"  /agent_model <agent> --key <key>        — 设置独立 API Key")
        return False

    if not agent_exists(arg1):
        print(f"{RED}Agent [{arg1}] 不存在。{RESET}")
        return False

    agent_cfg = load_agent_config(arg1)

    # 处理 --key 子命令
    if arg2 == "--key":
        key = parts[3] if len(parts) > 3 else ""
        if not key:
            print(f"{RED}❌ 请提供 API Key{RESET}")
            return False
        agent_cfg["key"] = key
        save_agent_config(arg1, agent_cfg)
        print(f"{GREEN}✅ Agent [{arg1}] 独立 API Key 已更新{RESET}")
        return False

    # 处理 clear 子命令
    if arg2 == "clear":
        if agent_cfg:
            save_agent_config(arg1, {})
            print(f"{GREEN}✅ Agent [{arg1}] 专属配置已清除，恢复全局默认{RESET}")
        else:
            print(f"{DIM}Agent [{arg1}] 无专属配置{RESET}")
        return False

    # 查看模式（无 arg2）
    if not arg2:
        print(f"{CYAN}═══ Agent [{arg1}] 模型配置 ═══{RESET}")
        if agent_cfg.get("provider") and agent_cfg.get("model"):
            provider = agent_cfg["provider"]
            model = agent_cfg["model"]
            info = get_provider_info(provider)
            name = info["name"] if info else provider
            print(f"  专属提供商: {CYAN}{provider}{RESET} ({name})")
            print(f"  专属模型: {CYAN}{model}{RESET}")
            if agent_cfg.get("key"):
                raw_key = agent_cfg["key"]
                key_display = raw_key[:8] + "****" if len(raw_key) > 8 else raw_key
                print(f"  独立 Key: {DIM}{key_display}{RESET}")
        else:
            print(f"  {DIM}使用全局默认: [{state.provider}] {state.model_name}{RESET}")
        print(f"\n{DIM}可用提供商:{RESET}")
        for p in list_providers():
            print(f"  {CYAN}{p['id']}{RESET} — {p['name']} {DIM}(默认: {p['default_model']}){RESET}")
        return False

    # 设置模式：解析 provider:model
    if ":" in arg2:
        provider_id, model_name = arg2.split(":", 1)
    else:
        # 仅提供模型名，保持当前 provider
        provider_id = state.provider
        model_name = arg2

    provider_id = provider_id.strip()
    model_name = model_name.strip()

    if not get_provider_info(provider_id):
        print(f"{RED}❌ 无效提供商: {provider_id}{RESET}")
        print(f"{DIM}可用提供商: {', '.join([p['id'] for p in list_providers()])}{RESET}")
        return False

    if not model_name:
        print(f"{RED}❌ 模型名称不能为空{RESET}")
        return False

    agent_cfg["provider"] = provider_id
    agent_cfg["model"] = model_name
    save_agent_config(arg1, agent_cfg)
    print(f"{GREEN}✅ Agent [{arg1}] 专属模型已设置: [{provider_id}] {model_name}{RESET}")
    return False


