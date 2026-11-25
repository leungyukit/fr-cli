"""
统一输出层测试(ui/output.py)
"""
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def force_color(monkeypatch):
    """默认所有测试都开颜色,这样能验证 ANSI 转义码

    v2.8.7：原先只 mock 了 stdout.isatty()，但
    ``fr_cli.ui.ui`` 在 **import 时**就做了两件事：
      ① ``_NO_COLOR = not color_enabled()`` —— 非 TTY 下为 True
      ② ``set_no_color(_NO_COLOR)`` —— 把 GREEN/CYAN/RESET 等常量**清空**
    于是 pytest（stdout 不是 TTY）下颜色常量是空串，断言 ANSI 码的用例
    在 CI 里必然失败 —— 且与 isatty mock 无关，mock 的是 stdout 对象，
    而 capsys 会在 fixture 之后替换 sys.stdout。

    正确做法：显式恢复颜色常量 + 强制判定函数返回 True。
    判定仍尊重 NO_COLOR / FR_CLI_NO_COLOR（TestTTYFallback 靠它）——
    那两个用例自己 reload 了 output 模块，重新绑定回真函数，行为与生产一致。
    """
    from fr_cli.ui import ui

    original_no_color = ui._NO_COLOR

    # ① 恢复被 import 时清空的颜色常量
    ui.set_no_color(False)
    # ② output.py 是按值 import 颜色常量的，得在恢复之后 reload 才能拿到带色值
    import importlib
    from fr_cli.ui import output
    importlib.reload(output)

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("FR_CLI_NO_COLOR", raising=False)

    def _fake_color_enabled() -> bool:
        import os
        if os.environ.get("FORCE_COLOR") or os.environ.get("CLICOLOR_FORCE"):
            return True
        if os.environ.get("NO_COLOR") or os.environ.get("FR_CLI_NO_COLOR"):
            return False
        return True  # 测试环境强制开色（CI/pytest 下 stdout 不是 TTY）

    monkeypatch.setattr(output, "_ui_color_enabled", _fake_color_enabled)

    yield

    # 还原：恢复原来的关色状态，并让 output 重新按当前常量绑定
    ui.set_no_color(original_no_color)
    importlib.reload(output)


# ---------- 基础 6 个函数 ----------

class TestBasicFunctions:
    """6 种语义化输出"""

    def test_success_includes_check_mark(self, capsys):
        from fr_cli.ui.output import success
        success("任务完成")
        out = capsys.readouterr().out
        assert "[OK]" in out
        assert "任务完成" in out
        assert "\x1b[" in out  # 含颜色码

    def test_failure_with_reason_and_suggestion(self, capsys):
        from fr_cli.ui.output import failure
        failure("加载失败", reason="网络超时", suggestion="重试或检查网络")
        out = capsys.readouterr().out
        assert "[x]" in out
        assert "加载失败" in out
        assert "网络超时" in out
        assert "重试" in out

    def test_warning_with_detail(self, capsys):
        from fr_cli.ui.output import warning
        warning("目录已存在", detail="/tmp/foo")
        out = capsys.readouterr().out
        assert "[!]" in out
        assert "目录已存在" in out
        assert "/tmp/foo" in out

    def test_info_basic(self, capsys):
        from fr_cli.ui.output import info
        info("正在分析...")
        out = capsys.readouterr().out
        assert "[i]" in out
        assert "正在分析" in out

    def test_step_with_progress(self, capsys):
        from fr_cli.ui.output import step
        step("加载中", current=2, total=10)
        out = capsys.readouterr().out
        assert "[2/10]" in out
        assert "加载中" in out

    def test_step_no_progress(self, capsys):
        from fr_cli.ui.output import step
        step("随便做点啥")
        out = capsys.readouterr().out
        assert "→" in out
        assert "随便做点啥" in out

    def test_header(self, capsys):
        from fr_cli.ui.output import header
        header("扫描结果")
        out = capsys.readouterr().out
        assert "扫描结果" in out
        assert "═══" in out


# ---------- kv / kv_block ----------

