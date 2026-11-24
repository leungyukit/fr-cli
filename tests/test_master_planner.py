"""MasterAgent 强制规划步 + /mode plan 可达性 测试

固化两个用户实测问题:
1. ReAct 循环"拆解"靠模型自觉: 回复不带工具调用块就静默退化成一问一答
   (session.json 实证 17 个任务 11 个零工具调用)。方向1: 任务型输入先出
   N 步计划再进入循环, 本测试锁门控规则与规划调用契约。
2. /mode 在 MasterAgent 开启时被整体禁用, 计划模式日常摸不到。方向3b:
   /mode plan 始终允许(路由层 plan 优先于 master), cot/tot/react 仍禁用。
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from fr_cli.agent.master_planner import MasterAgentPlannerMixin


class _PlannerStub(MasterAgentPlannerMixin):
    """只提供规划步需要的最小 surface(不拉起整个 MasterAgent)"""

    def __init__(self, lang="zh"):
        self.state = SimpleNamespace(
            client=MagicMock(), model_name="test-model", lang=lang,
        )
        self.session = {}

    def _build_tools_desc(self):
        return "- search_web: 搜索\n- write_file: 写文件"


class TestNeedsPlanningGate:
    """门控: 本地启发式, 零 LLM 成本"""

    def setup_method(self):
        self.p = _PlannerStub()

    @pytest.mark.parametrize("text", [
        "你好",
        "在吗",
        "你好，请用一句话介绍你自己",
        "fr-cli 是什么",
        "我想做一个微博自动发布功能，要如何实现？",
        "如果我要开发一个这样的功能，你可以怎么帮我做？",
        "思维模式都有哪些区别",
    ])
    def test_consultative_inputs_skip_planning(self, text):
        """问候/纯咨询直接回答, 不给"你好"画计划、不白搭调用"""
        assert self.p._needs_planning(text) is False

    @pytest.mark.parametrize("text", [
        "帮我制定一个硅胶厨具选品调研计划，三步即可",
        "帮我搜索2025年硅胶厨具的市场趋势并汇总成报告",
        "把桌面上的选品表格整理一下，按利润率排序然后写成一个新文件",
        "请帮我分析这个竞品的价格带并生成图表",
    ])
    def test_imperative_inputs_force_planning(self, text):
        """明确任务动词: 强制走规划步"""
        assert self.p._needs_planning(text) is True

    def test_long_input_defaults_to_task(self):
        """无任何标记的长文本(>=40 字)默认按任务处理"""
        long_text = "采购" * 25  # 50 字, 无咨询词也无任务动词
        assert len(long_text) >= 40
        assert self.p._needs_planning(long_text) is True

    def test_short_input_never_plans(self):
        assert self.p._needs_planning("") is False
        assert self.p._needs_planning("   ") is False
        assert self.p._needs_planning("帮我") is False  # <10 字


class TestPlanForTask:
    """规划调用: silent + 容错解析 + 失败回退"""

    PLAN_JSON = (
        '{"goal": "硅胶厨具选品调研", "summary": "先搜再抓取再成文", '
        '"steps": [{"description": "搜索市场趋势", "tool": "search_web", '
        '"params": {"query": "silicone 2025"}, "reasoning": "打底"}, '
        '{"description": "写报告", "tool": null, "params": {}, "reasoning": "沉淀"}]}'
    )

    def test_plan_parsed_and_normalized(self):
        """正常路径: 解析出计划, steps 规范化(tool null → None)"""
        p = _PlannerStub()
        with patch("fr_cli.core.stream.stream_cnt") as m:
            m.return_value = (self.PLAN_JSON, {}, 0.1, False)
            plan = p._plan_for_task("帮我制定一个硅胶厨具选品调研计划", lang="zh")
        assert plan is not None
        assert plan["goal"] == "硅胶厨具选品调研"
        assert len(plan["steps"]) == 2
        assert plan["steps"][0]["tool"] == "search_web"
        assert plan["steps"][1]["tool"] is None
        # silent=True: 规划过程的思维链不刷屏
        assert m.call_args.kwargs.get("silent") is True

    def test_cot_wrapped_plan_still_parses(self):
        """live 失败形态: CoT 前后文包裹的 JSON 也能捞出计划"""
        p = _PlannerStub()
        cot = "Let me think... need steps:\n" + self.PLAN_JSON + "\nDone."
        with patch("fr_cli.core.stream.stream_cnt") as m:
            m.return_value = (cot, {}, 0.1, False)
            plan = p._plan_for_task("帮我制定一个硅胶厨具选品调研计划", lang="zh")
        assert plan is not None and plan["steps"][0]["tool"] == "search_web"

    def test_unparseable_returns_none(self, capsys):
        """解析失败: 返回 None(调用方回退直连) + 打印一行提示不静默"""
        p = _PlannerStub()
        with patch("fr_cli.core.stream.stream_cnt") as m:
            m.return_value = ("完全不是JSON", {}, 0.1, False)
            plan = p._plan_for_task("帮我制定一个硅胶厨具选品调研计划", lang="zh")
        assert plan is None
        out = capsys.readouterr().out
        assert "规划解析失败" in out

    def test_interrupted_returns_none(self):
        """用户中断规划: 返回 None, 不报错"""
        p = _PlannerStub()
        with patch("fr_cli.core.stream.stream_cnt") as m:
            m.return_value = ("", {}, 0.1, True)
            assert p._plan_for_task("帮我制定一个硅胶厨具选品调研计划", lang="zh") is None


class TestModePlanReachableUnderMaster:
    """方向3b: /mode plan 与 MasterAgent 解耦"""

    def _state(self, master_enabled):
        calls = {"modes": []}

        def update_thinking_mode(mode):
            calls["modes"].append(mode)

        return SimpleNamespace(
            master_agent=SimpleNamespace(is_enabled=lambda: master_enabled),
            thinking_mode="direct",
            ui_mode="dev",
            update_thinking_mode=update_thinking_mode,
            _calls=calls,
        ), calls

    def test_plan_mode_allowed_under_master(self, capsys):
        """master 开启时 /mode plan 照常生效(路由层 plan 优先于 master)"""
        from fr_cli.repl.commands.base import _cmd_mode

        state, calls = self._state(master_enabled=True)
        _cmd_mode(state, ["/mode", "plan"])
        assert calls["modes"] == ["plan"]
        assert "无效" not in capsys.readouterr().out

    def test_cot_tot_react_still_blocked_under_master(self, capsys):
        """master 开启时 cot/tot/react 仍禁用(由其 ReAct 循环自主管理)"""
        from fr_cli.repl.commands.base import _cmd_mode

        for mode in ("cot", "tot", "react"):
            state, calls = self._state(master_enabled=True)
            _cmd_mode(state, ["/mode", mode])
            assert calls["modes"] == []
        out = capsys.readouterr().out
        assert "计划模式" in out  # 提示里告知 plan 始终可用

    def test_all_modes_allowed_without_master(self):
        """master 关闭时全部思维模式可切换(不回退)"""
        from fr_cli.repl.commands.base import _cmd_mode

        state, calls = self._state(master_enabled=False)
        _cmd_mode(state, ["/mode", "cot"])
        assert calls["modes"] == ["cot"]
