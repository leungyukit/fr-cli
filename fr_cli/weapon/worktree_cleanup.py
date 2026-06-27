"""
Worktree 自动清理 —— 空闲 N 天的 worktree 自动删除

策略:
- 扫描 ~/.fr_cli/worktree_registry.json 中的所有 worktree
- 检查每个 worktree 的最后访问时间(mtime)
- 超过空闲天数(默认 7 天)且用户确认后自动删除

注册表存储:
```json
{
  "worktrees": [
    {
      "path": "/repo/.worktrees/feat-x",
      "branch": "feat-x",
      "created_at": 1234567890,
      "last_used_at": 1234567890,
      "auto_clean": true
    }
  ]
}
```

触发:
- /worktree_clean [--days N] [--dry-run] [--force]
- 启动时(可选,config 控制)
- 定时任务(可选,通过 cron)
"""
import os
import shutil
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from fr_cli.core.store import JsonStore
from fr_cli.conf.paths import ROOT as FR_CLI_DIR


WORKTREE_REGISTRY = FR_CLI_DIR / "worktree_registry.json"
DEFAULT_IDLE_DAYS = 7


def _get_registry_path(registry_path: Optional[Path] = None) -> Path:
    """获取注册表路径(支持测试注入)"""
    return registry_path if registry_path is not None else WORKTREE_REGISTRY


def _ensure_registry(registry_path: Optional[Path] = None) -> Path:
    """确保注册表文件存在"""
    rp = _get_registry_path(registry_path)
    rp.parent.mkdir(parents=True, exist_ok=True)
    if not rp.exists():
        JsonStore(str(rp), default=dict).write({"worktrees": []})
    return rp


def register_worktree(path: str, branch: str, auto_clean: bool = True,
                      registry_path: Optional[Path] = None) -> bool:
    """注册一个 worktree 到清理列表"""
    rp = _ensure_registry(registry_path)
    try:
        data = JsonStore(str(rp), default=dict).read()
        wts = data.get("worktrees", [])

        # 移除同 path 的旧记录
        wts = [w for w in wts if w.get("path") != path]

        wts.append({
            "path": path,
            "branch": branch,
            "created_at": time.time(),
            "last_used_at": time.time(),
            "auto_clean": auto_clean,
        })
        data["worktrees"] = wts
        JsonStore(str(rp), default=dict).write(data)
        return True
    except Exception:
        return False


def unregister_worktree(path: str, registry_path: Optional[Path] = None) -> bool:
    """从注册表移除"""
    rp = _ensure_registry(registry_path)
    try:
        data = JsonStore(str(rp), default=dict).read()
        wts = data.get("worktrees", [])
        data["worktrees"] = [w for w in wts if w.get("path") != path]
        JsonStore(str(rp), default=dict).write(data)
        return True
    except Exception:
        return False


def touch_worktree(path: str, registry_path: Optional[Path] = None) -> bool:
    """更新最后使用时间(用于标记为活跃)"""
    rp = _ensure_registry(registry_path)
    try:
        data = JsonStore(str(rp), default=dict).read()
        wts = data.get("worktrees", [])
        now = time.time()
        updated = False
        for w in wts:
            if w.get("path") == path:
                w["last_used_at"] = now
                updated = True
                break
        if updated:
            data["worktrees"] = wts
            JsonStore(str(rp), default=dict).write(data)
        return updated
    except Exception:
        return False


