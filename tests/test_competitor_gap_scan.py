"""
竞品监控 能力缺口扫描器 测试
"""
import json
import yaml
from unittest.mock import MagicMock, patch

import pytest


# ---------- 隔离 fixture ----------

@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """隔离 ~/.fr_cli/,避免污染真实环境"""
    fake_fr_cli = tmp_path / ".fr_cli"
    fake_fr_cli.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(tmp_path))
    import fr_cli.conf.paths as _paths_mod
    if hasattr(_paths_mod, "_root_holder"):
        monkeypatch.setattr(_paths_mod._root_holder, "value", fake_fr_cli)
    yield
    # 清空模块缓存,避免后测影响前测
    import sys
    for mod in list(sys.modules):
        if mod.startswith("fr_cli.dynamic_builder.competitor_gap_scan"):
            del sys.modules[mod]


# ---------- load_model ----------

def test_load_default_model():
    from fr_cli.dynamic_builder.competitor_gap_scan import load_model
    model = load_model()
    assert model["domain"] == "competitor_monitor"
    assert model["title"] == "竞品监控"
    assert isinstance(model["capabilities"], list)
    assert len(model["capabilities"]) >= 5  # 至少 5 个能力
    # 抽查第一个能力结构
    cap = model["capabilities"][0]
    assert "name" in cap
    assert "description" in cap
    assert "key_signals" in cap
    assert "priority" in cap


def test_load_model_custom_path(tmp_path):
    from fr_cli.dynamic_builder.competitor_gap_scan import load_model
    custom_yaml = tmp_path / "custom.yaml"
    custom_yaml.write_text(yaml.dump({
        "domain": "test_domain",
        "title": "测试领域",
        "version": 2,
        "capabilities": [
            {"name": "test_cap", "description": "测试能力", "priority": "high"}
        ],
    }, allow_unicode=True), encoding="utf-8")
    model = load_model(path=str(custom_yaml))
    assert model["domain"] == "test_domain"
    assert model["version"] == 2
    assert len(model["capabilities"]) == 1


def test_load_model_missing_file_raises():
    from fr_cli.dynamic_builder.competitor_gap_scan import load_model
    with pytest.raises(FileNotFoundError, match="能力模型文件不存在"):
        load_model(path="/nonexistent/file.yaml")


