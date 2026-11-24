"""颜色判定单一源 + markdown_stream 跟随禁色 回归测试

固化的两个历史漏洞(均已修):
1. ui.py 的 _NO_COLOR 只认 NO_COLOR, 不认 FR_CLI_NO_COLOR, 与 output.py
   两套判定漂移 → FR_CLI_NO_COLOR=1 在 TTY 下关不掉 markdown 流式颜色。
2. markdown_stream 在 import 时把 ui 禁色态下的空常量"回填"成硬编码
   ANSI 码, 主动推翻全局禁色 → 非 TTY 场景泄漏 ?[96m 乱码。
"""
import io
import sys

import pytest

from fr_cli.ui import ui


def _set_tty(monkeypatch, value: bool):
    """伪造 stdin/stdout 的 isatty 返回值"""
    for stream in (sys.stdin, sys.stdout):
        monkeypatch.setattr(stream, "isatty", lambda v=value: v, raising=False)


class _PlainStdout:
    """普通 TTY stdout(类型模块名不含 prompt_toolkit, 不触发代理否决)

    带 write/flush 收集, 可直接断言 print_styled 的输出内容。
    """

    def __init__(self):
        self.chunks = []

    def isatty(self):
        return True

    def write(self, data):
        self.chunks.append(data)
        return len(data)

    def flush(self):
        pass


class _ProxyStdout:
    """伪装成 prompt_toolkit.patch_stdout 的 StdoutProxy

    代理检测看 type(sys.stdout).__module__, 改写类的 __module__ 即可伪装,
    不必真装 prompt_toolkit 代理。带 write 收集, 供断言打印内容。
    """

    __module__ = "prompt_toolkit.patch_stdout"

    def __init__(self):
        self.chunks = []

    def isatty(self):
        return True

    def write(self, data):
        self.chunks.append(data)
        return len(data)

    def flush(self):
        pass


@pytest.fixture(autouse=True)
def _restore_color_state():
    original = ui._NO_COLOR
    yield
    ui.set_no_color(original)


