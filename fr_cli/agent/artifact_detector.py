"""
AI 回复产物检测器 —— 统一检测插件/Agent 代码结构

提取自 core/chat.py 与 agent/master.py 的公共逻辑，
消除重复代码，保证行为一致性。
"""

from fr_cli.ui.ui import RED, GREEN, YELLOW, DIM, RESET
from fr_cli.lang.i18n import T
from fr_cli.addon.plugin import extract_code, PLUGIN_DIR


def install_plugin(name: str, code: str, state) -> tuple:
    """安装插件到插件目录。返回 (success, message)。"""
    safe_name = "".join(c for c in name if c.isalnum() or c == '_')
    if not safe_name:
        return False, "名称无效，仅允许字母/数字/下划线"
    if hasattr(state, 'security') and state.security:
        if not state.security.check("sec_write", f"/{safe_name}"):
            return False, "安全校验未通过"
    PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
    p_path = PLUGIN_DIR / f"{safe_name}.py"
    p_path.write_text(code, encoding='utf-8')
    if hasattr(state, 'plugins'):
        state.plugins[safe_name] = str(p_path)
    return True, safe_name


def install_agent(name: str, code: str, state) -> tuple:
    """安装 Agent 分身。返回 (success, message)。"""
    safe_name = "".join(c for c in name if c.isalnum() or c == '_')
    if not safe_name:
        return False, "名称无效，仅允许字母/数字/下划线"
    from fr_cli.agent.manager import (
        create_agent_dir, save_agent_code, save_persona, save_skills, agent_exists
    )
    create_agent_dir(safe_name)
    save_agent_code(safe_name, code)
    if not agent_exists(safe_name):
        save_persona(safe_name, f"#{safe_name}\n\n由 AI 对话创建的 Agent 分身。")
        save_skills(safe_name, "## 技能\n\n- 执行自定义 Python 逻辑\n- 入口: run(context, **kwargs)")
    return True, safe_name


def detect_plugin_artifact(
    txt: str, lang: str, state, interactive: bool = True, task_id: str = None
) -> bool:
    """检测 AI 回复中的插件代码结构，提示用户保存或加入审核队列。

    :param txt: AI 回复文本
    :param lang: 界面语言
    :param state: AppState 实例（需有 security 和 plugins 属性）
    :param interactive: 是否交互式询问名称；False 时进入后台审核队列
    :param task_id: 关联的 Hermes 任务 id，用于后台队列溯源
    :return: 是否检测到并处理了插件
    """
    if not txt or "def run(args='')" not in txt or "```python" not in txt:
        return False

    code = extract_code(txt)
    if not code or "def run" not in code or len(code) <= 50:
        return False

    if not interactive:
        from fr_cli.agent.review_queue import PersistentReviewQueue
        queue = PersistentReviewQueue()
        queue.add(
            artifact_type="plugin",
            code=code,
            task_id=task_id,
            metadata={"lang": lang},
        )
        print(f"{YELLOW}⚡ 后台检测到插件代码，已加入 Hermes 审核队列{RESET}")
        return True

    try:
        pname = input(f"{YELLOW}{T('artifact_detect', lang)}{RESET}").strip()
        if not pname:
            return False

        safe_name = "".join(c for c in pname if c.isalnum() or c == '_')
        if not safe_name:
            print(f"{RED}名称无效，仅允许字母/数字/下划线{RESET}")
            return False

        ok, msg = install_plugin(safe_name, code, state)
        if not ok:
            print(f"{RED}{msg}{RESET}")
            return False
        print(f"{GREEN}{T('ok_forged', lang, msg)}{RESET}")
        return True
    except EOFError:
        return False


def detect_agent_artifact(
    txt: str, lang: str, state, interactive: bool = True, task_id: str = None
) -> bool:
    """检测 AI 回复中的 Agent 分身代码结构，提示用户保存或加入审核队列。

    :param txt: AI 回复文本
    :param lang: 界面语言
    :param state: AppState 实例（仅用于安全校验，可选）
    :param interactive: 是否交互式询问名称；False 时进入后台审核队列
    :param task_id: 关联的 Hermes 任务 id，用于后台队列溯源
    :return: 是否检测到并处理了 Agent
    """
    if not txt or "def run(context," not in txt or "```python" not in txt:
        return False

    code = extract_code(txt)
    if not code or "def run(context," not in code or len(code) <= 50:
        return False

    if not interactive:
        from fr_cli.agent.review_queue import PersistentReviewQueue
        queue = PersistentReviewQueue()
        queue.add(
            artifact_type="agent",
            code=code,
            task_id=task_id,
            metadata={"lang": lang},
        )
        print(f"{YELLOW}⚡ 后台检测到 Agent 分身代码，已加入 Hermes 审核队列{RESET}")
        return True

    try:
        aname = input(f"{YELLOW}⚡ 检测到 Agent 分身结构，赐名 (回车放弃): {RESET}").strip()
        if not aname:
            return False

        safe_name = "".join(c for c in aname if c.isalnum() or c == '_')
        if not safe_name:
            print(f"{RED}名称无效，仅允许字母/数字/下划线{RESET}")
            return False

        from fr_cli.agent.manager import agent_exists
        if agent_exists(safe_name):
            confirm = input(
                f"{YELLOW}Agent [{safe_name}] 已存在，是否覆盖? [y/N]: {RESET}"
            ).strip().lower()
            if confirm not in ("y", "yes"):
                print(f"{DIM}已取消。{RESET}")
                return False
        ok, msg = install_agent(safe_name, code, state)
        if not ok:
            print(f"{RED}{msg}{RESET}")
            return False
        print(f"{GREEN}✅ Agent [{msg}] 已保存。{RESET}")
        print(f"{DIM}  运行: /agent_run {msg} [参数]{RESET}")
        return True
    except EOFError:
        return False