def list_worktrees_for_cleanup(registry_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """列出所有已注册的 worktree"""
    rp = _ensure_registry(registry_path)
    try:
        data = JsonStore(str(rp), default=dict).read()
        return data.get("worktrees", [])
    except Exception:
        return []


def find_idle_worktrees(idle_days: int = DEFAULT_IDLE_DAYS,
                       registry_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """找出空闲超期的 worktree

    Returns:
        [{"path", "branch", "idle_days", "age_days", ...}]
    """
    now = time.time()
    idle_threshold = idle_days * 24 * 3600
    result = []
    for w in list_worktrees_for_cleanup(registry_path):
        if not w.get("auto_clean"):
            continue
        path = w.get("path", "")
        if not path:
            continue

        # 检查实际路径是否存在(不存在也视为可清理)
        last_used = w.get("last_used_at", w.get("created_at", now))
        idle_sec = now - last_used
        idle_days_actual = idle_sec / 86400

        # 如果路径不存在,加入清理列表(孤儿)
        if not os.path.exists(path):
            result.append({**w, "idle_days": idle_days_actual, "reason": "路径不存在"})
        elif idle_sec >= idle_threshold:
            result.append({**w, "idle_days": idle_days_actual, "reason": f"空闲 {idle_days} 天"})
    return result


def clean_idle_worktrees(idle_days: int = DEFAULT_IDLE_DAYS,
                         dry_run: bool = False,
                         force: bool = False,
                         registry_path: Optional[Path] = None) -> Dict[str, Any]:
    """清理空闲 worktree

    Args:
        idle_days: 空闲天数阈值
        dry_run: 只列出,不实际删除
        force: 强制删除(忽略 auto_clean 标记)

    Returns:
        {"cleaned": [...], "skipped": [...], "errors": [...]}
    """
    from fr_cli.weapon.worktree import worktree_remove
    wts = find_idle_worktrees(idle_days, registry_path) if not force else list_worktrees_for_cleanup(registry_path)
    if force:
        wts = [w for w in wts if w.get("auto_clean", True)]

    cleaned = []
    skipped = []
    errors = []

    for w in wts:
        path = w.get("path")
        branch = w.get("branch")

        if dry_run:
            skipped.append({"path": path, "reason": "dry-run", **w})
            continue

        try:
            # 先用 git worktree remove
            parent_cwd = _find_repo_root_for_wt(path)
            if parent_cwd and os.path.exists(path):
                r = worktree_remove(cwd=parent_cwd, path=path, force=True)
                if r["ok"]:
                    cleaned.append({"path": path, "branch": branch})
                    unregister_worktree(path, registry_path)
                else:
                    # git 失败 → 直接强删目录
                    shutil.rmtree(path, ignore_errors=True)
                    cleaned.append({"path": path, "branch": branch, "method": "rmtree"})
                    unregister_worktree(path, registry_path)
            else:
                # 找不到 repo root,直接 rmtree
                shutil.rmtree(path, ignore_errors=True)
                cleaned.append({"path": path, "branch": branch, "method": "rmtree"})
                unregister_worktree(path, registry_path)
        except Exception as e:
            errors.append({"path": path, "error": str(e)})

    return {
        "cleaned": cleaned,
        "skipped": skipped,
        "errors": errors,
        "dry_run": dry_run,
        "idle_days_threshold": idle_days,
    }


def _find_repo_root_for_wt(wt_path: str) -> Optional[str]:
    """从 worktree 路径找主仓库的 cwd

    worktree 路径形如: <main_repo>/.worktrees/<branch>
    """
    p = Path(wt_path)
    # 向上两级:.worktrees/branch → .worktrees → main_repo
    if p.parent.name == ".worktrees":
        return str(p.parent.parent)
    # 否则找 .git 文件(.git 是文件而不是目录 = 这是 worktree)
    for ancestor in p.parents:
        git_file = ancestor / ".git"
        if git_file.is_file():
            # .git 文件内容形如: gitdir: /path/to/main/.git/worktrees/<name>
            try:
                content = git_file.read_text().strip()
                if content.startswith("gitdir:"):
                    gitdir = content[len("gitdir:"):].strip()
                    # /main/.git/worktrees/feat-x → /main
                    parts = Path(gitdir).parts
                    if "worktrees" in parts:
                        idx = parts.index("worktrees")
                        main_repo = str(Path(*parts[:idx - 1])) if idx >= 1 else None
                        if main_repo:
                            return main_repo
            except Exception:
                pass
    return None


def format_cleanup_report(report: Dict[str, Any], lang: str = "zh") -> str:
    """格式化清理报告"""
    if lang == "zh":
        title = "🧹 Worktree 自动清理"
        cleaned_label = "已清理"
        skipped_label = "跳过"
        errors_label = "错误"
        dry_label = "预览(不实际删除)"
    else:
        title = "🧹 Worktree Cleanup"
        cleaned_label = "Cleaned"
        skipped_label = "Skipped"
        errors_label = "Errors"
        dry_label = "Preview (no actual deletion)"

    lines = [title]
    if report.get("dry_run"):
        lines.append(f"({dry_label})")
    lines.append(f"  {cleaned_label}: {len(report['cleaned'])}")
    for c in report["cleaned"]:
        method = c.get("method", "git")
        lines.append(f"    ✅ {c['path']} [{method}]")
    if report["skipped"]:
        lines.append(f"  {skipped_label}: {len(report['skipped'])}")
        for s in report["skipped"][:10]:
            lines.append(f"    ⏭️  {s['path']} ({s.get('reason', '?')})")
    if report["errors"]:
        lines.append(f"  {errors_label}: {len(report['errors'])}")
        for e in report["errors"]:
            lines.append(f"    ❌ {e['path']}: {e['error']}")
    return "\n".join(lines)
