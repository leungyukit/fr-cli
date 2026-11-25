"""
内置 Agent 公共工具库
提取各内置 Agent 中的重复逻辑：Markdown 清理、确认对话框、JSON 配置读写等。
"""


def strip_code_blocks(text):
    """去除 markdown 代码块标记（```language ... ```）"""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.endswith("```"):
            text = text.rsplit("\n", 1)[0]
        text = text.strip()
    return text


def confirm_execute(prompt="是否执行", default_yes=True):
    """交互式确认执行
    返回 True 表示用户确认执行，False 表示取消。
    """
    from fr_cli.ui.ui import DIM, RESET
    suffix = "[Y/n]" if default_yes else "[y/N]"
    confirm = input(f"{DIM}{prompt}? {suffix}: {RESET}").strip().lower()
    if default_yes:
        return not confirm or confirm in ("y", "yes")
    return confirm in ("y", "yes")