class TestColorEnabledSingleSource:
    """ui.color_enabled() 单一判定源"""

    def test_non_tty_disables(self, monkeypatch):
        _set_tty(monkeypatch, False)
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("FR_CLI_NO_COLOR", raising=False)
        monkeypatch.delenv("FORCE_COLOR", raising=False)
        monkeypatch.delenv("CLICOLOR_FORCE", raising=False)
        assert ui.color_enabled() is False

    def test_double_tty_enables(self, monkeypatch):
        _set_tty(monkeypatch, True)
        for var in ("NO_COLOR", "FR_CLI_NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE"):
            monkeypatch.delenv(var, raising=False)
        assert ui.color_enabled() is True

    def test_stdin_non_tty_disables_even_if_stdout_tty(self, monkeypatch):
        """双 TTY 才开色 —— 与 main.py 的提前判定策略一致"""
        monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
        for var in ("NO_COLOR", "FR_CLI_NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE"):
            monkeypatch.delenv(var, raising=False)
        assert ui.color_enabled() is False

    def test_fr_cli_no_color_env_respected_in_tty(self, monkeypatch):
        """修复点 1: FR_CLI_NO_COLOR 必须在 TTY 下也关掉 markdown 路径的颜色"""
        _set_tty(monkeypatch, True)
        monkeypatch.setenv("FR_CLI_NO_COLOR", "1")
        monkeypatch.delenv("NO_COLOR", raising=False)
        assert ui.color_enabled() is False

    def test_no_color_env_respected_in_tty(self, monkeypatch):
        _set_tty(monkeypatch, True)
        monkeypatch.setenv("NO_COLOR", "1")
        assert ui.color_enabled() is False

    def test_force_color_overrides_non_tty(self, monkeypatch):
        _set_tty(monkeypatch, False)
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("FR_CLI_NO_COLOR", raising=False)
        monkeypatch.setenv("FORCE_COLOR", "1")
        assert ui.color_enabled() is True

    def test_clicolor_force_overrides_non_tty(self, monkeypatch):
        _set_tty(monkeypatch, False)
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("FR_CLI_NO_COLOR", raising=False)
        monkeypatch.setenv("CLICOLOR_FORCE", "1")
        assert ui.color_enabled() is True

    def test_force_color_beats_no_color(self, monkeypatch):
        """优先级: 强制开 > 强制关"""
        _set_tty(monkeypatch, False)
        monkeypatch.setenv("FORCE_COLOR", "1")
        monkeypatch.setenv("NO_COLOR", "1")
        assert ui.color_enabled() is True

    def test_off_when_stdout_proxied_by_prompt_toolkit(self, monkeypatch):
        """优先级 0(本轮新增): stdout 被 patch_stdout 代理时一律关色。

        REPL 的 AI 对话跑在 queue.py 的 patch_stdout 上下文里, StdoutProxy
        非 raw 模式走 Vt100_Output.write(), 把 ESC 字节换成字面 '?'
        (prompt_toolkit/output/vt100.py: "Removes vt100 escape codes"),
        打任何色都只会得到 ?[96m 乱码; 且代理下 isatty() 仍为 True,
        只有这项检测能拦住(真实冒烟: markdown 满屏 ?[96m?[1m•?[0m、
        master_loop 的 ?[2m自动会话已创建...?[0m)。
        """
        _set_tty(monkeypatch, True)
        for var in ("NO_COLOR", "FR_CLI_NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setattr(sys, "stdout", _ProxyStdout())
        assert ui.color_enabled() is False

    def test_proxy_veto_beats_force_color(self, monkeypatch):
        """代理否决压过 FORCE_COLOR: 代理下打了色也只会显示 ?[ 乱码,
        强制开在这里没有意义, 宁可纯文本。"""
        _set_tty(monkeypatch, True)
        for var in ("NO_COLOR", "FR_CLI_NO_COLOR", "CLICOLOR_FORCE"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("FORCE_COLOR", "1")
        monkeypatch.setattr(sys, "stdout", _ProxyStdout())
        assert ui.color_enabled() is False

    def test_on_when_stdout_is_plain_tty(self, monkeypatch):
        """回归: 普通 TTY stdout 不触发代理否决, 正常上色不能被误伤"""
        _set_tty(monkeypatch, True)
        for var in ("NO_COLOR", "FR_CLI_NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setattr(sys, "stdout", _PlainStdout())
        assert ui.color_enabled() is True


class TestMarkdownStreamFollowsGlobalState:
    """修复点 2: markdown_stream 颜色常量实时跟随 ui, 禁色态拼不出任何序列"""

    def test_disabled_state_emits_no_escape(self):
        from fr_cli.ui.markdown_stream import StreamingMarkdownRenderer
        ui.set_no_color(True)
        # 即使调用方显式传 use_color=True, 禁色态下常量是空串, 拼不出序列
        r = StreamingMarkdownRenderer(use_color=True)
        out = r.feed("- 项目符号\n")
        assert "\033[" not in out
        assert "•" in out

    def test_enabled_state_emits_escape(self):
        from fr_cli.ui.markdown_stream import StreamingMarkdownRenderer
        ui.set_no_color(False)
        r = StreamingMarkdownRenderer(use_color=True)
        out = r.feed("- 项目符号\n")
        assert "\033[96m" in out  # 亮青
        assert "\033[1m" in out   # 加粗
        assert "\033[0m" in out   # 复位
        assert "•" in out

    def test_toggle_mid_stream(self):
        """运行中切换全局开关, 渲染器实时跟随(旧版 import 快照做不到)"""
        from fr_cli.ui.markdown_stream import StreamingMarkdownRenderer
        ui.set_no_color(False)
        r = StreamingMarkdownRenderer(use_color=True)
        assert "\033[" in r.feed("- a\n")
        ui.set_no_color(True)
        assert "\033[" not in r.feed("- b\n")

    def test_constants_are_dynamic_proxy(self):
        """模块级 __getattr__ 代理: 访问即取 ui 当前值, 不是 import 时快照"""
        from fr_cli.ui import markdown_stream
        ui.set_no_color(True)
        assert markdown_stream.CYAN == ""
        assert markdown_stream.RESET == ""
        ui.set_no_color(False)
        assert markdown_stream.CYAN == "\033[96m"

    def test_unknown_attribute_still_raises(self):
        from fr_cli.ui import markdown_stream
        with pytest.raises(AttributeError):
            _ = markdown_stream.NOT_A_COLOR


class TestStreamRendererColorDecision:
    """stream.py 的组合判定(可测函数)"""

    def test_off_when_non_tty(self, monkeypatch):
        from fr_cli.core.stream import _markdown_use_color
        _set_tty(monkeypatch, False)
        for var in ("NO_COLOR", "FR_CLI_NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE"):
            monkeypatch.delenv(var, raising=False)
        ui.set_no_color(False)  # 全局没被显式关, 但环境非 TTY
        assert _markdown_use_color() is False

    def test_off_when_explicitly_disabled(self, monkeypatch):
        from fr_cli.core.stream import _markdown_use_color
        _set_tty(monkeypatch, True)
        for var in ("NO_COLOR", "FR_CLI_NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE"):
            monkeypatch.delenv(var, raising=False)
        ui.set_no_color(True)
        assert _markdown_use_color() is False

    def test_on_when_tty_and_enabled(self, monkeypatch):
        from fr_cli.core.stream import _markdown_use_color
        _set_tty(monkeypatch, True)
        for var in ("NO_COLOR", "FR_CLI_NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE"):
            monkeypatch.delenv(var, raising=False)
        ui.set_no_color(False)
        assert _markdown_use_color() is True

    def test_off_when_fr_cli_no_color_in_tty(self, monkeypatch):
        """修复点 1 的端到端: FR_CLI_NO_COLOR=1 + TTY → 流式路径也关色"""
        from fr_cli.core.stream import _markdown_use_color
        _set_tty(monkeypatch, True)
        monkeypatch.setenv("FR_CLI_NO_COLOR", "1")
        monkeypatch.delenv("NO_COLOR", raising=False)
        ui.set_no_color(False)
        assert _markdown_use_color() is False

    def test_off_when_stdout_proxied_by_prompt_toolkit(self, monkeypatch):
        """真实 TTY 的 REPL 里 stdout 被 patch_stdout 代理: StdoutProxy 会把
        ANSI 的 ESC 字节替换成字面 '?', 渲染器必须关色。

        这是真实冒烟暴露的遗漏: _ColorDisable 一直有这项检测, 但只管
        stream.py 自己的常量, markdown renderer 的颜色开关漏了, 导致
        REPL 里 markdown 输出显示 ?[96m?[1m•?[0m 乱码。
        """
        from fr_cli.core import stream as stream_mod
        from fr_cli.core.stream import _markdown_use_color
        _set_tty(monkeypatch, True)
        for var in ("NO_COLOR", "FR_CLI_NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE"):
            monkeypatch.delenv(var, raising=False)
        ui.set_no_color(False)
        monkeypatch.setattr(stream_mod, "_is_prompt_toolkit_stdout", lambda: True)
        assert _markdown_use_color() is False

    def test_on_when_stdout_not_proxied(self, monkeypatch):
        """未被代理 + TTY + 全局开 → 开色"""
        from fr_cli.core import stream as stream_mod
        from fr_cli.core.stream import _markdown_use_color
        _set_tty(monkeypatch, True)
        for var in ("NO_COLOR", "FR_CLI_NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE"):
            monkeypatch.delenv(var, raising=False)
        ui.set_no_color(False)
        monkeypatch.setattr(stream_mod, "_is_prompt_toolkit_stdout", lambda: False)
        assert _markdown_use_color() is True


class TestOutputColorEnabledDelegation:
    """output.py 的判定委托给 ui, 两套逻辑不再漂移"""

    def test_matches_ui_decision(self, monkeypatch):
        from fr_cli.ui import output
        _set_tty(monkeypatch, True)
        monkeypatch.setenv("FR_CLI_NO_COLOR", "1")
        monkeypatch.delenv("NO_COLOR", raising=False)
        assert output._color_enabled() is False
        assert output._color_enabled() == ui.color_enabled()


class TestOutputColorGateIsRuntime:
    """本轮修复: output._c() 每次调用实时判定, 不用 import 时快照。

    patch_stdout 代理是 REPL 对话中途才装上的, import 时(stdout 还是真 TTY)
    求值的 _COLOR 快照会把代理期的颜色决策冻死在"开", 之后每次 _c() 都往
    StdoutProxy 里打 ESC, 用户看到的就是 ?[92m 这类乱码。
    """

    def test_c_gated_by_runtime_color_enabled(self, monkeypatch):
        """同一支 _c(): 代理下原样返回, 非代理 TTY 下才包色。

        pytest 非 TTY 环境下 output 的快照常量本就是空串, 直接打 success()
        两种代码路径都看不出差别; 这里喂显式颜色码, 让"放不放行"完全由
        门控决定 —— 谁把 _c 改回 import 快照, 第二个断言就会挂。
        """
        from fr_cli.ui import output
        for var in ("NO_COLOR", "FR_CLI_NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE"):
            monkeypatch.delenv(var, raising=False)
        _set_tty(monkeypatch, True)  # stdin 也要是 TTY(双 TTY 才开色)
        # pytest 非 TTY 环境下 output 的快照常量是空串, 喂真码才能观测门控放行
        monkeypatch.setattr(output, "RESET", "\033[0m")
        monkeypatch.setattr(sys, "stdout", _ProxyStdout())
        assert output._c("\033[92m", "x") == "x"
        monkeypatch.setattr(sys, "stdout", _PlainStdout())
        assert output._c("\033[92m", "x") == "\033[92mx\033[0m"

    def test_color_enabled_false_under_proxy(self, monkeypatch):
        """委托链在代理下返回 False(output._color_enabled → ui.color_enabled)"""
        from fr_cli.ui import output
        _set_tty(monkeypatch, True)
        for var in ("NO_COLOR", "FR_CLI_NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setattr(sys, "stdout", _ProxyStdout())
        assert output._color_enabled() is False

    def test_success_plain_under_proxy(self, monkeypatch):
        """冒烟: 代理期 success() 整体不泄漏 ESC( constants 喂真码,
        这样"是否泄漏"才真由门控决定, 能抓到把门控删掉的回归)"""
        from fr_cli.ui import output
        for var in ("NO_COLOR", "FR_CLI_NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setattr(output, "GREEN", "\033[92m")
        monkeypatch.setattr(output, "RESET", "\033[0m")
        monkeypatch.setattr(output, "DIM", "\033[2m")
        fake = _ProxyStdout()
        monkeypatch.setattr(sys, "stdout", fake)
        output.success("任务完成", detail="已存档")
        text = "".join(fake.chunks)
        assert "\033[" not in text
        assert "[OK] 任务完成" in text
        assert "已存档" in text


class TestPrintStyled:
    """chat 路径统一出口 ui.print_styled(): 色开原样打, 色关剥序列

    固化的漏洞: pipeline_respond/pipeline_post/plan_mode/thinking/master_loop
    等 19 处原本是 `from ui import DIM, RESET` 后裸 print(f"{DIM}...{RESET}")。
    REPL 的 AI 对话期 stdout 被 prompt_toolkit.patch_stdout 代理,
    Vt100_Output.write() 把 ESC 字节换成字面 '?', 于是用户满屏看到
    ?[2m自动会话已创建?[0m 这种乱码(真实冒烟复现过)。统一走 print_styled
    后, 代理/非 TTY/NO_COLOR 三种场景都输出纯文本。
    """

    SAMPLE = "\033[2m自动会话已创建\033[0m · \033[36m已切到新会话\033[0m"

    def test_plain_tty_keeps_ansi(self, monkeypatch):
        """普通 TTY(命令路径): 原样透传, 不误剥"""
        for var in ("NO_COLOR", "FR_CLI_NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE"):
            monkeypatch.delenv(var, raising=False)
        _set_tty(monkeypatch, True)
        ui.set_no_color(False)  # 清掉 import 快照, 让判定只由环境决定
        fake = _PlainStdout()
        monkeypatch.setattr(sys, "stdout", fake)
        ui.print_styled(self.SAMPLE)
        text = "".join(fake.chunks)
        assert text == self.SAMPLE + "\n"
        assert "\033[" in text

    def test_proxy_strips_ansi(self, monkeypatch):
        """代理期(REPL 的 AI 对话): 剥成纯文本, 不泄漏 ?[ 乱码"""
        _set_tty(monkeypatch, True)  # 代理下 isatty 仍为 True, 只有否决能拦住
        for var in ("NO_COLOR", "FR_CLI_NO_COLOR", "CLICOLOR_FORCE"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("FORCE_COLOR", "1")  # 压过 FORCE_COLOR, 它没有意义
        ui.set_no_color(False)  # 只留代理否决一道闸, 谁删了否决本测试挂
        fake = _ProxyStdout()
        monkeypatch.setattr(sys, "stdout", fake)
        ui.print_styled(self.SAMPLE)
        text = "".join(fake.chunks)
        assert "\033[" not in text
        assert "?[" not in text
        assert "自动会话已创建" in text and "已切到新会话" in text

    def test_non_tty_strips_ansi(self, monkeypatch):
        """非 TTY(管道/重定向/日志): 剥成纯文本"""
        for var in ("NO_COLOR", "FR_CLI_NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE"):
            monkeypatch.delenv(var, raising=False)
        _set_tty(monkeypatch, False)
        ui.set_no_color(False)
        fake = _PlainStdout()
        monkeypatch.setattr(sys, "stdout", fake)
        ui.print_styled(self.SAMPLE)
        text = "".join(fake.chunks)
        assert "\033[" not in text
        assert text == "自动会话已创建 · 已切到新会话\n"

    def test_no_color_env_strips_even_in_tty(self, monkeypatch):
        """TTY 下 NO_COLOR=1: 剥成纯文本(用户显式关色)"""
        for var in ("FR_CLI_NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("NO_COLOR", "1")
        _set_tty(monkeypatch, True)
        ui.set_no_color(False)
        fake = _PlainStdout()
        monkeypatch.setattr(sys, "stdout", fake)
        ui.print_styled(self.SAMPLE)
        assert "\033[" not in "".join(fake.chunks)

    def test_explicit_set_no_color_strips(self, monkeypatch):
        """set_no_color(True) 显式覆盖也走剥离子句

        回归: print_styled 曾只查 color_enabled(), 漏掉 _NO_COLOR 显式态,
        cron 等运行时关色后 chat 路径照样打色。判定组合必须与
        stream._markdown_use_color 一致: 两个条件缺一不可。
        """
        for var in ("NO_COLOR", "FR_CLI_NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE"):
            monkeypatch.delenv(var, raising=False)
        _set_tty(monkeypatch, True)
        ui.set_no_color(True)
        fake = _PlainStdout()
        monkeypatch.setattr(sys, "stdout", fake)
        ui.print_styled(self.SAMPLE)
        assert "\033[" not in "".join(fake.chunks)

    def test_no_message_drift_between_paths(self, monkeypatch):
        """反漂移: 同一条消息两条代码路径的纯文本内容必须一致。

        若有人把 print_styled 改成 "if color: print(彩色版) else: print(纯文版)"
        抄两份消息, 两边文案漂移时本断言挂。
        """
        for var in ("NO_COLOR", "FR_CLI_NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE"):
            monkeypatch.delenv(var, raising=False)
        # 路径 A: 普通 TTY, 原样带色输出
        _set_tty(monkeypatch, True)
        ui.set_no_color(False)
        colored = _PlainStdout()
        monkeypatch.setattr(sys, "stdout", colored)
        ui.print_styled(self.SAMPLE)
        # 路径 B: 同一消息在代理下剥色输出
        stripped = _ProxyStdout()
        monkeypatch.setattr(sys, "stdout", stripped)
        ui.print_styled(self.SAMPLE)
        from fr_cli.ui.ansi import strip_ansi
        assert strip_ansi("".join(colored.chunks)) == "".join(stripped.chunks)


class TestSecurityPathNoLeak:
    """安全确认(Y/A/F/N)路径不带色裸 print 回归

    固化的漏洞: ReAct 工具执行跑在 queue.py 的 patch_stdout 代理里,
    security.ask() 的标题/选项/重试提示与 input() 提示符原本是
    `from ui import RED, BOLD...` 后裸 print/input, 代理期 ESC 被换成
    '?', 用户看到:
        ?[91m?[1m[!] 检测到高危神通，请选择因果:?[0m
        ?[93m  >> 读取卷轴: MANUAL.md?[0m
        ?[96m[Y]仅此  [A]本轮  [F]永世  [N]拒绝?[0m
    (live 冒烟复现: master agent 调 read_file 触发 sec_read 确认)。
    统一走 print_styled + use_color() 门控 input 提示后, 代理期输出纯文本。
    """

    def _clean_env(self, monkeypatch):
        for var in ("NO_COLOR", "FR_CLI_NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE",
                    "FR_CLI_BATCH_CONFIRM", "FR_CLI_NON_INTERACTIVE"):
            monkeypatch.delenv(var, raising=False)

    def test_ask_strips_ansi_under_proxy(self, monkeypatch):
        """代理期(REPL AI 对话): 三段提示全部剥成纯文本, 内容不丢"""
        import fr_cli.security.security as security_mod
        self._clean_env(monkeypatch)
        _set_tty(monkeypatch, True)
        ui.set_no_color(False)
        fake = _ProxyStdout()
        monkeypatch.setattr(sys, "stdout", fake)
        monkeypatch.setattr("builtins.input", lambda prompt="": "n")
        allowed, _, _ = security_mod.ask("sec_read", "MANUAL.md", "zh", {}, {}, {})
        assert allowed is False
        text = "".join(fake.chunks)
        assert "\033[" not in text and "?[" not in text
        assert "检测到高危神通" in text
        assert "读取卷轴: MANUAL.md" in text
        assert "[Y]仅此" in text and "[N]拒绝" in text

    def test_ask_input_prompt_has_no_escape_under_proxy(self, monkeypatch):
        """代理期 input() 提示符退化为纯空格, 不带转义序列"""
        import fr_cli.security.security as security_mod
        self._clean_env(monkeypatch)
        _set_tty(monkeypatch, True)
        ui.set_no_color(False)
        seen = []
        monkeypatch.setattr(sys, "stdout", _ProxyStdout())
        monkeypatch.setattr("builtins.input",
                            lambda prompt="": (seen.append(prompt), "n")[1])
        security_mod.ask("sec_read", "MANUAL.md", "zh", {}, {}, {})
        assert seen and "\033[" not in seen[0] and "?[" not in seen[0]

    def test_ask_keeps_ansi_on_plain_tty(self, monkeypatch):
        """普通 TTY(非代理): 颜色原样透传, 不误剥"""
        import fr_cli.security.security as security_mod
        self._clean_env(monkeypatch)
        _set_tty(monkeypatch, True)
        ui.set_no_color(False)
        # 模拟 import 时开着色的常量快照(pytest 收集期多半非 TTY, 常量是空串)
        for name, code in (("RED", "\033[91m"), ("BOLD", "\033[1m"),
                           ("YELLOW", "\033[93m"), ("CYAN", "\033[96m"),
                           ("RESET", "\033[0m")):
            monkeypatch.setattr(security_mod, name, code)
        fake = _PlainStdout()
        monkeypatch.setattr(sys, "stdout", fake)
        monkeypatch.setattr("builtins.input", lambda prompt="": "n")
        security_mod.ask("sec_read", "MANUAL.md", "zh", {}, {}, {})
        text = "".join(fake.chunks)
        assert "\033[91m" in text and "\033[96m" in text
        assert "?[" not in text

    def test_retry_hint_strips_under_proxy(self, monkeypatch):
        """未识别输入的重试提示同样走 print_styled"""
        import fr_cli.security.security as security_mod
        self._clean_env(monkeypatch)
        _set_tty(monkeypatch, True)
        ui.set_no_color(False)
        answers = iter(["x", "n"])
        monkeypatch.setattr(sys, "stdout", _ProxyStdout())
        monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
        security_mod.ask("sec_read", "MANUAL.md", "zh", {}, {}, {})
        text = "".join(sys.stdout.chunks)
        assert "请输入 Y/A/F/N 之一" in text
        assert "\033[" not in text and "?[" not in text

    def test_sandbox_auto_echo_strips_under_proxy(self, monkeypatch):
        """command/security.py 的 sandbox_auto 自动放行回显也不泄漏"""
        from fr_cli.command.security import SecurityManager
        self._clean_env(monkeypatch)
        _set_tty(monkeypatch, True)
        ui.set_no_color(False)
        fake = _ProxyStdout()
        monkeypatch.setattr(sys, "stdout", fake)
        mgr = SecurityManager("zh", {"autonomous_mode": "sandbox_auto"})
        assert mgr.check("sec_read", "MANUAL.md") is True
        text = "".join(fake.chunks)
        assert "自动放行沙盒操作: sec_read" in text
        assert "\033[" not in text and "?[" not in text

    def test_use_color_matches_print_styled_predicate(self, monkeypatch):
        """use_color() = 显式关色 与 环境判定 缺一不可(与 print_styled 同一判定)"""
        self._clean_env(monkeypatch)
        _set_tty(monkeypatch, True)
        ui.set_no_color(False)
        monkeypatch.setattr(sys, "stdout", _PlainStdout())
        assert ui.use_color() is True
        ui.set_no_color(True)
        assert ui.use_color() is False  # 显式关色压过 TTY
        ui.set_no_color(False)
        monkeypatch.setattr(sys, "stdout", _ProxyStdout())
        assert ui.use_color() is False  # 代理否决压过 TTY
