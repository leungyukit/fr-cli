"""
项目记忆自动加载 —— 类似 CLAUDE.md / AGENTS.md

启动时自动扫描当前目录(或向上回溯),加载项目级说明文档,
注入到 system prompt,让 AI 理解项目背景。

搜索优先级(从 cwd 开始逐级向上):
  1. .frcli.md
  2. AGENTS.md
  3. CLAUDE.md
  4. .github/AGENTS.md

最多回溯到 git root(如果存在)或最多 5 层。
"""
import os
from pathlib import Path
from typing import List, Optional, Tuple


MAX_DEPTH = 5
MAX_TOTAL_CHARS = 16000  # 防止 prompt 爆炸


def _is_git_root(path: Path) -> bool:
    """判断是否是 git 仓库根目录"""
    return (path / ".git").exists()


def _find_git_root(start: Path) -> Optional[Path]:
    """向上回溯找 git root"""
    current = start.resolve()
    for _ in range(MAX_DEPTH + 1):
        if _is_git_root(current):
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent
    return None


def find_project_memory_files(cwd: Optional[Path] = None) -> List[Tuple[Path, str]]:
    """从 cwd 开始向上找项目记忆文件

    Returns:
        [(file_path, content), ...] 按优先级顺序
    """
    if cwd is None:
        cwd = Path.cwd()

    start = cwd.resolve()
    # 确定搜索边界:git root(若有)或回溯 MAX_DEPTH 层
    git_root = _find_git_root(start)
    if git_root is not None:
        # 从 cwd 到 git_root 之间搜索
        search_roots = []
        current = start
        search_roots.append(current)
        while current != git_root and current.parent != current:
            current = current.parent
            search_roots.append(current)
    else:
        # 回溯 MAX_DEPTH 层
        search_roots = []
        current = start
        for _ in range(MAX_DEPTH + 1):
            search_roots.append(current)
            parent = current.parent
            if parent == current:
                break
            current = parent

    filenames = [".frcli.md", "AGENTS.md", "CLAUDE.md", ".github/AGENTS.md"]
    results = []
    seen_paths = set()

    for root in search_roots:
        for fn in filenames:
            fpath = root / fn
            if fpath in seen_paths:
                continue
            if fpath.exists() and fpath.is_file():
                try:
                    content = fpath.read_text(encoding="utf-8", errors="ignore")
                    if content.strip():
                        results.append((fpath, content))
                        seen_paths.add(fpath)
                except Exception:
                    pass
        # 找 .github/AGENTS.md 的特殊情况
        gh_path = root / ".github" / "AGENTS.md"
        if gh_path.exists() and gh_path not in seen_paths:
            try:
                content = gh_path.read_text(encoding="utf-8", errors="ignore")
                if content.strip():
                    results.append((gh_path, content))
                    seen_paths.add(gh_path)
            except Exception:
                pass

    return results


def build_project_memory_section(cwd: Optional[Path] = None) -> str:
    """构建注入到 system prompt 的项目记忆字符串

    Returns:
        空字符串(没找到) 或 带标题的拼接内容
    """
    files = find_project_memory_files(cwd)
    if not files:
        return ""

    parts = ["[Project Memory]\n"]
    parts.append("以下项目记忆由 fr-cli 自动从 .frcli.md / AGENTS.md / CLAUDE.md 加载。\n")
    parts.append("这些是你的项目上下文,请始终遵守。\n\n")

    total_chars = 0
    for fpath, content in files:
        rel = fpath.name
        if fpath.parent != Path.cwd():
            # 显示相对路径
            try:
                rel = str(fpath.relative_to(Path.cwd()))
            except ValueError:
                rel = str(fpath)
        # 截断单个文件避免 prompt 爆炸
        if len(content) > 4000:
            content = content[:4000] + f"\n\n... (truncated, see {rel} for full content) ..."

        section = f"--- {rel} ---\n{content}\n\n"
        if total_chars + len(section) > MAX_TOTAL_CHARS:
            parts.append(f"... ({len(files) - len(parts) + 1} more files truncated)\n")
            break
        parts.append(section)
        total_chars += len(section)

    return "".join(parts)


def should_inject_memory(cwd: Optional[Path] = None) -> bool:
    """判断是否应该注入项目记忆(找到了至少一个文件)"""
    files = find_project_memory_files(cwd)
    return len(files) > 0