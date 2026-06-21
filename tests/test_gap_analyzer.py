"""
能力缺口分析器测试
"""
import json
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def sample_tools():
    return [
        {"name": "read_file", "description": "读取文件", "aliases": ["/read"], "triggers": ["读取", "read"]},
        {"name": "search_web", "description": "网页搜索", "aliases": ["/web"], "triggers": ["搜索", "search"]},
    ]


class TestKeywordMatching:
    """测试关键词命中判定"""

    def test_known_tool_covered(self, sample_tools):
        from fr_cli.dynamic_builder.gap_analyzer import CapabilityGapAnalyzer

        analyzer = CapabilityGapAnalyzer(keyword_threshold=0.3)
        report = analyzer.analyze("读取 README.md", sample_tools)
        assert report["gap"] is False
        assert "read_file" in report["reasoning"]

    def test_unknown_tool_gap_no_llm(self, sample_tools):
        from fr_cli.dynamic_builder.gap_analyzer import CapabilityGapAnalyzer

        analyzer = CapabilityGapAnalyzer(keyword_threshold=0.3)
        report = analyzer.analyze("把图片转换成 ASCII 艺术", sample_tools)
        # 无 state/model，退化为保守缺口判断
        assert report["gap"] is True


class TestLLMFallback:
    """测试 LLM 二次判断"""

    @patch("fr_cli.dynamic_builder.gap_analyzer.stream_cnt")
    def test_llm_reports_covered(self, mock_stream, sample_tools):
        from fr_cli.dynamic_builder.gap_analyzer import CapabilityGapAnalyzer

        mock_stream.return_value = (
            json.dumps({"gap": False, "confidence": 0.9, "suggested_tool_name": "", "reasoning": "可用 search_web 找资料"}),
            {}, 0.1, False,
        )
        state = SimpleNamespace(client=MagicMock(), model_name="glm-4-flash", lang="zh")
        analyzer = CapabilityGapAnalyzer(keyword_threshold=0.3)
        report = analyzer.analyze("查一下最新新闻", sample_tools, state=state)
        assert report["gap"] is False
        assert report["confidence"] == pytest.approx(0.9)

    @patch("fr_cli.dynamic_builder.gap_analyzer.stream_cnt")
    def test_llm_reports_gap(self, mock_stream, sample_tools):
        from fr_cli.dynamic_builder.gap_analyzer import CapabilityGapAnalyzer

        mock_stream.return_value = (
            json.dumps({"gap": True, "confidence": 0.8, "suggested_tool_name": "ascii_art", "reasoning": "无现成工具"}),
            {}, 0.1, False,
        )
        state = SimpleNamespace(client=MagicMock(), model_name="glm-4-flash", lang="zh")
        analyzer = CapabilityGapAnalyzer(keyword_threshold=0.3)
        report = analyzer.analyze("把图片转成 ASCII", sample_tools, state=state)
        assert report["gap"] is True
        assert report["suggested_tool_name"] == "ascii_art"


class TestBuildMissingTool:
    """测试 build_missing_tool 工具"""

    @patch("fr_cli.command.registered.dynamic_build.get_registry")
    @patch("fr_cli.dynamic_builder.build_tool")
    def test_builds_when_gap_detected(self, mock_build_tool, mock_get_registry, sample_tools):
        from fr_cli.command.registered.dynamic_build import _build_missing_tool
        from fr_cli.core.result import Result

        mock_get_registry.return_value.get_available_tools.return_value = sample_tools
        mock_build_tool.return_value = Result.ok("built ascii_tool")

        deps = SimpleNamespace(
            client=MagicMock(), model_name="glm-4-flash", lang="zh",
            cfg={}, vfs=None, security=None, plugins={},
        )
        with patch("fr_cli.dynamic_builder.gap_analyzer.stream_cnt") as mock_stream:
            mock_stream.return_value = (
                json.dumps({"gap": True, "confidence": 0.9, "suggested_tool_name": "ascii_tool", "reasoning": "无工具"}),
                {}, 0.1, False,
            )
            result = _build_missing_tool(deps, requirement="把图片转成 ASCII")

        assert result.is_ok()
        assert result.unwrap()["built"] is True
        mock_build_tool.assert_called_once()

    @patch("fr_cli.command.registered.dynamic_build.get_registry")
    def test_skips_when_covered(self, mock_get_registry, sample_tools):
        from fr_cli.command.registered.dynamic_build import _build_missing_tool

        mock_get_registry.return_value.get_available_tools.return_value = sample_tools
        deps = SimpleNamespace(
            client=None, model_name=None, lang="zh",
            cfg={}, vfs=None, security=None, plugins={},
        )
        result = _build_missing_tool(deps, requirement="读取 README")
        assert result.is_ok()
        assert result.unwrap()["built"] is False
