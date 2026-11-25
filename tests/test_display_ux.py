"""
UX / 显示层改动的回归测试（v2.8.7）

覆盖本轮四组改动：
1. **颜色常量活引用** —— ``set_no_color()`` 对按值 import 的模块真正生效
2. **代码块语法高亮** —— 零依赖，关键字/字符串/注释分色
3. **长回答折叠 + Ctrl+O 展开** —— 折叠内容不丢，可找回
4. **状态栏重排** —— 左右分栏、全局优先级裁剪、上下文占用预警、工具参数
"""

import time

from fr_cli.ui import ui
from fr_cli.ui import syntax
from fr_cli.ui.markdown_stream import StreamingMarkdownRenderer
from fr_cli.ui.prompt.status import StatusState


# ===================================================================
# 1. 颜色常量活引用
# ===================================================================


class TestLiveColorConstants:

    def test_imported_constant_follows_runtime_toggle(self):
        """按值 import 的常量必须跟随 set_no_color()"""
        from fr_cli.ui.ui import RED

        original = ui.no_color()
        try:
            ui.set_no_color(False)
            assert str(RED) != ""
            ui.set_no_color(True)
            assert str(RED) == ""
            assert f"{RED}" == ""
        finally:
            ui.set_no_color(original)

    def test_combined_constant_is_also_live(self):
        """CYAN + BOLD 这种组合即使在 import 期求值也要是活的"""
        from fr_cli.ui.ui import BOLD, CYAN

        combined = CYAN + BOLD
        original = ui.no_color()
        try:
            ui.set_no_color(False)
            assert str(combined) != ""
            ui.set_no_color(True)
            assert str(combined) == ""
        finally:
            ui.set_no_color(original)

    def test_bool_and_eq_follow_state(self):
        """真值与相等判断也要跟随（markdown_stream 的 `not color` 靠它）"""
        from fr_cli.ui.ui import GREEN

        original = ui.no_color()
        try:
            ui.set_no_color(True)
            assert not GREEN
            assert GREEN == ""
            ui.set_no_color(False)
            assert GREEN
            assert GREEN != ""
        finally:
            ui.set_no_color(original)

    def test_still_is_a_str(self):
        """必须是 str 子类 —— 下游有 isinstance(x, str) / 字符串拼接"""
        from fr_cli.ui.ui import CYAN

        assert isinstance(CYAN, str)


# ===================================================================
# 2. 代码块语法高亮
# ===================================================================


class TestSyntaxHighlight:

    def test_keywords_get_color(self):
        original = ui.no_color()
        try:
            ui.set_no_color(False)
            out = syntax.highlight_code("def greet():", "python", use_color=True)
            assert "\033[" in out
            # 关键字被单独上色（前后有转义序列）
            assert "\033[" in out and "def" in out
        finally:
            ui.set_no_color(original)

    def test_no_color_returns_plain_text(self):
        """关色时必须原样返回 —— 不能拼任何转义序列"""
        out = syntax.highlight_code("def greet(): # hi", "python", use_color=False)
        assert out == "def greet(): # hi"
        assert "\033[" not in out

    def test_unsupported_language_is_plain(self):
        out = syntax.highlight_code("some text", "brainfuck", use_color=True)
        assert out == "some text"

    def test_language_alias(self):
        assert syntax.normalize_lang("py") == "python"
        assert syntax.normalize_lang("JS") == "javascript"
        assert syntax.normalize_lang("golang") == "go"
        assert syntax.normalize_lang("nope") is None

    def test_string_not_mistaken_for_comment(self):
        """字符串里的 # 不该被当成注释"""
        original = ui.no_color()
        try:
            ui.set_no_color(False)
            out = syntax.highlight_code("x = '# not a comment'", "python", use_color=True)
            # 整个引号包裹的片段是一个整体（字符串色），不是"注释 + 剩余文本"
            assert "'# not a comment'" in out
            # 注释色(DIM)不应该出现在这一行里
            dim_code = str(ui.DIM)
            assert dim_code not in out
        finally:
            ui.set_no_color(original)

    def test_renderer_applies_highlight(self):
        """渲染器的代码块路径要真的走高亮"""
        original = ui.no_color()
        try:
            ui.set_no_color(False)
            r = StreamingMarkdownRenderer(use_color=True)
            out = r.feed("```python\ndef f():\n    pass\n```\n")
            assert "\033[" in out
        finally:
            ui.set_no_color(original)


# ===================================================================
# 3. 长回答折叠 + Ctrl+O 展开
# ===================================================================


