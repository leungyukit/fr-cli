"""
Git Worktree 工具注册
- worktree_create: 创建新 worktree + 分支
- worktree_list: 列出所有 worktree
- worktree_remove: 删除 worktree
- worktree_switch: 切换当前 cwd 到指定 worktree
"""
from fr_cli.command.registry import register
from fr_cli.core.result import Result
from fr_cli.weapon.worktree import (
    worktree_create as _worktree_create,
    worktree_list as _worktree_list,
    worktree_remove as _worktree_remove,
    format_worktree_list,
)


def _get_repo_cwd(deps):
    """获取主仓库 cwd"""
    import os
    return deps.vfs.cwd if (deps.vfs and getattr(deps.vfs, "cwd", None)) else os.getcwd()


@register(
    name="worktree_create",
    triggers=["worktree", "worktree 创建", "隔离环境"],
    description="创建 git worktree(独立 working copy,适合并行开发)",
    params={"branch": str, "path": str, "base": str},
    aliases=["/worktree_new"],
)
def _register_worktree_create(deps, **kwargs):
    branch = kwargs.get("branch") or None
    path = kwargs.get("path") or None
    base = kwargs.get("base") or None

    cwd = _get_repo_cwd(deps)
    result = _worktree_create(cwd=cwd, branch=branch, path=path, base=base)
    if not result["ok"]:
        return Result.fail(result.get("error", "worktree 创建失败"))
    return Result.ok(
        f"✅ Worktree 创建成功:\n"
        f"  路径: {result['path']}\n"
        f"  分支: {result.get('branch', '(detached)')}\n"
        f"  基于: {result.get('base', 'HEAD')}\n"
        f"\n下一步:cd 进去开始工作"
    )


@register(
    name="worktree_list",
    triggers=["worktree 列表", "列出 worktree"],
    description="列出所有 git worktree",
    params={},
    aliases=["/worktree_list"],
)
def _register_worktree_list(deps, **kwargs):
    cwd = _get_repo_cwd(deps)
    result = _worktree_list(cwd=cwd)
    if not result["ok"]:
        return Result.fail(result.get("error", "worktree 列表失败"))
    text = format_worktree_list(result["worktrees"], current_cwd=cwd)
    return Result.ok(text)


@register(
    name="worktree_remove",
    triggers=["worktree 删除", "删除 worktree"],
    description="删除 git worktree(保留分支)",
    params={"path": str, "force": bool},
    aliases=["/worktree_remove"],
)
def _register_worktree_remove(deps, **kwargs):
    path = kwargs.get("path") or None
    force = bool(kwargs.get("force", False))

    cwd = _get_repo_cwd(deps)
    result = _worktree_remove(cwd=cwd, path=path, force=force)
    if not result["ok"]:
        return Result.fail(result.get("error", "worktree 删除失败"))
    return Result.ok(f"✅ Worktree 已删除: {result['removed']}")


@register(
    name="worktree_switch",
    triggers=["切换 worktree", "switch worktree", "进入 worktree"],
    description="切换当前 cwd 到指定 worktree 路径",
    params={"path": str},
    aliases=["/worktree_switch"],
)
def _register_worktree_switch(deps, **kwargs):
    import os
    path = kwargs.get("path") or None
    if not path:
        return Result.fail("需要提供 path")

    if not os.path.exists(path):
        return Result.fail(f"路径不存在: {path}")

    # 修改 vfs.cwd(如果 vfs 支持)
    if deps.vfs:
        try:
            deps.vfs.cwd = path
            deps.vfs.cd(path, deps.lang)
            return Result.ok(f"✅ 已切换到: {path}")
        except Exception as e:
            return Result.fail(f"切换失败: {e}")
    return Result.ok(f"提示:请 cd 到 {path}")
