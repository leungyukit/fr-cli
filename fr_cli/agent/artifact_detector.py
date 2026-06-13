"""
AI 回复产物检测器 —— 统一检测插件/Agent 代码结构

提取自 core/chat.py 与 agent/master.py 的公共逻辑，
消除重复代码，保证行为一致性。
"""

from fr_cli.ui.ui import RED, GREEN, YELLOW, DIM, RESET
from fr_cli.lang.i18n import T
from fr_cli.addon.plugin import extract_code, PLUGIN_DIR


def detect_plugin_artifact(txt: str, lang: str, state) -> bool:
    """检测 AI 回复中的插件代码结构，提示用户保存。

    :param txt: AI 回复文本
    :param lang: 界面语言
    :param state: AppState 实例（需有 security 和 plugins 属性）
    :return: 是否检测到并处理了插件
    """
    if not txt or "def run(args='')" not in txt or "```python" not in txt:
        return False

    code = extract_code(txt)
    if not code or "def run" not in code or len(code) <= 50:
        return False

    try:
        pname = input(f"{YELLOW}{T('artifact_detect', lang)}{RESET}").strip()
        if not pname:
            return False

        safe_name = "".join(c for c in pname if c.isalnum() or c == '_')
        if not safe_name:
            print(f"{RED}名称无效，仅允许字母/数字/下划线{RESET}")
            return False

        if hasattr(state, 'security') and state.security:
            if not state.security.check("sec_write", f"/{safe_name}"):
                return False
        else:
            # 无安全模块时直接放行（测试环境）
            pass

        PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
        p_path = PLUGIN_DIR / f"{safe_name}.py"
        p_path.write_text(code, encoding='utf-8')
        if hasattr(state, 'plugins'):
            state.plugins[safe_name] = str(p_path)
        print(f"{GREEN}{T('ok_forged', lang, safe_name)}{RESET}")
        return True
    except EOFError:
        return False


def detect_agent_artifact(txt: str, lang: str, state) -> bool:
    """检测 AI 回复中的 Agent 分身代码结构，提示用户保存。

    :param txt: AI 回复文本
    :param lang: 界面语言
    :param state: AppState 实例（仅用于安全校验，可选）
    :return: 是否检测到并处理了 Agent
    """
    if not txt or "def run(context," not in txt or "```python" not in txt:
        return False

    code = extract_code(txt)
    if not code or "def run(context," not in code or len(code) <= 50:
        return False

    try:
        aname = input(f"{YELLOW}⚡ 检测到 Agent 分身结构，赐名 (回车放弃): {RESET}").strip()
        if not aname:
            return False

        safe_name = "".join(c for c in aname if c.isalnum() or c == '_')
        if not safe_name:
            print(f"{RED}名称无效，仅允许字母/数字/下划线{RESET}")
            return False

        from fr_cli.agent.manager import (
            create_agent_dir, save_agent_code, save_persona, save_skills, agent_exists
        )
        if agent_exists(safe_name):
            confirm = input(
                f"{YELLOW}Agent [{safe_name}] 已存在，是否覆盖? [y/N]: {RESET}"
            ).strip().lower()
            if confirm not in ("y", "yes"):
                print(f"{DIM}已取消。{RESET}")
                return False
            d = create_agent_dir(safe_name)
            save_agent_code(safe_name, code)
            print(f"{GREEN}✅ Agent [{safe_name}] 已覆盖更新。{RESET}")
            print(f"{DIM}  路径: {d}{RESET}")
        else:
            d = create_agent_dir(safe_name)
            save_agent_code(safe_name, code)
            save_persona(safe_name, f"#{safe_name}\n\n由 AI 对话创建的 Agent 分身。")
            save_skills(safe_name, "## 技能\n\n- 执行自定义 Python 逻辑\n- 入口: run(context, **kwargs)")
            print(f"{GREEN}✅ Agent [{safe_name}] 创建完成！{RESET}")
            print(f"{DIM}  路径: {d}{RESET}")
            print(f"{DIM}  运行: /agent_run {safe_name} [参数]{RESET}")
        return True
    except EOFError:
        return False
