"""
Git 集成工具 —— 让 fr-cli 像 Claude Code 一样感知版本控制

提供工具:
- git_status: 查看 working tree 状态
- git_diff: 查看变更内容
- git_log: 查看提交历史
- git_add: 暂存文件
- git_commit: 提交变更
- git_branch: 查看/创建/切换分支
- git_show: 查看某次提交详情
"""
import os
import subprocess
import sys
from typing import List, Optional


def _run_git(args: List[str], cwd: Optional[str] = None, timeout: int = 10) -> dict:
    """运行 git 命令并返回结构化结果

    Returns:
        {"ok": bool, "stdout": str, "stderr": str, "code": int}
    """
    cmd = ["git"] + args
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "ok": proc.returncode == 0,
            "stdout": proc.stdout or "",
            "stderr": proc.stderr or "",
            "code": proc.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": f"git 命令超时({timeout}s)", "code": -1}
    except FileNotFoundError:
        return {"ok": False, "stdout": "", "stderr": "未找到 git 命令", "code": -1}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e), "code": -1}


def git_status(cwd: Optional[str] = None, short: bool = True) -> dict:
    """查看 git working tree 状态

    Args:
        cwd: 工作目录(默认当前)
        short: 是否简短输出(--short)

    Returns:
        {"ok": bool, "branch": str, "status": str, "is_repo": bool}
    """
    # 先看是否是 git 仓库
    check = _run_git(["rev-parse", "--is-inside-work-tree"], cwd=cwd)
    if not check["ok"]:
        return {"ok": False, "is_repo": False, "error": check["stderr"] or "不是 git 仓库"}

    # 分支
    branch_result = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
    branch = branch_result["stdout"].strip() or "(unknown)"

    # 状态
    args = ["status", "--short"] if short else ["status"]
    status_result = _run_git(args, cwd=cwd)
    return {
        "ok": True,
        "is_repo": True,
        "branch": branch,
        "status": status_result["stdout"].strip(),
        "raw": status_result["stdout"] if not short else None,
    }


def git_diff(cwd: Optional[str] = None, path: Optional[str] = None, staged: bool = False) -> dict:
    """查看变更内容

    Args:
        cwd: 工作目录
        path: 限定某个文件
        staged: 查看已暂存(staged)的变更,默认 working tree
    """
    args = ["diff"]
    if staged:
        args.append("--staged")
    if path:
        args.append("--")
        args.append(path)
    result = _run_git(args, cwd=cwd, timeout=15)
    return {
        "ok": result["ok"],
        "diff": result["stdout"],
        "error": result["stderr"] if not result["ok"] else None,
    }


def git_log(cwd: Optional[str] = None, limit: int = 10, oneline: bool = False) -> dict:
    """查看提交历史

    Args:
        limit: 最多返回 N 条
        oneline: 单行格式
    """
    args = ["log", f"-n{limit}"]
    if oneline:
        args.append("--oneline")
    else:
        # 详细格式: hash | author | date | subject
        args.append("--pretty=format:%h | %an | %ad | %s")
        args.append("--date=short")
    result = _run_git(args, cwd=cwd)
    return {
        "ok": result["ok"],
        "log": result["stdout"],
        "error": result["stderr"] if not result["ok"] else None,
    }


def git_add(cwd: Optional[str] = None, paths: Optional[List[str]] = None) -> dict:
    """暂存文件"""
    if not paths:
        paths = ["."]
    result = _run_git(["add"] + paths, cwd=cwd)
    return {
        "ok": result["ok"],
        "staged": paths,
        "error": result["stderr"] if not result["ok"] else None,
    }


def git_commit(cwd: Optional[str] = None, message: str = "", add_all: bool = False) -> dict:
    """提交变更

    Args:
        message: 提交信息
        add_all: 提交前 git add -A(暂存所有已 tracked 的变更)
    """
    if not message:
        return {"ok": False, "error": "提交信息不能为空"}

    if add_all:
        add_result = git_add(cwd=cwd)
        if not add_result["ok"]:
            return {"ok": False, "error": f"git add 失败: {add_result['error']}"}

    result = _run_git(["commit", "-m", message], cwd=cwd)
    return {
        "ok": result["ok"],
        "message": message,
        "output": result["stdout"],
        "error": result["stderr"] if not result["ok"] else None,
    }


def git_branch(cwd: Optional[str] = None, action: str = "list", name: Optional[str] = None) -> dict:
    """分支操作

    Args:
        action: list / create / checkout / delete
        name: 分支名(create/checkout/delete 时需要)
    """
    if action == "list":
        result = _run_git(["branch", "--list"], cwd=cwd)
        branches = [b.strip().lstrip("* ").strip() for b in result["stdout"].splitlines() if b.strip()]
        return {"ok": True, "branches": branches, "current": _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)["stdout"].strip()}
    elif action == "create":
        if not name:
            return {"ok": False, "error": "需要提供分支名 name"}
        result = _run_git(["branch", name], cwd=cwd)
        return {"ok": result["ok"], "created": name, "error": result["stderr"] if not result["ok"] else None}
    elif action == "checkout":
        if not name:
            return {"ok": False, "error": "需要提供分支名 name"}
        result = _run_git(["checkout", name], cwd=cwd)
        return {"ok": result["ok"], "checked_out": name, "error": result["stderr"] if not result["ok"] else None}
    elif action == "delete":
        if not name:
            return {"ok": False, "error": "需要提供分支名 name"}
        result = _run_git(["branch", "-d", name], cwd=cwd)
        return {"ok": result["ok"], "deleted": name, "error": result["stderr"] if not result["ok"] else None}
    else:
        return {"ok": False, "error": f"未知 action: {action}"}


def git_show(cwd: Optional[str] = None, ref: str = "HEAD") -> dict:
    """查看某次提交的详情"""
    result = _run_git(["show", "--stat", "--pretty=format:%h | %an | %ad | %s%n%n%b", "--date=short", ref], cwd=cwd)
    return {
        "ok": result["ok"],
        "output": result["stdout"],
        "error": result["stderr"] if not result["ok"] else None,
    }


def git_is_repo(cwd: Optional[str] = None) -> bool:
    """快速判断 cwd 是否是 git 仓库"""
    return _run_git(["rev-parse", "--is-inside-work-tree"], cwd=cwd)["ok"]