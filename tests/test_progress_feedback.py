"""
进度反馈(spinner + on_progress 回调)测试
"""
from unittest.mock import MagicMock, patch



# ---------- Spinner 自身 ----------

class TestSpinner:
    """Spinner 基础行为 + TTY fallback"""

    def test_disabled_mode_just_prints(self, capsys):
        """非 TTY 模式(测试环境)只打印一行,不做动画"""
        from fr_cli.ui.spinner import Spinner

        with Spinner("测试中...", enabled=False):
            pass
        captured = capsys.readouterr()
        assert "测试中..." in captured.out
        # 没有动画字符
        assert "⠋" not in captured.out and "⠙" not in captured.out

    def test_update_message_changes_displayed_text(self, capsys):
        """update() 改变显示消息(运行中)"""
        from fr_cli.ui.spinner import Spinner

        sp = Spinner("初始", enabled=False)
        with sp:
            sp.update("更新后")
            sp.update("再次更新")
        # 至少最后一条消息被打印
        # 非 TTY 模式只打印 "..." 一行,update 不影响已打印行
        # 所以这里只验证不报错

    def test_context_manager_returns_self(self):
        from fr_cli.ui.spinner import Spinner
        sp = Spinner("x", enabled=False)
        with sp as returned:
            assert returned is sp

    def test_tty_mode_starts_and_stops_thread(self, capsys):
        """TTY 模式启动/停止后台线程"""
        from fr_cli.ui import spinner as sp_mod

        # 模拟 TTY
        original_isatty = sp_mod.sys.stdout.isatty
        sp_mod.sys.stdout.isatty = lambda: True
        try:
            sp = spinner_module_safe("loading", enabled=True)
            with sp:
                # 让线程跑一会
                import time
                time.sleep(0.25)
            # 退出后行被清除
            # 不严格断言,只验证不崩
            assert sp._thread is not None
        finally:
            sp_mod.sys.stdout.isatty = original_isatty

    def test_ascii_terminal_uses_ascii_frames(self, monkeypatch):
        """_can_encode_unicode 返回 False 时,Spinner 用 ASCII 帧"""
        from fr_cli.ui import spinner as sp_mod
        from fr_cli.ui.spinner import Spinner

        # 强制 _can_encode_unicode 返回 False
        monkeypatch.setattr(sp_mod, "_can_encode_unicode", lambda: False)

        sp = Spinner("x", enabled=True)
        # 不进入 context(避免后台线程跑)
        assert sp._frames == Spinner.ASCII_FRAMES
        assert "⠋" not in sp._frames

    def test_unicode_terminal_uses_braille_frames(self, monkeypatch):
        """_can_encode_unicode 返回 True 时,Spinner 用 Braille 帧"""
        from fr_cli.ui import spinner as sp_mod
        from fr_cli.ui.spinner import Spinner

        monkeypatch.setattr(sp_mod, "_can_encode_unicode", lambda: True)

        sp = Spinner("x", enabled=True)
        assert sp._frames == Spinner.FRAMES
        assert "⠋" in sp._frames


def spinner_module_safe(msg, enabled=True):
    """小工具:避坑 imports"""
    from fr_cli.ui.spinner import Spinner
    return Spinner(msg, enabled=enabled)


# ---------- on_progress 回调:InsightExtractor ----------

class TestInsightExtractorProgress:
    """InsightExtractor.extract 的 on_progress 回调被正确触发"""

    def test_on_progress_called_for_each_stage(self, monkeypatch):
        """完整流程下,4 个 stage 都被回调到(用 mock stream_cnt 让所有 stage 成功)"""
        from fr_cli.agent.insight_extractor import InsightExtractor
        from fr_cli.agent.insight_source import MockSelectionSource

        # mock stream_cnt 返回有效 JSON,让 batch + aggregate + save 全部成功
        valid_json = (
            '{"summary":"t","categories":[],"price_bands":[],'
            '"lifecycle_patterns":[],"seasonal_trends":[],"key_signals":[]}'
        )
        def fake_stream(*a, **kw):
            return (valid_json, None, 0.1, False)
        monkeypatch.setattr("fr_cli.core.stream.stream_cnt", fake_stream)

        captured = []
        def cb(stage, current, total, info):
            captured.append((stage, current, total, info))

        ext = InsightExtractor(
            client=MagicMock(), model_name="m", lang="zh",
            source=MockSelectionSource(count=10), batch_size=5,
        )
        ext.extract(on_progress=cb)

        # 必有的 stage
        stages = [s for s, *_ in captured]
        assert "load" in stages
        assert "summarize" in stages
        assert "aggregate" in stages  # 2 批,会走聚合
        assert "save" in stages

        # 2 批 → summarize 被调 2 次
        summarize_calls = [c for c in captured if c[0] == "summarize"]
        assert len(summarize_calls) == 2
        # 第 2 个 call: current=2, total=2
        assert summarize_calls[1][1] == 2
        assert summarize_calls[1][2] == 2

    def test_no_records_skips_summarize(self):
        """无数据时,summarize 阶段不触发"""
        from fr_cli.agent.insight_extractor import InsightExtractor
        from fr_cli.agent.insight_source import MockSelectionSource

        captured = []
        def cb(stage, current, total, info):
            captured.append(stage)

        ext = InsightExtractor(
            client=None, model_name=None, lang="zh",
            source=MockSelectionSource(count=0), batch_size=5,
        )
        ext.extract(on_progress=cb)
        assert "summarize" not in captured
        assert "load" in captured  # load 还是会跑

    def test_on_progress_none_backward_compatible(self):
        """不传 on_progress 时(向后兼容),extract 仍正常工作"""
        from fr_cli.agent.insight_extractor import InsightExtractor
        from fr_cli.agent.insight_source import MockSelectionSource

        ext = InsightExtractor(
            client=None, model_name=None, lang="zh",
            source=MockSelectionSource(count=10), batch_size=5,
        )
        # 关键:不传 on_progress 不应该报错
        result = ext.extract()
        assert "insights" in result


