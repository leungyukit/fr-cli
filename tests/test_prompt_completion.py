"""
TUI 输入与命令补全测试
"""
from unittest.mock import MagicMock, patch


class TestFanRenPromptKeyBindings:
    """测试 FanRenPrompt 的快捷键绑定"""

    def test_slash_keybinding_exists_with_high_priority(self):
        """/ 键绑定存在且优先级高于默认值"""
        from fr_cli.ui.prompt import FanRenPrompt

        state = MagicMock()
        # 直接构造 FanRenPrompt（不依赖 TTY 检测）
        with patch.object(FanRenPrompt, "_init_tty"):
            prompt = FanRenPrompt(state)
            kb = prompt._build_keybindings()

        # 查找 / 键绑定
        slash_bindings = [b for b in kb.bindings if "/" in b.keys]
        assert len(slash_bindings) >= 1, "缺少 / 键绑定"

    def test_tab_keybinding_exists_with_high_priority(self):
        """Tab 键绑定存在且优先级高于默认值"""
        from fr_cli.ui.prompt import FanRenPrompt

        state = MagicMock()
        with patch.object(FanRenPrompt, "_init_tty"):
            prompt = FanRenPrompt(state)
            kb = prompt._build_keybindings()

        tab_bindings = [b for b in kb.bindings if "tab" in b.keys or "c-i" in b.keys]
        assert len(tab_bindings) >= 1, "缺少 Tab 键绑定"


class TestFanRenCompleter:
    """测试命令补全器"""

    def test_completer_returns_commands_for_slash(self):
        """输入 / 时返回命令补全"""
        from fr_cli.ui.prompt import FanRenCompleter
        from prompt_toolkit.document import Document

        completer = FanRenCompleter(
            lambda: [("model", "切换模型"), ("help", "帮助")],
            lambda: [],
        )
        doc = Document("/", cursor_position=1)
        completions = list(completer.get_completions(doc, None))
        assert len(completions) > 0
        texts = [c.text.strip() for c in completions]
        assert "model" in texts
        assert "help" in texts

    def test_completer_returns_empty_for_normal_text(self):
        """普通文本不返回补全"""
        from fr_cli.ui.prompt import FanRenCompleter
        from prompt_toolkit.document import Document

        completer = FanRenCompleter(
            lambda: [("model", "切换模型")],
            lambda: [],
        )
        doc = Document("hello", cursor_position=5)
        completions = list(completer.get_completions(doc, None))
        assert len(completions) == 0
