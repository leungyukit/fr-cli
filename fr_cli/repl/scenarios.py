"""
快捷场景命令 —— 开发者日常高频操作的"一键 AI"

覆盖：
- /commit：自动 git diff → AI 生成 commit message → 确认 → commit
- /pr：当前分支 vs main → AI 生成 PR 描述
- /review：调 coding_helper 走 code review
- /daily：写日报模板（可选）
"""
import subprocess
import shlex
from typing import Optional, Tuple, List


# ==================== Git 工具函数 ====================

def _run_git(*args, cwd: Optional[str] = None) -> Tuple[bool, str]:
    """运行 git 命令，返回 (ok, output)"""
    try:
        result = subprocess.run(
            ["git"] + list(args),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    except subprocess.TimeoutExpired:
        return False, "git 命令超时（15s）"
    except FileNotFoundError:
        return False, "git 未安装"
    except Exception as e:
        return False, f"git 错误: {e}"


def _is_git_repo() -> bool:
    ok, _ = _run_git("rev-parse", "--is-inside-work-tree")
    return ok


def _get_staged_diff() -> str:
    """获取已暂存的 diff（staged changes）"""
    ok, diff = _run_git("diff", "--staged")
    if not ok or not diff:
        return ""
    return diff[:5000]  # 截断


def _get_unstaged_diff() -> str:
    """获取未暂存的 diff"""
    ok, diff = _run_git("diff")
    if not ok or not diff:
        return ""
    return diff[:5000]


def _get_status() -> str:
    """获取 git status 简写"""
    ok, status = _run_git("status", "--short")
    return status if ok else ""


def _get_current_branch() -> str:
    ok, branch = _run_git("branch", "--show-current")
    return branch if ok else ""


def _get_default_branch() -> str:
    """尝试获取默认分支（main / master / dev）"""
    for branch in ("main", "master", "develop", "dev"):
        ok, _ = _run_git("rev-parse", "--verify", f"origin/{branch}")
        if ok:
            return branch
    return "main"


def _get_diff_against(branch: str) -> str:
    """获取当前分支 vs 指定分支的 diff"""
    ok, diff = _run_git("diff", f"origin/{branch}...HEAD")
    if not ok or not diff:
        return ""
    return diff[:8000]


# ==================== /commit ====================

def scenario_commit(state, args: List[str], prompt) -> str:
    """/commit 快捷场景"""
    from fr_cli.ui.ui import GREEN, RED, YELLOW, CYAN, DIM, RESET

    if not _is_git_repo():
        return f"{RED}❌ 当前目录不是 git 仓库{RESET}\n   {DIM}💡 cd 到项目根目录再试{RESET}"

    staged = _get_staged_diff()
    unstaged = _get_unstaged_diff()
    status = _get_status()

    if not staged and not unstaged:
        return f"{YELLOW}⚠️ 没有需要提交的改动{RESET}"

    # 1. 如果有未暂存的改动，提示暂存
    if not staged and unstaged:
        print(f"{CYAN}📦 检测到未暂存的改动，自动 stage 所有修改...{RESET}")
        ok, out = _run_git("add", "-u")
        if not ok:
            return f"{RED}❌ git add 失败: {out}{RESET}"
        staged = _get_staged_diff()

    if not staged:
        return f"{YELLOW}⚠️ 没有 staged 改动（可能只有未跟踪文件，git add 后再试）{RESET}"

    # 2. 让 AI 生成 commit message
    files_info = status or "(no status)"
    commit_prompt = (
        f"请根据以下 git diff 生成一个简洁的 commit message。\n\n"
        f"【要求】\n"
        f"- 使用 conventional commit 格式（feat:/fix:/refactor:/docs:/chore: 等）\n"
        f"- 中文，50 字内标题，详细说明在 body\n"
        f"- 不要加任何解释，直接输出 commit message 本身（不要代码块标记）\n\n"
        f"【改动文件】\n{files_info[:500]}\n\n"
        f"【diff】\n{staged[:3000]}"
    )

    print(f"{CYAN}🤖 正在生成 commit message...{RESET}")
    prompt.set_busy(True)
    try:
        from fr_cli.core.stream import stream_cnt
        full_text = ""
        full_text, _, _, _ = stream_cnt(state.client, state.model_name,
            [{"role": "user", "content": commit_prompt}],
            state.lang, max_tokens=512,
        )
    except Exception as e:
        from fr_cli.core.errors import friendly_print
        return f"{RED}{friendly_print(e)}{RESET}"
    finally:
        prompt.set_busy(False)

    # 清理 AI 输出（去掉 markdown 代码块标记）
    commit_msg = full_text.strip()
    if commit_msg.startswith("```"):
        lines = commit_msg.split("\n")
        commit_msg = "\n".join(lines[1:]) if len(lines) > 1 else commit_msg
        if commit_msg.endswith("```"):
            commit_msg = commit_msg[:-3].strip()

    print(f"\n{GREEN}📝 生成的 commit message:{RESET}\n")
    print(f"  {DIM}─" * 30 + f"{RESET}")
    for line in commit_msg.split("\n"):
        print(f"  {line}")
    print(f"  {DIM}─" * 30 + f"{RESET}\n")

    # 3. 用户确认
    confirm = prompt.confirm("确认提交?", default=True)
    if not confirm:
        # 允许用户编辑
        edited = prompt._session.prompt(
            FormattedText([("class:indicator", "  ✏️  编辑 commit msg (回车取消): ")]),
            default=commit_msg,
        ) if prompt._session else commit_msg
        if not edited or not edited.strip():
            return f"{YELLOW}已取消{RESET}"
        commit_msg = edited

    # 4. 执行 commit
    # 用 -m 提交，避免 shell 注入
    ok, out = _run_git("commit", "-m", commit_msg)
    if not ok:
        return f"{RED}❌ git commit 失败: {out}{RESET}"

    print(f"{GREEN}✅ 提交成功!{RESET}")
    # 显示简要 diff
    ok, show = _run_git("log", "-1", "--oneline")
    if ok:
        print(f"  {DIM}{show}{RESET}")
    return ""


# ==================== /pr ====================

def scenario_pr(state, args: List[str], prompt) -> str:
    """/pr 快捷场景：当前分支 vs main → AI 生成 PR 描述"""
    from fr_cli.ui.ui import GREEN, RED, YELLOW, CYAN, DIM, RESET

    if not _is_git_repo():
        return f"{RED}❌ 当前目录不是 git 仓库{RESET}"

    branch = _get_current_branch()
    if not branch or branch in ("main", "master"):
        return f"{YELLOW}⚠️ 当前在默认分支 ({branch})，没有 PR 可生成{RESET}"

    default_branch = _get_default_branch()
    diff = _get_diff_against(default_branch)

    if not diff:
        return f"{YELLOW}⚠️ 当前分支与 origin/{default_branch} 没有差异{RESET}\n   {DIM}💡 先 git push 再来{RESET}"

    # 让 AI 生成 PR 描述
    pr_prompt = (
        f"请根据以下 git diff 生成一个 Pull Request 描述。\n\n"
        f"【分支信息】\n"
        f"- 当前分支: {branch}\n"
        f"- 目标分支: {default_branch}\n\n"
        f"【要求格式】（Markdown）\n"
        f"## Summary\n"
        f"（1-3 句话说明这次改动的目的）\n\n"
        f"## Changes\n"
        f"（列点说明主要变更）\n\n"
        f"## Test Plan\n"
        f"（如何验证这些改动）\n\n"
        f"【diff】\n{diff[:5000]}\n\n"
        f"只输出 Markdown 内容，不要任何额外解释。"
    )

    print(f"{CYAN}🤖 正在生成 PR 描述...{RESET}")
    prompt.set_busy(True)
    try:
        from fr_cli.core.stream import stream_cnt
        full_text = ""
        full_text, _, _, _ = stream_cnt(state.client, state.model_name,
            [{"role": "user", "content": pr_prompt}],
            state.lang, max_tokens=1024,
        )
    except Exception as e:
        from fr_cli.core.errors import friendly_print
        return f"{RED}{friendly_print(e)}{RESET}"
    finally:
        prompt.set_busy(False)

    # 清理
    pr_desc = full_text.strip()
    if pr_desc.startswith("```markdown"):
        pr_desc = pr_desc[len("```markdown"):].lstrip()
    if pr_desc.startswith("```"):
        pr_desc = pr_desc[3:].lstrip()
    if pr_desc.endswith("```"):
        pr_desc = pr_desc[:-3].rstrip()

    # 拼上标题
    title_prompt = f"用 30 字内中文给这个 PR 起个标题（只输出标题文字，不要 #）"
    print(f"{CYAN}🤖 正在生成 PR 标题...{RESET}")
    prompt.set_busy(True)
    try:
        from fr_cli.core.stream import stream_cnt
        title_text = ""
        for chunk in stream_cnt(
            state.client, state.model_name,
            [{"role": "user", "content": title_prompt + "\n\n" + diff[:2000]}],
            state.lang, max_tokens=128,
        ):
            title_text += chunk if isinstance(chunk, str) else ""
        title = title_text.strip().split("\n")[0].strip()
    except Exception:
        title = f"feat: {branch} 改动"
    finally:
        prompt.set_busy(False)

    print(f"\n{GREEN}📋 PR 预览:{RESET}\n")
    print(f"  {CYAN}标题:{RESET} {title}")
    print(f"  {CYAN}目标:{RESET} {default_branch} ← {branch}\n")
    print(f"  {DIM}─" * 40 + f"{RESET}")
    for line in pr_desc.split("\n"):
        print(f"  {line}")
    print(f"  {DIM}─" * 40 + f"{RESET}\n")

    # 保存到文件供用户复制
    from fr_cli.conf.paths import ROOT
    pr_file = ROOT / "pr_description.md"
    pr_file.write_text(f"# {title}\n\n{pr_desc}\n", encoding="utf-8")
    print(f"  {DIM}💾 已保存到: {pr_file}{RESET}")
    print(f"  {DIM}💡 复制到 GitHub PR 页面即可{RESET}\n")
    return ""


# ==================== /review ====================

def scenario_review(state, args: List[str], prompt) -> str:
    """/review 快捷场景：调 coding_helper 走 code review"""
    from fr_cli.ui.ui import GREEN, RED, YELLOW, CYAN, DIM, RESET

    # 1. 决定 review 范围
    scope = args[0] if args else "."
    if scope == "staged" and _is_git_repo():
        # 从 git staged 拿文件列表
        ok, files = _run_git("diff", "--name-only", "--staged")
        if not ok or not files:
            return f"{YELLOW}⚠️ 没有 staged 改动{RESET}"
        file_list = files.split("\n")
        print(f"{CYAN}🔍 Reviewing {len(file_list)} staged files...{RESET}")
    elif scope == "." or scope == "":
        # 当前目录
        from pathlib import Path
        cwd = Path(state.vfs.cwd) if state.vfs.cwd else Path.cwd()
        py_files = list(cwd.glob("**/*.py"))[:20]
        file_list = [str(f.relative_to(cwd)) for f in py_files]
        if not file_list:
            return f"{YELLOW}⚠️ 当前目录没有 .py 文件{RESET}"
        print(f"{CYAN}🔍 Reviewing {len(file_list)} Python files in {cwd}...{RESET}")
    else:
        # 单文件
        file_list = [scope]

    # 2. 让 AI 做 review
    review_prompt = (
        f"请对以下文件进行 code review。\n\n"
        f"【范围】{', '.join(file_list[:10])}\n\n"
        f"【要求】\n"
        f"- 重点关注：安全（注入/越权）、性能、错误处理、代码风格\n"
        f"- 给出具体文件 + 行号 + 问题 + 建议\n"
        f"- 用 Markdown 表格输出\n"
        f"- 如果没问题就只说一句「无明显问题」"
    )

    print(f"{CYAN}🤖 AI 正在 review...{RESET}")
    prompt.set_busy(True)
    try:
        from fr_cli.core.stream import stream_cnt
        full_text = ""
        full_text, _, _, _ = stream_cnt(state.client, state.model_name,
            [{"role": "user", "content": review_prompt}],
            state.lang, max_tokens=2048,
        )
    except Exception as e:
        from fr_cli.core.errors import friendly_print
        return f"{RED}{friendly_print(e)}{RESET}"
    finally:
        prompt.set_busy(False)

    # 清理
    review = full_text.strip()
    if review.startswith("```markdown"):
        review = review[len("```markdown"):].lstrip()
    if review.startswith("```"):
        review = review[3:].lstrip()
    if review.endswith("```"):
        review = review[:-3].rstrip()

    print(f"\n{GREEN}📋 Code Review:{RESET}\n")
    print(review)
    print()

    # 3. 保存到文件
    from fr_cli.conf.paths import ROOT
    review_file = ROOT / "code_review.md"
    review_file.write_text(review, encoding="utf-8")
    print(f"  {DIM}💾 已保存到: {review_file}{RESET}")
    return ""
