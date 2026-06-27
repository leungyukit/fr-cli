"""
Git Worktree 管理 —— 隔离的并行工作环境

Git worktree 允许同一个仓库同时有多个 working copy,每个 worktree
可以独立 checkout 不同的分支,互不干扰。这让 Agent 可以在不同
worktree 里并行开发多个 feature,主目录保持干净。

概念:
- 主 worktree (main checkout):仓库根目录
- 链接 worktree (linked):从 .git/worktrees/<name> 链接到 <path>
- 每个 worktree 有独立的 working tree / index / HEAD

fr-cli 集成:
- /worktree new <branch>  创建新 worktree + cd 进去
- /worktree list           列出所有 worktree
- /worktree switch <name>  切换到指定 worktree
- /worktree remove <name>  删除 worktree(保留 branch)
- AI 工具:worktree_create / worktree_list / worktree_remove
- 主目录切换:state.vfs.cwd 跟随 worktree 路径

路径策略:
- 默认 worktree 放在 <repo>/.worktrees/<branch>
- 也可指定自定义路径
"""
import os
import subprocess
from typing import List, Optional, Dict, Any


_WORKTREE_DEFAULT_DIR = ".worktrees"


def _run_git(args: List[str], cwd: Optional[str] = None, timeout: int = 10) -> Dict[str, Any]:
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
            "code": proc.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "git 命令超时", "code": -1}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e), "code": -1}


def worktree_is_repo(cwd: Optional[str] = None) -> bool:
    """检查是否是 git 仓库"""
    return _run_git(["rev-parse", "--is-inside-work-tree"], cwd=cwd)["ok"]


def worktree_list(cwd: Optional[str] = None) -> Dict[str, Any]:
    """列出所有 worktree

    Returns:
        {"ok": bool, "worktrees": [{"path": str, "head": str, "branch": str}, ...]}
    """
    if not worktree_is_repo(cwd):
        return {"ok": False, "error": "不是 git 仓库"}

    # --porcelain 格式:每两行一个 worktree,path\nHEAD <sha> [branch]
    result = _run_git(["worktree", "list", "--porcelain"], cwd=cwd, timeout=10)
    if not result["ok"]:
        return {"ok": False, "error": result["stderr"]}

    worktrees = []
    blocks = result["stdout"].split("\n\n")
    for block in blocks:
        if not block.strip():
            continue
        wt = {"path": "", "head": "", "branch": ""}
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("worktree "):
                wt["path"] = line[len("worktree "):]
            elif line.startswith("HEAD "):
                wt["head"] = line[len("HEAD "):]
            elif line.startswith("branch "):
                wt["branch"] = line[len("branch "):].replace("refs/heads/", "")
            elif line == "bare":
                wt["bare"] = True
        worktrees.append(wt)
    return {"ok": True, "worktrees": worktrees}


def worktree_create(cwd: Optional[str] = None, branch: Optional[str] = None,
                   path: Optional[str] = None,
                   base: Optional[str] = None,
                   detach: bool = False) -> Dict[str, Any]:
    """创建新 worktree

    Args:
        cwd: 主仓库目录
        branch: 新分支名(同时也是 worktree 目录名,如果不指定 path)
        path: 自定义路径
        base: 基于哪个分支/commit 创建(默认基于当前 HEAD)
        detach: 是否 detached HEAD(不创建分支)
    """
    if not worktree_is_repo(cwd):
        return {"ok": False, "error": "不是 git 仓库"}

    # 默认路径
    if not path:
        if not branch:
            return {"ok": False, "error": "需要提供 branch 或 path"}
        path = os.path.join(cwd or os.getcwd(), _WORKTREE_DEFAULT_DIR, branch)

    # 路径必须存在父目录
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        try:
            os.makedirs(parent, exist_ok=True)
        except Exception as e:
            return {"ok": False, "error": f"创建父目录失败: {e}"}

    args = ["worktree", "add"]
    if detach:
        args.append("--detach")
    else:
        if branch:
            args.append("-b")
            args.append(branch)
    # git 语法:git worktree add [-b <branch>] <path> [<commit-ish>]
    # base 必须在 path 之后
    args.append(path)
    if base:
        args.append(base)

    result = _run_git(args, cwd=cwd, timeout=30)
    if not result["ok"]:
        return {"ok": False, "error": result["stderr"] or "git worktree add 失败"}

    return {
        "ok": True,
        "path": path,
        "branch": branch,
        "base": base,
        "bare": False,
    }


def worktree_remove(cwd: Optional[str] = None, path: Optional[str] = None,
                   force: bool = False) -> Dict[str, Any]:
    """移除 worktree

    Args:
        cwd: 任意 git worktree 目录
        path: 要移除的 worktree 路径
        force: 强制删除(即使有未提交变更)
    """
    if not path:
        return {"ok": False, "error": "需要提供 path"}

    args = ["worktree", "remove"]
    if force:
        args.append("--force")
    args.append(path)

    result = _run_git(args, cwd=cwd, timeout=15)
    if not result["ok"]:
        return {"ok": False, "error": result["stderr"] or "git worktree remove 失败"}

    return {"ok": True, "removed": path}


def worktree_prune(cwd: Optional[str] = None) -> Dict[str, Any]:
    """清理 stale worktree 引用"""
    result = _run_git(["worktree", "prune"], cwd=cwd)
    if not result["ok"]:
        return {"ok": False, "error": result["stderr"]}
    return {"ok": True}


def worktree_path_for_branch(repo_cwd: str, branch: str) -> str:
    """根据分支名推算默认 worktree 路径"""
    return os.path.join(repo_cwd, _WORKTREE_DEFAULT_DIR, branch)


def format_worktree_list(worktrees: List[Dict[str, Any]], current_cwd: Optional[str] = None) -> str:
    """格式化 worktree 列表为可读字符串"""
    if not worktrees:
        return "无 worktree"

    lines = ["Git Worktrees:"]
    for wt in worktrees:
        path = wt.get("path", "")
        branch = wt.get("branch", "(detached)")
        head = wt.get("head", "")[:8]
        marker = " ← 当前" if current_cwd and os.path.realpath(path) == os.path.realpath(current_cwd) else ""
        lines.append(f"  📁 {path}")
        lines.append(f"     分支: {branch} | HEAD: {head}{marker}")
    return "\n".join(lines)
