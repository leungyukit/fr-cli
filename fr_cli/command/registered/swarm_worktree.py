"""
多 Agent 共享 Worktree 工具:
- swarm_worktree_create: 创建群组(N 个 worktree,每个 agent 一个)
- swarm_worktree_merge: 合并群组到目标分支
- swarm_worktree_discard: 丢弃群组
- swarm_worktree_list: 列出群组
"""
from fr_cli.command.registry import register
from fr_cli.core.result import Result


@register(
    name="swarm_worktree_create",
    triggers=["蜂群 worktree", "swarm worktree", "群组 worktree"],
    description="为多个 agent 各创建独立 worktree(用于并行协作)",
    params={"prefix": str, "agents": list, "base": str, "repo": str},
    aliases=["/swarm_wt_new"],
)
def _register_swarm_wt_create(deps, **kwargs):
    import os
    prefix = kwargs.get("prefix") or f"swarm-{int(__import__('time').time())}"
    agents_raw = kwargs.get("agents") or ""
    base = kwargs.get("base") or "master"
    repo = kwargs.get("repo") or None

    # agents 可能是 list 或 str
    if isinstance(agents_raw, list):
        agents = [a.strip() for a in agents_raw if a.strip()]
    else:
        agents = [a.strip() for a in str(agents_raw).split(",") if a.strip()]

    if not agents:
        return Result.fail("需要提供 agents(逗号分隔,如 coder,reviewer)")

    # 默认 repo = vfs cwd
    if not repo:
        repo = deps.vfs.cwd if (deps.vfs and getattr(deps.vfs, "cwd", None)) else os.getcwd()

    from fr_cli.weapon.worktree_group import create_worktree_group, format_group

    result = create_worktree_group(repo, prefix, agents, base_branch=base)
    if not result["ok"]:
        return Result.fail(result.get("error", "群组创建失败"))

    group_id = result["group_id"]
    text = format_group(group_id, "zh")
    if result.get("errors"):
        text += f"\n\n⚠️ 部分失败: {result['errors']}"
    text += "\n\n下一步:\n"
    text += f"  每个 agent 在自己的 worktree 工作(cd {result['worktrees'][0]['path']} 等)\n"
    text += f"  /swarm_wt_merge {group_id}  合并到 {base}\n"
    text += f"  /swarm_wt_discard {group_id}  丢弃"
    return Result.ok(text)


@register(
    name="swarm_worktree_merge",
    triggers=["合并蜂群", "merge swarm worktree"],
    description="合并蜂群 worktree 群组到目标分支",
    params={"group_id": str, "target": str, "squash": bool},
    aliases=["/swarm_wt_merge"],
)
def _register_swarm_wt_merge(deps, **kwargs):
    group_id = kwargs.get("group_id") or ""
    target = kwargs.get("target") or "master"
    squash = bool(kwargs.get("squash", False))

    if not group_id:
        return Result.fail("需要提供 group_id")

    from fr_cli.weapon.worktree_group import merge_group
    result = merge_group(group_id, target_branch=target, squash=squash)
    if not result["ok"]:
        err_text = "\n".join(
            f"  ❌ {e['branch']}: {e['error']}"
            for e in result.get("errors", [])
        )
        return Result.fail(f"合并失败:\n{err_text}")

    text = "✅ 蜂群合并成功:\n"
    text += f"  合并 {len(result['merged'])} 个分支到 {target}\n"
    for m in result["merged"]:
        text += f"    ✅ {m['branch']} ({m['agent']})\n"
    if result["deleted"]:
        text += f"  删除 {len(result['deleted'])} 个 worktree\n"
    return Result.ok(text)


@register(
    name="swarm_worktree_discard",
    triggers=["丢弃蜂群", "discard swarm worktree"],
    description="丢弃蜂群 worktree 群组(不 merge)",
    params={"group_id": str},
    aliases=["/swarm_wt_discard"],
)
def _register_swarm_wt_discard(deps, **kwargs):
    group_id = kwargs.get("group_id") or ""
    if not group_id:
        return Result.fail("需要提供 group_id")

    from fr_cli.weapon.worktree_group import discard_group
    result = discard_group(group_id)
    if not result["ok"]:
        return Result.fail("丢弃失败")

    text = "🗑️ 蜂群已丢弃:\n"
    text += f"  删除 {len(result['deleted'])} 个 worktree\n"
    for p in result["deleted"]:
        text += f"    ✅ {p}\n"
    if result.get("errors"):
        text += "\n⚠️ 部分失败:\n"
        for e in result["errors"]:
            text += f"  ❌ {e['path']}: {e['error']}\n"
    return Result.ok(text)


@register(
    name="swarm_worktree_list",
    triggers=["蜂群列表", "swarm groups"],
    description="列出所有蜂群 worktree 群组",
    params={},
    aliases=["/swarm_wt_list"],
)
def _register_swarm_wt_list(deps, **kwargs):
    from fr_cli.weapon.worktree_group import list_groups

    groups = list_groups()
    if not groups:
        return Result.ok("🐝 没有活跃的蜂群群组")

    lines = [f"🐝 蜂群 Worktree 群组 ({len(groups)}):"]
    for g in groups:
        lines.append(f"\n  [{g['group_id']}] {g.get('status', '?')}")
        lines.append(f"    仓库: {g['main_repo']}")
        lines.append(f"    前缀: {g['prefix']}")
        lines.append(f"    Worktrees: {len(g['worktrees'])}")
        lines.append(f"    详情: /swarm_wt_show {g['group_id']}")
    return Result.ok("\n".join(lines))
