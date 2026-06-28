"""
多 Agent 共享 Worktree —— 蜂群 + worktree 隔离

场景:
- 复杂任务需要多个 Agent 协作(代码 review / 写文档 / 写测试)
- 不同 Agent 可能在同一个 repo 工作,如果都在 main 分支会冲突
- 解决:每个 Agent 自动分到独立 worktree,结束后 merge 回主分支

策略:
- /swarm_worktree <branch_prefix> [agents...] 创建 N 个 worktree
- 每个 Agent 在自己的 worktree 里独立工作(cd 进去)
- 执行完后,用户选择:
  - merge:把所有 worktree merge 回主分支(可选自动 squash)
  - review:逐个 review,选择保留哪些
  - discard:全部丢弃
- 结果以 PR description / patch 形式汇总

存储:
- registry.json:记录所有"群组 worktree"和它们的状态
- 每个群组:group_id, prefix, agents[], main_branch, base_commit
"""
import os
import subprocess
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from fr_cli.core.store import JsonStore
from fr_cli.conf.paths import ROOT as FR_CLI_DIR


GROUP_REGISTRY = FR_CLI_DIR / "worktree_groups.json"


def _ensure_registry() -> Path:
    """确保注册表存在"""
    FR_CLI_DIR.mkdir(parents=True, exist_ok=True)
    if not GROUP_REGISTRY.exists():
        JsonStore(str(GROUP_REGISTRY), default=dict).write({"groups": {}})
    return GROUP_REGISTRY


def _run_git(args: List[str], cwd: Optional[str] = None, timeout: int = 30) -> Dict[str, Any]:
    """运行 git 命令"""
    cmd = ["git"] + args
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True,
            timeout=timeout, check=False,
        )
        return {
            "ok": proc.returncode == 0,
            "stdout": proc.stdout or "",
            "stderr": proc.stderr or "",
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "git 超时"}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e)}


def create_worktree_group(main_repo: str, prefix: str, agents: List[str],
                          base_branch: str = "master",
                          auto_clean_days: int = 7) -> Dict[str, Any]:
    """创建一组 worktree(每个 agent 一个)

    Args:
        main_repo: 主仓库路径
        prefix: 分支前缀(如 "swarm-2026-06-28-review")
        agents: agent 名列表(如 ["coder", "reviewer", "tester"])
        base_branch: 基于哪个分支创建
        auto_clean_days: 自动清理天数

    Returns:
        {"ok": bool, "group_id": str, "worktrees": [{agent, path, branch}], "error": str?}
    """
    if not agents:
        return {"ok": False, "error": "至少需要 1 个 agent"}

    # 检查主仓库
    if not _run_git(["rev-parse", "--is-inside-work-tree"], cwd=main_repo)["ok"]:
        return {"ok": False, "error": f"不是 git 仓库: {main_repo}"}

    # 生成 group_id
    group_id = f"{prefix}-{int(time.time())}"

    worktrees = []
    errors = []

    for agent in agents:
        branch = f"{prefix}/{agent}"
        path = os.path.join(main_repo, ".worktrees", agent)

        # git worktree add -b <branch> <path> <base>
        r = _run_git(["worktree", "add", "-b", branch, path, base_branch],
                     cwd=main_repo, timeout=30)
        if r["ok"]:
            # 注册到清理列表
            try:
                from fr_cli.weapon.worktree_cleanup import register_worktree
                register_worktree(path, branch, auto_clean=True)
            except Exception:
                pass
            worktrees.append({"agent": agent, "path": path, "branch": branch})
        else:
            errors.append({"agent": agent, "error": r["stderr"]})

    if not worktrees:
        return {"ok": False, "error": f"所有 worktree 创建失败: {errors}"}

    # 保存群组
    _save_group(group_id, {
        "main_repo": main_repo,
        "prefix": prefix,
        "base_branch": base_branch,
        "worktrees": worktrees,
        "created_at": time.time(),
        "auto_clean_days": auto_clean_days,
        "status": "active",
    })

    return {
        "ok": True,
        "group_id": group_id,
        "worktrees": worktrees,
        "errors": errors,
    }


def _save_group(group_id: str, group_data: Dict[str, Any]):
    """保存群组到注册表"""
    rp = _ensure_registry()
    data = JsonStore(str(rp), default=dict).read()
    groups = data.get("groups", {})
    groups[group_id] = group_data
    data["groups"] = groups
    JsonStore(str(rp), default=dict).write(data)


def get_group(group_id: str) -> Optional[Dict[str, Any]]:
    """获取群组"""
    rp = _ensure_registry()
    data = JsonStore(str(rp), default=dict).read()
    return data.get("groups", {}).get(group_id)


