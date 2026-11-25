"""
REPL 命令：/agent_team —— Agent Team 协作小组开关

用法:
    /agent_team on      开启（普通对话自动走「拆解 → 多成员并行 → 聚合」）
    /agent_team off     关闭（恢复普通单模型对话）
    /agent_team         查看当前状态与可用成员
    /agent_team run <任务>   一次性跑一轮团队协作（不改变开关状态）
"""
from fr_cli.ui.ui import CYAN, DIM, GREEN, RED, RESET, YELLOW
from fr_cli.ui.output import bullet, header, info, success, warning


def _cmd_agent_team(state, parts):
    """Agent Team 开关与状态"""
    from fr_cli.agent.team import (
        AgentTeam,
        is_team_enabled,
        set_team_enabled,
    )

    arg1 = (parts[1] if len(parts) > 1 else "").strip().lower()

    # ---- /agent_team run <任务>：一次性协作，不改变开关 ----
    if arg1 == "run":
        task = " ".join(parts[2:]).strip()
        if not task:
            print(f"{YELLOW}用法: /agent_team run <任务描述>{RESET}")
            return False
        info("团队协作中 —— 正在拆解任务…")
        result = AgentTeam(state).run(task)
        if result.is_fail():
            print(f"{RED}[x] 团队协作失败: {result.error}{RESET}")
            return False
        payload = result.unwrap() or {}
        header("任务拆解")
        bullet([
            f"{p.get('member')} — {p.get('title')}"
            for p in (payload.get("plan") or [])
        ])
        failed = [r for r in (payload.get("results") or []) if not r.get("ok")]
        if failed:
            warning(
                f"{len(failed)} 个成员未完成",
                reason="; ".join(
                    f"{r.get('member')}: {r.get('error')}" for r in failed
                ),
            )
        print()
        print(payload.get("answer") or "")
        print()
        return False

    # ---- /agent_team on|off ----
    if arg1 in ("on", "1", "true", "enable", "enabled"):
        if is_team_enabled(state):
            print(f"{DIM}Agent Team 已经是开启状态。{RESET}")
            return False
        if set_team_enabled(state, True):
            success("Agent Team 已开启")
            print(f"{DIM}  普通对话将自动拆解任务，由多个成员并行完成后再汇总。{RESET}")
            _print_members(state)
        else:
            print(f"{RED}[x] 无法写入配置（state 缺少 cfg）。{RESET}")
        return False

    if arg1 in ("off", "0", "false", "disable", "disabled"):
        if not is_team_enabled(state):
            print(f"{DIM}Agent Team 已经是关闭状态。{RESET}")
            return False
        if set_team_enabled(state, False):
            success("Agent Team 已关闭")
            print(f"{DIM}  恢复普通单模型对话。{RESET}")
        else:
            print(f"{RED}[x] 无法写入配置（state 缺少 cfg）。{RESET}")
        return False

    if arg1:
        print(f"{YELLOW}用法: /agent_team on | /agent_team off | /agent_team run <任务>{RESET}")
        return False

    # ---- 无参数：查看状态 ----
    enabled = is_team_enabled(state)
    status = f"{GREEN}已开启{RESET}" if enabled else f"{DIM}已关闭{RESET}"
    print(f"{CYAN}Agent Team: {status}{RESET}")
    if enabled:
        print(f"{DIM}  普通对话会自动拆解任务 → 多成员并行 → 汇总。{RESET}")
        print(f"{DIM}  用 /agent_team off 关闭。{RESET}")
    _print_members(state)
    return False


def _print_members(state):
    """列出当前可指派的团队成员"""
    from fr_cli.agent.team import discover_members

    members = discover_members(state)
    header("可用成员")
    for m in members:
        kind = m.get("kind", "")
        print(f"  {CYAN}{m['name']}{RESET} {DIM}[{kind}] {m.get('desc', '')}{RESET}")
    print(f"{DIM}  共 {len(members)} 位 —— 规划器只会从中挑选。{RESET}")