class TestKV:
    """key: value 输出"""

    def test_kv_basic(self, capsys):
        from fr_cli.ui.output import kv
        kv("模型", "glm-4-flash")
        out = capsys.readouterr().out
        assert "模型" in out
        assert "glm-4-flash" in out

    def test_kv_indent(self, capsys):
        from fr_cli.ui.output import kv
        kv("嵌套", "值", indent=1)
        out = capsys.readouterr().out
        assert out.startswith("  ")  # 2 空格缩进

    def test_kv_block(self, capsys):
        from fr_cli.ui.output import kv_block
        kv_block([
            ("模型", "glm-4-flash"),
            ("用量", "1234 tokens"),
        ])
        out = capsys.readouterr().out
        assert "模型" in out
        assert "glm-4-flash" in out
        assert "用量" in out
        assert "1234 tokens" in out


# ---------- 列表辅助 ----------

class TestListHelpers:
    """bullet / separator"""

    def test_bullet(self, capsys):
        from fr_cli.ui.output import bullet
        bullet(["item1", "item2", "item3"])
        out = capsys.readouterr().out
        assert "item1" in out
        assert "item2" in out
        assert "•" in out

    def test_bullet_indent(self, capsys):
        from fr_cli.ui.output import bullet
        bullet(["x"], indent=1)
        out = capsys.readouterr().out
        assert out.startswith("  ")

    def test_separator(self, capsys):
        from fr_cli.ui.output import separator
        separator()
        out = capsys.readouterr().out
        assert "─" in out
        # 前导空行
        assert out.startswith("\n")


# ---------- Result 适配器 ----------

class TestResultAdapter:
    """result() 接受 Result / tuple"""

    def test_result_tuple_success(self, capsys):
        from fr_cli.ui.output import result
        result(("data ok", None))
        out = capsys.readouterr().out
        assert "[OK]" in out
        assert "data ok" in out

    def test_result_tuple_failure(self, capsys):
        from fr_cli.ui.output import result
        result((None, "出错啦"))
        out = capsys.readouterr().out
        assert "[x]" in out
        assert "出错啦" in out

    def test_result_object_success(self, capsys):
        from fr_cli.ui.output import result
        r = MagicMock(error=None, data="loaded")
        result(r, success_msg="ok")
        out = capsys.readouterr().out
        assert "[OK]" in out
        assert "ok" in out

    def test_result_object_failure(self, capsys):
        from fr_cli.ui.output import result
        r = MagicMock(error="网络错误", data=None)
        result(r)
        out = capsys.readouterr().out
        assert "[x]" in out
        assert "网络错误" in out


# ---------- TTY 降级 ----------

class TestTTYFallback:
    """非 TTY / NO_COLOR 时退化"""

    def test_no_color_env(self, capsys, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        # 重新 import 才能拿到新环境变量判断
        import importlib
        from fr_cli.ui import output
        importlib.reload(output)
        output.success("test")
        out = capsys.readouterr().out
        # 无颜色码
        assert "\x1b[" not in out
        # 但 emoji 仍保留
        assert "[OK]" in out
        assert "test" in out

    def test_fr_cli_no_color_env(self, capsys, monkeypatch):
        monkeypatch.setenv("FR_CLI_NO_COLOR", "1")
        import importlib
        from fr_cli.ui import output
        importlib.reload(output)
        output.failure("bad")
        out = capsys.readouterr().out
        assert "\x1b[" not in out
        assert "[x]" in out
        assert "bad" in out


# ---------- 集成: insight 命令使用 output ----------

class TestInsightIntegration:
    """insight.py 的 print 调用应能正常跑"""

    def test_insight_unknown_subcommand_uses_failure(self, capsys):
        from fr_cli.repl.commands import insight
        state = MagicMock(lang="zh")
        insight._cmd_insight(state, ["/insight", "nonexistent_subcmd"])
        out = capsys.readouterr().out
        assert "[x]" in out
        assert "nonexistent_subcmd" in out

    def test_insight_sources_uses_info(self, capsys):
        from fr_cli.repl.commands import insight
        state = MagicMock(lang="zh")
        insight._cmd_insight(state, ["/insight", "sources"])
        out = capsys.readouterr().out
        assert "[i]" in out
        assert "可用选品数据源" in out

    def test_competitor_gaps_unknown_subcommand(self, capsys):
        from fr_cli.repl.commands import competitor_gaps
        state = MagicMock(lang="zh")
        competitor_gaps._cmd_competitor_gaps(state, ["/competitor_gaps", "weird"])
        out = capsys.readouterr().out
        assert "[x]" in out
        assert "weird" in out
