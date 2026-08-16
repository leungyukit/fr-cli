"""
/help 重新设计(发现机制)测试
"""
from unittest.mock import MagicMock


# ---------- _NEW_COMMANDS 数据完整性 ----------

class TestNewCommandsRegistry:
    """_NEW_COMMANDS 列表本身质量检查"""

    def test_not_empty(self):
        from fr_cli.repl.commands._common import _NEW_COMMANDS
        assert len(_NEW_COMMANDS) >= 3

    def test_all_entries_have_required_fields(self):
        from fr_cli.repl.commands._common import _NEW_COMMANDS
        for entry in _NEW_COMMANDS:
            assert len(entry) == 3, f"entry 应有 3 字段: {entry}"
            cmd, desc, badge = entry
            assert cmd.startswith("/"), f"cmd 必须以 / 开头: {cmd}"
            assert desc, f"desc 不能空: {cmd}"
            assert badge, f"badge 不能空: {cmd}"

    def test_no_duplicate_commands(self):
        from fr_cli.repl.commands._common import _NEW_COMMANDS
        cmds = [e[0] for e in _NEW_COMMANDS]
        duplicates = [c for c in cmds if cmds.count(c) > 1]
        assert not duplicates, f"重复命令: {set(duplicates)}"

    def test_key_recent_features_present(self):
        """最近 6 个月加的关键命令都在列表里"""
        from fr_cli.repl.commands._common import _NEW_COMMANDS
        cmds = [e[0] for e in _NEW_COMMANDS]
        # insight 整套
        assert "/insight" in cmds
        assert "/insight extract" in cmds
        # competitor_gaps 整套
        assert "/competitor_gaps" in cmds
        # dream(主控相关)
        assert "/dream" in cmds


# ---------- _print_new_commands 输出 ----------

class TestPrintNewCommands:
    """_print_new_commands 输出格式"""

    def test_chinese_output_includes_title_and_commands(self, capsys):
        from fr_cli.repl.commands._common import _print_new_commands
        state = MagicMock(lang="zh")
        _print_new_commands(state, "zh")
        out = capsys.readouterr().out
        assert "最近新功能" in out or "Recent" in out
        # 至少包含一个 /insight
        assert "/insight" in out
        # 包含 badge
        assert "🆕" in out
        # 包含使用提示
        assert "/help new" in out

    def test_english_output(self, capsys):
        from fr_cli.repl.commands._common import _print_new_commands
        state = MagicMock(lang="en")
        _print_new_commands(state, "en")
        out = capsys.readouterr().out
        assert "Recent" in out
        assert "/insight" in out

    def test_output_starts_with_newline_for_breathing_room(self, capsys):
        from fr_cli.repl.commands._common import _print_new_commands
        state = MagicMock(lang="zh")
        _print_new_commands(state, "zh")
        out = capsys.readouterr().out
        # 输出前有空行,让"新功能"区在视觉上分隔
        assert out.startswith("\n") or out == ""


# ---------- /help <command> 精确查询 ----------

class TestHelpCommandDetail:
    """_print_command_detail 单命令详细帮助"""

    def test_known_command_shows_brief(self, capsys):
        from fr_cli.repl.commands._common import _print_command_detail
        state = MagicMock(lang="zh")
        _print_command_detail(state, "/insight", "zh")
        out = capsys.readouterr().out
        assert "/insight" in out
        assert "选品洞察" in out or "爆款" in out

    def test_unknown_command_falls_back_to_handler_docstring(self, capsys):
        """_COMMAND_BRIEF 没有时,试 handler.__doc__"""
        from fr_cli.repl.commands._common import _print_command_detail
        state = MagicMock(lang="zh")
        # /master 是 COMMAND_ROUTES 里的,_COMMAND_BRIEF 里也有,会走 brief 分支
        # 改成不存在的命令测试 fallback
        _print_command_detail(state, "/__nonexistent__", "zh")
        out = capsys.readouterr().out
        # 兜底文案
        assert "/__nonexistent__" in out

    def test_chinese_vs_english(self, capsys):
        from fr_cli.repl.commands._common import _print_command_detail
        # 同一命令,zh 和 en 输出都包含命令名
        for lang in ["zh", "en"]:
            _print_command_detail(MagicMock(), "/insight", lang)
            out = capsys.readouterr().out
            assert "/insight" in out


# ---------- /help 整体流程 ----------

class TestHelpFlow:
    """_print_help 各分支路径"""

    def test_default_help_includes_new_section(self, capsys):
        """默认 /help 输出顶部包含新功能区"""
        from fr_cli.repl.commands._common import _print_help
        state = MagicMock(lang="zh", provider="zhipu", display_model="glm-4-flash")
        _print_help(state, "")
        out = capsys.readouterr().out
        # 顶部"新功能"区在分类命令之前
        assert "新功能" in out
        # 整体包含常见的分类命令
        assert "/model" in out
        # 包含使用提示
        assert "/help" in out

    def test_help_new_topic_only_shows_new_section(self, capsys):
        """`/help new` 只显示新功能区,不显示完整命令表"""
        from fr_cli.repl.commands._common import _print_help
        state = MagicMock(lang="zh", provider="zhipu", display_model="glm-4-flash")
        _print_help(state, "new")
        out = capsys.readouterr().out
        assert "新功能" in out
        # 不应该包含完整命令表(否则 /help new 失去意义)
        # /model 会在很多地方出现,但完整命令表有很多 "/dir", "/append" 之类
        # /help new 应该只显示 _NEW_COMMANDS
        # 简单检查:不出现 "/dir" 之类的非新功能命令
        assert "/dir" not in out

    def test_help_with_exact_command_routes_to_detail(self, capsys):
        """`/help /insight` 走精确命令查询分支"""
        from fr_cli.repl.commands._common import _print_help
        state = MagicMock(lang="zh", provider="zhipu", display_model="glm-4-flash")
        _print_help(state, "/insight")
        out = capsys.readouterr().out
        # 不应该进入默认长输出
        # 简化检查:不在完整命令表中
        assert "/dir" not in out
        # 包含 /insight 说明
        assert "选品" in out or "insight" in out.lower()

    def test_help_with_unknown_command_falls_back_to_default(self, capsys):
        """`/help __unknown__` 走默认帮助(因为不是 / 开头的精确命令)"""
        from fr_cli.repl.commands._common import _print_help
        state = MagicMock(lang="zh", provider="zhipu", display_model="glm-4-flash")
        _print_help(state, "__unknown__")
        out = capsys.readouterr().out
        # 进入默认路径,显示分类命令
        assert "/model" in out

    def test_help_all_shows_everything(self, capsys):
        """`/help all` 显示所有分类详情"""
        from fr_cli.repl.commands._common import _print_help
        state = MagicMock(lang="zh", provider="zhipu", display_model="glm-4-flash")
        _print_help(state, "all")
        out = capsys.readouterr().out
        # help_detail_config 等
        # 至少包含某个分类的字串
        assert len(out) > 100  # 完整输出应该比较长

    def test_help_topic_category_still_works(self, capsys):
        """`/help config` 等分类 topic 仍然工作(向后兼容)"""
        from fr_cli.repl.commands._common import _print_help
        state = MagicMock(lang="zh", provider="zhipu", display_model="glm-4-flash")
        _print_help(state, "config")
        out = capsys.readouterr().out
        # config 分类帮助应该出现(具体内容由 i18n 控制)
        assert len(out) > 0