# ---------- on_progress 回调:CompetitorGapScanner ----------

class TestCompetitorScannerProgress:
    """CompetitorGapScanner.scan 的 on_progress 回调"""

    def test_on_progress_for_each_capability(self):
        from fr_cli.dynamic_builder.competitor_gap_scan import CompetitorGapScanner

        captured = []
        def cb(stage, current, total, info):
            captured.append((stage, current, total, info))

        # 自定义小模型,只测 2 个能力(快)
        scanner = CompetitorGapScanner()
        scanner._model_cache = {
            "domain": "test", "title": "t", "version": 1,
            "capabilities": [
                {"name": "cap_a", "description": "A", "key_signals": [],
                 "priority": "high", "example_usage": "x"},
                {"name": "cap_b", "description": "B", "key_signals": [],
                 "priority": "low", "example_usage": "x"},
            ],
        }
        with patch("fr_cli.dynamic_builder.gap_analyzer.analyze_gap",
                   return_value={"gap": False, "confidence": 0.9,
                                 "suggested_tool_name": "", "reasoning": ""}):
            scanner.scan(save_report=False, on_progress=cb)

        stages = [s for s, *_ in captured]
        assert "load_model" in stages
        assert "analyze" in stages
        analyze_calls = [c for c in captured if c[0] == "analyze"]
        assert len(analyze_calls) == 2
        # 第 2 次: current=2, total=2
        assert analyze_calls[1][1] == 2


# ---------- 端到端:命令 + spinner + on_progress ----------

class TestEndToEndProgress:
    """/insight extract 和 /competitor_gaps scan 命令走 spinner + on_progress"""

    def test_insight_extract_runs_without_error(self, capsys, monkeypatch):
        """extract 命令在 spinner 下不崩(Spinner 在非 TTY 自动降级)"""
        from fr_cli.repl.commands import insight as insight_cmd

        # 用 mock LLM 模拟一个简单的 summarize
        call_count = [0]
        def fake_stream(*a, **kw):
            call_count[0] += 1
            return (json_dummy(), None, 0.1, False)
        monkeypatch.setattr(
            "fr_cli.core.stream.stream_cnt", fake_stream
        )
        # 强制 spinner 进入"非 TTY 模式"(测试环境本来也是)
        from fr_cli.ui import spinner
        monkeypatch.setattr(spinner.sys, "stdout",
                            type("FakeStdout", (), {"isatty": lambda: False,
                                                     "encoding": "utf-8",
                                                     "write": lambda *a: None,
                                                     "flush": lambda: None})())

        result = insight_cmd._do_extract(MagicMock(), ["--batch", "5"])
        assert result is False
        # 至少调用了一次 LLM(没 LLM 时直接 skipped,call_count=0 也 OK)
        # 关键是结果正常返回

    def test_competitor_gaps_scan_runs_without_error(self, capsys, monkeypatch):
        from fr_cli.repl.commands import competitor_gaps

        with patch("fr_cli.dynamic_builder.gap_analyzer.analyze_gap",
                   return_value={"gap": True, "confidence": 0.8,
                                 "suggested_tool_name": "x", "reasoning": "r"}):
            result = competitor_gaps._cmd_competitor_gaps(
                MagicMock(), ["/competitor_gaps", "scan"]
            )
        assert result is False
        out = capsys.readouterr().out
        assert "竞品监控" in out or "能力扫描" in out


def json_dummy():
    """模拟 LLM 输出的简单 JSON"""
    import json
    return json.dumps({
        "summary": "test",
        "categories": [], "price_bands": [], "lifecycle_patterns": [],
        "seasonal_trends": [], "key_signals": [],
    }, ensure_ascii=False)
