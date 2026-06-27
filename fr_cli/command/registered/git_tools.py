"""
注册表分组:Git 集成工具
- git_status / git_diff / git_log / git_add / git_commit / git_branch / git_show

像 Claude Code 一样在 AI 工具列表中暴露 git 能力。
"""
from fr_cli.command.registry import register
from fr_cli.weapon.git_tools import (
    git_status as _git_status,
    git_diff as _git_diff,
    git_log as _git_log,
    git_add as _git_add,
    git_commit as _git_commit,
    git_branch as _git_branch,
    git_show as _git_show,
)


@register(
    name="git_status",
    triggers=["git状态", "git status", "仓库状态", "查看变更"],
    description="查看 git working tree 状态(分支、未暂存变更)",
    params={},
    aliases=["/git_status"],
)
def _register_git_status(deps, **kwargs):
    import os
    cwd = deps.vfs.cwd if (deps.vfs and getattr(deps.vfs, "cwd", None)) else os.getcwd()
    result = _git_status(cwd=cwd)
    if not result.get("ok"):
        from fr_cli.core.result import Result
        if not result.get("is_repo"):
            return Result.fail("当前目录不是 git 仓库")
        return Result.fail(result.get("error", "git status 失败"))
    # 格式化输出
    out = f"分支: {result['branch']}\n"
    if result.get("status"):
        out += f"状态:\n{result['status']}\n"
    else:
        out += "工作区干净,无变更\n"
    from fr_cli.core.result import Result
    return Result.ok(out)


@register(
    name="git_diff",
    triggers=["git diff", "查看diff", "查看差异"],
    description="查看文件变更内容(unified diff 格式)",
    params={"path": str, "staged": bool},
    aliases=["/git_diff"],
)
def _register_git_diff(deps, **kwargs):
    import os
    cwd = deps.vfs.cwd if (deps.vfs and getattr(deps.vfs, "cwd", None)) else os.getcwd()
    path = kwargs.get("path") or None
    staged = bool(kwargs.get("staged", False))
    result = _git_diff(cwd=cwd, path=path, staged=staged)
    from fr_cli.core.result import Result
    if not result["ok"]:
        return Result.fail(result.get("error", "git diff 失败"))
    if not result["diff"]:
        return Result.ok("无变更")
    return Result.ok(result["diff"])


@register(
    name="git_log",
    triggers=["git log", "提交历史", "git history"],
    description="查看 git 提交历史(默认最近 10 条)",
    params={"limit": int, "oneline": bool},
    aliases=["/git_log"],
)
def _register_git_log(deps, **kwargs):
    import os
    cwd = deps.vfs.cwd if (deps.vfs and getattr(deps.vfs, "cwd", None)) else os.getcwd()
    try:
        limit = int(kwargs.get("limit", 10))
    except (ValueError, TypeError):
        limit = 10
    oneline = bool(kwargs.get("oneline", False))
    result = _git_log(cwd=cwd, limit=limit, oneline=oneline)
    from fr_cli.core.result import Result
    if not result["ok"]:
        return Result.fail(result.get("error", "git log 失败"))
    if not result["log"]:
        return Result.ok("暂无提交历史")
    return Result.ok(result["log"])


@register(
    name="git_add",
    triggers=["git add", "暂存", "stage"],
    description="git add 暂存文件(默认全部)",
    params={"paths": list},
    security="sec_exec",  # 写操作
    aliases=["/git_add"],
)
def _register_git_add(deps, **kwargs):
    import os
    cwd = deps.vfs.cwd if (deps.vfs and getattr(deps.vfs, "cwd", None)) else os.getcwd()
    paths = kwargs.get("paths") or None
    result = _git_add(cwd=cwd, paths=paths)
    from fr_cli.core.result import Result
    if not result["ok"]:
        return Result.fail(result.get("error", "git add 失败"))
    return Result.ok(f"已暂存: {result['staged']}")


@register(
    name="git_commit",
    triggers=["git commit", "git提交", "提交变更"],
    description="git commit 提交变更",
    params={"message": str, "add_all": bool},
    security="sec_exec",
    aliases=["/git_commit"],
)
def _register_git_commit(deps, **kwargs):
    import os
    cwd = deps.vfs.cwd if (deps.vfs and getattr(deps.vfs, "cwd", None)) else os.getcwd()
    message = kwargs.get("message", "").strip()
    add_all = bool(kwargs.get("add_all", True))
    if not message:
        return __import__("fr_cli.core.result", fromlist=["Result"]).Result.fail("提交信息不能为空")
    result = _git_commit(cwd=cwd, message=message, add_all=add_all)
    from fr_cli.core.result import Result
    if not result["ok"]:
        return Result.fail(result.get("error", "git commit 失败"))
    return Result.ok(result.get("output") or "已提交")


@register(
    name="git_branch",
    triggers=["git branch", "切换分支", "创建分支"],
    description="git 分支操作(list/create/checkout/delete)",
    params={"action": str, "name": str},
    aliases=["/git_branch"],
)
def _register_git_branch(deps, **kwargs):
    import os
    cwd = deps.vfs.cwd if (deps.vfs and getattr(deps.vfs, "cwd", None)) else os.getcwd()
    action = kwargs.get("action", "list")
    name = kwargs.get("name") or None
    result = _git_branch(cwd=cwd, action=action, name=name)
    from fr_cli.core.result import Result
    if not result["ok"]:
        return Result.fail(result.get("error", "git branch 失败"))
    if action == "list":
        out = f"当前分支: {result['current']}\n所有分支:\n"
        out += "\n".join(f"  {b}" for b in result["branches"])
        return Result.ok(out)
    return Result.ok(str(result))


@register(
    name="git_show",
    triggers=["git show", "查看提交"],
    description="查看某次 git 提交的详情(默认 HEAD)",
    params={"ref": str},
    aliases=["/git_show"],
)
def _register_git_show(deps, **kwargs):
    import os
    cwd = deps.vfs.cwd if (deps.vfs and getattr(deps.vfs, "cwd", None)) else os.getcwd()
    ref = kwargs.get("ref") or "HEAD"
    result = _git_show(cwd=cwd, ref=ref)
    from fr_cli.core.result import Result
    if not result["ok"]:
        return Result.fail(result.get("error", "git show 失败"))
    return Result.ok(result["output"])