def test_load_model_invalid_format(tmp_path):
    from fr_cli.dynamic_builder.competitor_gap_scan import load_model
    bad = tmp_path / "bad.yaml"
    bad.write_text("this is not a dict", encoding="utf-8")
    with pytest.raises(ValueError, match="格式错误"):
        load_model(path=str(bad))

    bad2 = tmp_path / "bad2.yaml"
    bad2.write_text(yaml.dump({"no_capabilities": True}, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="capabilities 列表"):
        load_model(path=str(bad2))


# ---------- format_report_text ----------

def test_format_report_empty():
    from fr_cli.dynamic_builder.competitor_gap_scan import format_report_text
    assert format_report_text({}) == "(无报告)"


def test_format_report_no_gaps():
    from fr_cli.dynamic_builder.competitor_gap_scan import format_report_text
    report = {
        "title": "竞品监控",
        "scanned": 8,
        "gap_count": 0,
        "tools_count": 50,
        "timestamp": "2026-08-14T10:00:00",
        "gaps": [],
    }
    text = format_report_text(report)
    assert "竞品监控" in text
    assert "已扫: 8" in text
    assert "缺口: 0" in text
    assert "现有工具: 50" in text
    assert "已覆盖" in text


def test_format_report_with_gaps_sorted_by_priority():
    from fr_cli.dynamic_builder.competitor_gap_scan import format_report_text
    report = {
        "title": "竞品监控",
        "scanned": 3,
        "gap_count": 3,
        "tools_count": 10,
        "timestamp": "2026-08-14T10:00:00",
        "gaps": [
            {"name": "low_cap", "description": "低优", "priority": "low",
             "confidence": 0.9, "key_signals": ["a"], "reasoning": "r"},
            {"name": "high_cap", "description": "高优", "priority": "high",
             "confidence": 0.5, "key_signals": ["b"], "reasoning": "r"},
            {"name": "medium_cap", "description": "中优", "priority": "medium",
             "confidence": 0.7, "key_signals": ["c"], "reasoning": "r"},
        ],
    }
    text = format_report_text(report)
    # 验证顺序: high → medium → low
    h_pos = text.find("high_cap")
    m_pos = text.find("medium_cap")
    l_pos = text.find("low_cap")
    assert h_pos < m_pos < l_pos
    # 优先级 emoji
    assert "🔴" in text
    assert "🟡" in text
    assert "🟢" in text


# ---------- Scanner.scan() ----------

def test_scan_uses_analyze_gap_and_saves_report():
    """扫描流程:遍历能力 → 调 analyze_gap → 只保留 gap 项 → 持久化"""
    from fr_cli.dynamic_builder.competitor_gap_scan import (
        CompetitorGapScanner, load_latest_report,
    )

    # 模拟 analyze_gap: 前 2 个返回 gap=True, 后 1 个返回 gap=False
    call_log = []
    def fake_analyze(requirement, tools, state, lang):
        call_log.append(requirement[:30])
        if "price" in requirement:
            return {"gap": True, "confidence": 0.9,
                    "suggested_tool_name": "competitor_price_monitor",
                    "reasoning": "无对应工具"}
        if "stock" in requirement:
            return {"gap": True, "confidence": 0.7,
                    "suggested_tool_name": "competitor_stock_monitor",
                    "reasoning": "无对应工具"}
        return {"gap": False, "confidence": 0.95,
                "suggested_tool_name": "",
                "reasoning": "已有 read_file 工具可覆盖"}

    # 加载内置模型但只测前 3 个能力(避免依赖全部)
    scanner = CompetitorGapScanner()
    # 截短 capabilities 到 3 个,模拟场景
    scanner._model_cache = None
    model_full = scanner.model
    scanner._model_cache = {
        **model_full,
        "capabilities": [
            {"name": "competitor_price_monitor", "description": "价格",
             "key_signals": ["价格"], "priority": "high", "example_usage": "x"},
            {"name": "competitor_stock_monitor", "description": "库存",
             "key_signals": ["库存"], "priority": "medium", "example_usage": "x"},
            {"name": "competitor_new_arrivals", "description": "上新",
             "key_signals": ["上新"], "priority": "high", "example_usage": "x"},
        ],
    }

    state = MagicMock()
    scanner = CompetitorGapScanner(state=state)
    scanner._model_cache = None
    model_full = scanner.model
    scanner._model_cache = {
        **model_full,
        "capabilities": [
            {"name": "competitor_price_monitor", "description": "价格",
             "key_signals": ["价格"], "priority": "high", "example_usage": "x"},
            {"name": "competitor_stock_monitor", "description": "库存",
             "key_signals": ["库存"], "priority": "medium", "example_usage": "x"},
            {"name": "competitor_new_arrivals", "description": "上新",
             "key_signals": ["上新"], "priority": "high", "example_usage": "x"},
        ],
    }

    with patch("fr_cli.dynamic_builder.gap_analyzer.analyze_gap", side_effect=fake_analyze):
        report = scanner.scan(save_report=True)

    # 1) analyze_gap 确实被调了 3 次
    assert len(call_log) == 3

    # 2) report 结构正确
    assert report["scanned"] == 3
    assert report["gap_count"] == 2  # 只有 2 个 True
    gap_names = [g["name"] for g in report["gaps"]]
    assert "competitor_price_monitor" in gap_names
    assert "competitor_stock_monitor" in gap_names
    assert "competitor_new_arrivals" not in gap_names  # False 被过滤

    # 3) 持久化检查
    saved = load_latest_report()
    assert saved is not None
    assert saved["scanned"] == 3
    assert saved["gap_count"] == 2


def test_scan_handles_analyzer_exception():
    """analyze_gap 抛异常时,扫描器把该项标为 gap 继续往下走"""
    from fr_cli.dynamic_builder.competitor_gap_scan import CompetitorGapScanner

    def boom(*a, **kw):
        raise RuntimeError("LLM 罢工了")

    scanner = CompetitorGapScanner()
    scanner._model_cache = {
        "domain": "test", "title": "t", "version": 1,
        "capabilities": [
            {"name": "cap_x", "description": "d", "key_signals": [],
             "priority": "high", "example_usage": "x"},
        ],
    }
    with patch("fr_cli.dynamic_builder.gap_analyzer.analyze_gap", side_effect=boom):
        report = scanner.scan(save_report=False)
    assert report["gap_count"] == 1
    assert report["gaps"][0]["reasoning"].startswith("分析器异常")
    assert report["gaps"][0]["gap"] is True


# ---------- REPL 命令 ----------

def test_cmd_competitor_gaps_model():
    """/competitor_gaps model 显示模型概要"""
    from fr_cli.repl.commands.competitor_gaps import _cmd_competitor_gaps
    state = MagicMock()
    result = _cmd_competitor_gaps(state, ["/competitor_gaps", "model"])
    assert result is False


def test_cmd_competitor_gaps_show_no_report():
    """/competitor_gaps show 无报告时友好提示"""
    from fr_cli.repl.commands.competitor_gaps import _cmd_competitor_gaps
    state = MagicMock()
    result = _cmd_competitor_gaps(state, ["/competitor_gaps", "show"])
    assert result is False


def test_cmd_competitor_gaps_scan_with_mock_analyzer():
    """/competitor_gaps scan 端到端"""
    from fr_cli.repl.commands.competitor_gaps import _cmd_competitor_gaps

    fake_analyze = MagicMock(return_value={
        "gap": True, "confidence": 0.8,
        "suggested_tool_name": "x", "reasoning": "r",
    })
    state = MagicMock()
    state.display_model = "mock"
    state.lang = "zh"
    with patch("fr_cli.dynamic_builder.gap_analyzer.analyze_gap", side_effect=fake_analyze):
        result = _cmd_competitor_gaps(state, ["/competitor_gaps", "scan"])

    assert result is False
    assert fake_analyze.call_count >= 5  # 至少 5 个内置能力


def test_cmd_competitor_gaps_add_pushes_to_review_queue():
    """/competitor_gaps add <name> 推到 /hermes review 队列"""
    from fr_cli.dynamic_builder.competitor_gap_scan import _reports_dir
    from fr_cli.repl.commands.competitor_gaps import _cmd_competitor_gaps

    # 先种一份 latest.json
    d = _reports_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "latest.json").write_text(json.dumps({
        "title": "竞品监控",
        "scanned": 1,
        "gap_count": 1,
        "tools_count": 0,
        "timestamp": "2026-08-14T10:00:00",
        "gaps": [
            {"name": "competitor_price_monitor",
             "description": "价格监控",
             "priority": "high",
             "key_signals": ["价格"],
             "example_usage": "x",
             "gap": True,
             "confidence": 0.9,
             "suggested_tool_name": "competitor_price_monitor",
             "reasoning": "r"},
        ],
    }, ensure_ascii=False), encoding="utf-8")

    # mock ReviewQueue
    mock_item = MagicMock()
    mock_item.id = "rev-test123"
    mock_queue_class = MagicMock()
    mock_queue_class.return_value.add.return_value = mock_item

    state = MagicMock()
    with patch.dict("sys.modules", {
        "fr_cli.agent.review_queue": MagicMock(ReviewQueue=mock_queue_class),
    }):
        result = _cmd_competitor_gaps(state, ["/competitor_gaps", "add",
                                              "competitor_price_monitor"])
    assert result is False
    # 验证 add 被调,且 artifact_type="competitor_gap"
    call_kwargs = mock_queue_class.return_value.add.call_args.kwargs
    assert call_kwargs["artifact_type"] == "competitor_gap"
    assert call_kwargs["suggested_name"] == "competitor_price_monitor"
    assert call_kwargs["metadata"]["priority"] == "high"


def test_cmd_competitor_gaps_add_unknown_name():
    """/competitor_gaps add <不存在的 name> 友好提示"""
    from fr_cli.dynamic_builder.competitor_gap_scan import _reports_dir
    from fr_cli.repl.commands.competitor_gaps import _cmd_competitor_gaps

    d = _reports_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "latest.json").write_text(json.dumps({
        "gaps": [{"name": "real_cap"}],
    }, ensure_ascii=False), encoding="utf-8")

    state = MagicMock()
    result = _cmd_competitor_gaps(state, ["/competitor_gaps", "add", "nope"])
    assert result is False


def test_cmd_competitor_gaps_add_no_report():
    """/competitor_gaps add 但没报告时友好提示"""
    from fr_cli.repl.commands.competitor_gaps import _cmd_competitor_gaps
    state = MagicMock()
    result = _cmd_competitor_gaps(state, ["/competitor_gaps", "add", "any"])
    assert result is False


def test_cmd_competitor_gaps_unknown_subcommand():
    from fr_cli.repl.commands.competitor_gaps import _cmd_competitor_gaps
    state = MagicMock()
    result = _cmd_competitor_gaps(state, ["/competitor_gaps", "wat"])
    assert result is False