def list_groups() -> List[Dict[str, Any]]:
    """列出所有群组"""
    rp = _ensure_registry()
    data = JsonStore(str(rp), default=dict).read()
    groups = data.get("groups", {})
    return [
        {"group_id": gid, **gdata}
        for gid, gdata in groups.items()
    ]


def merge_group(group_id: str, target_branch: str = "master",
                squash: bool = False,
                delete_after: bool = True) -> Dict[str, Any]:
    """merge 群组所有 worktree 到目标分支

    Args:
        group_id: 群组 ID
        target_branch: 合并到哪个分支
        squash: 是否 squash(每个 agent 的 commit 合并成一个)
        delete_after: 合并后删除 worktree

    Returns:
        {"ok": bool, "merged": [...], "errors": [...], "deleted": [...]}
    """
    group = get_group(group_id)
    if not group:
        return {"ok": False, "error": f"群组不存在: {group_id}"}

    main_repo = group["main_repo"]
    merged = []
    errors = []

    # 先确保主仓库在目标分支
    cur = _run_git(["branch", "--show-current"], cwd=main_repo)
    if cur["stdout"].strip() != target_branch:
        # 尝试 checkout
        chk = _run_git(["checkout", target_branch], cwd=main_repo)
        if not chk["ok"]:
            return {"ok": False, "error": f"无法 checkout {target_branch}: {chk['stderr']}"}

    # 逐个 merge
    for wt in group["worktrees"]:
        branch = wt["branch"]
        merge_args = ["merge", "--no-ff", f"--message=Merge worktree {branch}"]
        if squash:
            merge_args.append("--squash")
        else:
            merge_args.append(f"--message=Merge worktree {branch}")
        merge_args.append(branch)

        r = _run_git(merge_args, cwd=main_repo, timeout=60)
        if r["ok"]:
            merged.append({"branch": branch, "agent": wt["agent"]})
        else:
            errors.append({"branch": branch, "agent": wt["agent"], "error": r["stderr"]})
            # 中止后续 merge(避免冲突堆积)
            _run_git(["merge", "--abort"], cwd=main_repo)

    # 删除 worktree
    deleted = []
    if delete_after and merged:
        for wt in group["worktrees"]:
            try:
                from fr_cli.weapon.worktree import worktree_remove
                r = worktree_remove(cwd=main_repo, path=wt["path"], force=True)
                if r["ok"]:
                    deleted.append(wt["path"])
            except Exception:
                pass
        # 标记群组完成
        group["status"] = "merged"
        group["merged_at"] = time.time()
        _save_group(group_id, group)

    return {
        "ok": len(errors) == 0,
        "merged": merged,
        "errors": errors,
        "deleted": deleted,
    }


def discard_group(group_id: str, delete_worktrees: bool = True) -> Dict[str, Any]:
    """丢弃群组(不 merge,只删 worktree)

    Returns:
        {"ok": bool, "deleted": [...], "errors": [...]}
    """
    group = get_group(group_id)
    if not group:
        return {"ok": False, "error": f"群组不存在: {group_id}"}

    deleted = []
    errors = []

    if delete_worktrees:
        from fr_cli.weapon.worktree import worktree_remove
        for wt in group["worktrees"]:
            r = worktree_remove(cwd=group["main_repo"], path=wt["path"], force=True)
            if r["ok"]:
                deleted.append(wt["path"])
            else:
                errors.append({"path": wt["path"], "error": r["stderr"]})

    group["status"] = "discarded"
    group["discarded_at"] = time.time()
    _save_group(group_id, group)

    return {
        "ok": len(errors) == 0,
        "deleted": deleted,
        "errors": errors,
    }


def format_group(group_id: str, lang: str = "zh") -> str:
    """格式化群组显示"""
    group = get_group(group_id)
    if not group:
        return f"群组 {group_id} 不存在"

    if lang == "zh":
        title = "🐝 蜂群 Worktree"
        status_label = "状态"
        wt_label = "Worktree"
    else:
        title = "🐝 Swarm Worktree Group"
        status_label = "Status"
        wt_label = "Worktree"

    lines = [f"{title} [{group_id}]"]
    lines.append(f"  {status_label}: {group.get('status', '?')}")
    lines.append(f"  仓库: {group['main_repo']}")
    lines.append(f"  前缀: {group['prefix']}")
    lines.append(f"  基于: {group.get('base_branch', '?')}")
    lines.append("")
    lines.append(f"  {wt_label}:")
    for wt in group["worktrees"]:
        lines.append(f"    {wt['agent']}: {wt['path']}")
        lines.append(f"      分支: {wt['branch']}")
    return "\n".join(lines)