class TestCollapseRegistry:

    def test_register_peek_take(self):
        from fr_cli.core import collapse

        collapse.clear()
        collapse.register("隐藏内容", meta="测试")
        item = collapse.peek()
        assert item is not None
        assert item.text == "隐藏内容"
        assert item.meta == "测试"

        taken = collapse.take()
        assert taken.text == "隐藏内容"
        assert collapse.peek() is None

    def test_take_on_empty_returns_none(self):
        from fr_cli.core import collapse

        collapse.clear()
        assert collapse.take() is None

    def test_max_items_keeps_recent(self):
        from fr_cli.core import collapse

        collapse.clear()
        for i in range(collapse.MAX_ITEMS + 3):
            collapse.register(f"item{i}")
        assert collapse.count() == collapse.MAX_ITEMS
        assert collapse.peek().text == f"item{collapse.MAX_ITEMS + 2}"

    def test_thread_safe_under_concurrent_register(self):
        """折叠发生在后台线程，登记必须线程安全"""
        import threading

        from fr_cli.core import collapse

        collapse.clear()

        def _worker():
            for i in range(50):
                collapse.register(f"x{i}")

        threads = [threading.Thread(target=_worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert collapse.count() == collapse.MAX_ITEMS


class TestRendererFolding:

    def test_short_answer_not_folded(self):
        """正常长度的回答完全不受影响（流式体验零损失）"""
        from fr_cli.core import collapse

        collapse.clear()
        r = StreamingMarkdownRenderer(use_color=False, fold_threshold=60, fold_tail=10)
        out = "".join(r.feed(f"line {i}\n") for i in range(20))
        out += r.flush()
        assert "折叠" not in out
        assert collapse.count() == 0

    def test_long_answer_folded_with_tail(self):
        from fr_cli.core import collapse

        collapse.clear()
        r = StreamingMarkdownRenderer(use_color=False, fold_threshold=10, fold_tail=3)
        out = ""
        for i in range(30):
            out += r.feed(f"第{i}行\n")
        out += r.flush()

        assert "折叠" in out
        # 尾部保留（最后几行仍可见）
        assert "第29行" in out
        # 折叠内容进了登记表
        assert collapse.count() == 1
        item = collapse.peek()
        assert "第10行" in item.text

    def test_fold_registers_middle_only(self):
        """登记的是"没显示出来的那段"，尾部已在屏幕上，不该重复"""
        from fr_cli.core import collapse

        collapse.clear()
        r = StreamingMarkdownRenderer(use_color=False, fold_threshold=10, fold_tail=3)
        for i in range(30):
            r.feed(f"第{i}行\n")
        r.flush()
        item = collapse.peek()
        assert "第29行" not in item.text   # 尾部不重复登记
        assert "第10行" in item.text       # 中间部分在


class TestFoldResult:

    def test_fold_result_registers_hidden_lines(self):
        """命令输出折叠后，省略的内容要能找回"""
        from fr_cli.core import collapse
        from fr_cli.core.chat.helpers import fold_result

        collapse.clear()
        text = "\n".join(f"line{i}" for i in range(100))
        out = fold_result(text)
        assert "省略" in out
        assert collapse.count() == 1
        item = collapse.peek()
        assert "line20" in item.text
        assert "line0\n" not in item.text   # 头部已在屏幕上


# ===================================================================
# 4. 状态栏重排
# ===================================================================


class TestStatusBarLayout:

    def _full_state(self):
        s = StatusState()
        s.provider, s.model = "stepfun", "step-5-preview"
        s.directory = "/Users/liangyj/workspace/fr-cli"
        s.queue_depth = 2
        s.steer_pending = 1
        s.context_tokens = 3600
        s.context_limit = 4000
        s.last_response_time = 3.2
        s.last_input_tokens, s.last_output_tokens, s.last_total_tokens = 100, 200, 300
        s.mode = "react"
        s.tool_name = "read_file"
        s.tool_args = "path=README.md"
        s.tool_started = time.time() - 1.0
        return s

    def test_left_and_right_split(self):
        s = self._full_state()
        text = "".join(t for _, t in s.render(160))
        assert "stepfun/step-5-preview" in text
        assert "read_file" in text
        # 右区按展示顺序排在最后（模式在最后）
        assert text.rstrip().endswith("react")
        # 左右之间有填充空格（右区被推到最右）
        assert "│   " in text or "│  " in text

    def test_narrow_width_keeps_model_and_busy(self):
        """窄屏时先丢低优先级项，模型与忙碌状态必须保留"""
        s = self._full_state()
        text = "".join(t for _, t in s.render(40))
        assert "stepfun/step-5-preview" in text
        assert "read_file" in text
        # 低优先级的目录/时间/模式被丢掉
        assert "react" not in text

    def test_context_warn_colors(self):
        """上下文占用：≥80% 黄，≥100% 红"""
        s = StatusState()
        s.provider, s.model = "z", "m"
        s.context_tokens, s.context_limit = 3900, 4000
        assert "class:status-yellow" in [st for st, _ in s.render(80)
                                          if "上下文" in _]

        s.context_tokens = 4500
        rendered = s.render(80)
        ctx_style = [st for st, tx in rendered if "上下文" in tx]
        assert ctx_style == ["class:status-red"]

    def test_tool_args_shown(self):
        """工具执行时能看到参数摘要"""
        s = self._full_state()
        text = "".join(t for _, t in s.render(100))
        assert "path=README.md" in text

    def test_tool_args_absent_when_empty(self):
        s = StatusState()
        s.provider, s.model = "z", "m"
        s.tool_name = "ls"
        text = "".join(t for _, t in s.render(80))
        assert "ls" in text
        assert "path=" not in text

    def test_tool_source_shown(self):
        """工具执行时能看到"谁在调"（来源 agent）"""
        s = self._full_state()
        s.tool_source = "master"
        text = "".join(t for _, t in s.render(120))
        assert "[master]" in text
        assert "read_file" in text

    def test_tool_error_shown_in_red(self):
        """工具失败时状态栏显示失败原因（工具结果本身不回显给用户）"""
        s = self._full_state()
        s.tool_source = "local"
        s.tool_error = "路径超出沙盒范围"
        rendered = s.render(120)
        text = "".join(t for _, t in rendered)
        assert "路径超出沙盒范围" in text
        assert "✗" in text
        styles = [st for st, tx in rendered if "✗" in tx]
        assert styles == ["class:status-red"], f"失败原因应为红色: {styles}"

    def test_tool_error_cleared_on_success(self):
        """成功时工具字段清空，不留残影"""
        s = self._full_state()
        s.tool_error = ""
        s.tool_source = ""
        text = "".join(t for _, t in s.render(120))
        assert "✗" not in text
        assert "[" not in text, "来源前缀未清空"


# ===================================================================
# 4.5 工具来源 / 失败原因上报
# ===================================================================


class TestToolSourceReporting:

    class _FakePrompt:
        def __init__(self):
            from fr_cli.ui.prompt.status import StatusState
            self.status = StatusState()
            self.invalidated = 0

        def _invalidate(self):
            self.invalidated += 1

    class _FakeState:
        def __init__(self, prompt):
            self._prompt = prompt

    def test_start_reports_name_args_and_source(self):
        from fr_cli.command.executor_dispatch import _report_tool_start

        prompt = self._FakePrompt()
        _report_tool_start(self._FakeState(prompt), "read_file",
                           {"path": "/tmp/a.txt"}, "master")
        assert prompt.status.tool_name == "read_file"
        assert "path=/tmp/a.txt" in prompt.status.tool_args
        assert prompt.status.tool_source == "master"
        assert prompt.invalidated >= 1

    def test_end_on_success_clears_fields(self):
        from fr_cli.command.executor_dispatch import _report_tool_start, _report_tool_end

        prompt = self._FakePrompt()
        _report_tool_start(self._FakeState(prompt), "read_file", {"path": "/a"}, "master")
        _report_tool_end(prompt)
        assert prompt.status.tool_name == ""
        assert prompt.status.tool_source == ""
        assert prompt.status.tool_error == ""

    def test_end_on_failure_keeps_scene(self):
        """失败时保留工具名/参数/来源，并带上失败原因"""
        from fr_cli.command.executor_dispatch import _report_tool_start, _report_tool_end

        prompt = self._FakePrompt()
        _report_tool_start(self._FakeState(prompt), "read_file", {"path": "/a"}, "master")
        _report_tool_end(prompt, error="路径超出沙盒范围\n第二行")
        assert prompt.status.tool_name == "read_file"
        assert prompt.status.tool_source == "master"
        # 换行压平 + 截断，保证状态栏一行放得下
        assert "\n" not in prompt.status.tool_error
        assert "路径超出沙盒范围" in prompt.status.tool_error

    def test_source_scope_propagates_to_nested_calls(self):
        """tool_source_scope 里的 invoke_tool 能拿到来源"""
        from fr_cli.command.executor_dispatch import (
            _TOOL_SOURCE, tool_source_scope,
        )

        assert _TOOL_SOURCE.get() == ""
        with tool_source_scope("local"):
            assert _TOOL_SOURCE.get() == "local"
            with tool_source_scope("master"):
                assert _TOOL_SOURCE.get() == "master"
            assert _TOOL_SOURCE.get() == "local"
        assert _TOOL_SOURCE.get() == ""

    def test_error_text_truncated(self):
        from fr_cli.command.executor_dispatch import _short_error

        out = _short_error("x" * 200)
        assert len(out) <= 49
        assert out.endswith("…")
        assert _short_error(None) == ""


# ===================================================================
# 5. @ 文件补全
# ===================================================================


class TestFileCompletion:

    def _completer(self, agents, files):
        from fr_cli.ui.prompt.completer import FanRenCompleter

        return FanRenCompleter(
            get_commands=lambda: [],
            get_agents=lambda: agents,
            get_files=files,
        )

    def _doc(self, text):
        from prompt_toolkit.document import Document

        return Document(text)

    def test_files_completed_when_no_agent_matches(self):
        c = self._completer([("local", "本地")], lambda w: [("README.md", "文件")])
        out = list(c.get_completions(self._doc("@READ"), None))
        displays = [str(o.display) for o in out]
        assert any("README.md" in d for d in displays)

    def test_agent_wins_when_matched(self):
        """Agent 命中时优先给 Agent（@local 是内置 Agent，不是文件）"""
        c = self._completer([("local", "本地")], lambda w: [("local", "文件")])
        out = list(c.get_completions(self._doc("@loc"), None))
        assert len(out) == 1
        assert "local" in str(out[0].display)

    def test_no_files_callback_is_safe(self):
        c = self._completer([], None)
        out = list(c.get_completions(self._doc("@"), None))
        assert out == []


# ===================================================================
# 6. 首次启动上手卡片
# ===================================================================


class TestOnboardingCard:

    def test_printed_once_only(self, capsys, tmp_home):
        from fr_cli.repl.bootstrap import print_onboarding_card

        cfg = {}
        assert print_onboarding_card(None, cfg) is True
        out = capsys.readouterr().out
        assert "快速上手" in out
        assert "Ctrl+O" in out

        # 第二次不再打印
        assert print_onboarding_card(None, cfg) is False
        assert capsys.readouterr().out == ""

    def test_card_contains_one_runnable_example(self, capsys, tmp_home):
        """卡片要给一条能直接抄的示例（原文要求：快捷键 + 常用命令 + 一条示例）"""
        from fr_cli.repl.bootstrap import print_onboarding_card

        print_onboarding_card(None, {})
        out = capsys.readouterr().out
        assert "示例" in out
        assert "@local 帮我总结 README.md" in out

    def test_card_does_not_drop_existing_config(self, tmp_home):
        """回归：卡片只是置一个标志，不能把用户其它配置整份覆盖掉

        save_config 是整文件替换，历史上这里直接 save_config(cfg)，
        传入局部字典时会把用户配置整个抹掉（真实事故：provider/key 全丢）。
        """
        import json

        from fr_cli.conf.config import load_config, save_config
        from fr_cli.repl.bootstrap import print_onboarding_card

        save_config({
            "provider": "stepfun",
            "model": "step-5-preview",
            "providers": {"stepfun": {"key": "sk-keepme", "model": "step-5-preview"}},
            "custom_user_field": "must-survive",
        })

        assert print_onboarding_card(None, {}) is True

        disk = json.loads((tmp_home / ".fr_cli" / "config.json").read_text(encoding="utf-8"))
        assert disk.get("provider") == "stepfun", "provider 被卡片覆盖丢失"
        assert disk.get("model") == "step-5-preview", "model 被卡片覆盖丢失"
        assert disk.get("providers", {}).get("stepfun", {}).get("key") == "sk-keepme"
        assert disk.get("custom_user_field") == "must-survive", "自定义字段被卡片抹掉"
        assert disk.get("onboarding_card_shown") is True
        assert load_config().get("provider") == "stepfun"

    def test_box_borders_are_aligned(self, capsys, tmp_home):
        """框线（顶/内容/底）显示宽度必须一致，否则框会歪"""
        import re
        from fr_cli.repl.bootstrap import print_onboarding_card
        from fr_cli.ui.ui import get_display_width

        print_onboarding_card(None, {})
        out = capsys.readouterr().out
        clean = [re.sub(r"\033\[[0-9;]*m", "", ln) for ln in out.splitlines()]
        box = [ln for ln in clean if ln.startswith(("╭", "│", "╰"))]
        assert box, "未渲染出卡片框线"
        widths = {get_display_width(ln) for ln in box}
        assert len(widths) == 1, f"框线宽度不一致: {widths}"

    def test_narrow_terminal_keeps_alignment(self, capsys, tmp_home, monkeypatch):
        """窄终端下压缩描述列，但框线仍对齐、不折行"""
        import os
        import re
        import shutil

        from fr_cli.repl.bootstrap import print_onboarding_card
        from fr_cli.ui.ui import get_display_width

        monkeypatch.setattr(
            shutil, "get_terminal_size", lambda fallback=(80, 24): os.terminal_size((50, 24))
        )

        print_onboarding_card(None, {})
        out = capsys.readouterr().out
        clean = [re.sub(r"\033\[[0-9;]*m", "", ln) for ln in out.splitlines()]
        box = [ln for ln in clean if ln.startswith(("╭", "│", "╰"))]
        widths = {get_display_width(ln) for ln in box}
        assert len(widths) == 1, f"窄终端框线宽度不一致: {widths}"
        assert max(widths) <= 50, "窄终端下卡片超出终端宽度"
