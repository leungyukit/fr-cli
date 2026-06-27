"""Plan UI 彩色渲染测试"""
import os
import unittest


class TestPlanUIRender(unittest.TestCase):
    def setUp(self):
        # 强制无颜色输出,便于断言
        os.environ["NO_COLOR"] = "1"

    def test_render_plan_beautiful(self):
        from fr_cli.core.plan_ui import render_plan_beautiful
        plan = {
            "goal": "测试目标",
            "summary": "测试摘要",
            "steps": [
                {"tool": "read_file", "description": "读 README",
                 "params": {"path": "README.md"}},
                {"tool": "shell", "description": "跑测试",
                 "params": {"command": "pytest"}},
            ],
        }
        out = render_plan_beautiful(plan, lang="zh", use_color=False)
        self.assertIn("执行计划", out)
        self.assertIn("测试目标", out)
        self.assertIn("read_file", out)
        self.assertIn("shell", out)
        self.assertIn("[1/2]", out)
        self.assertIn("[2/2]", out)

    def test_render_plan_en(self):
        from fr_cli.core.plan_ui import render_plan_beautiful
        plan = {
            "goal": "Test goal",
            "steps": [{"tool": "read_file", "description": "Read README"}],
        }
        out = render_plan_beautiful(plan, lang="en", use_color=False)
        self.assertIn("Execution Plan", out)
        self.assertIn("Test goal", out)
        self.assertIn("Please approve", out)

    def test_render_plan_empty_steps(self):
        from fr_cli.core.plan_ui import render_plan_beautiful
        plan = {"goal": "Empty"}
        out = render_plan_beautiful(plan, use_color=False)
        self.assertIn("Empty", out)

    def test_render_plan_long_param(self):
        from fr_cli.core.plan_ui import render_plan_beautiful
        plan = {
            "goal": "Long",
            "steps": [{
                "tool": "test",
                "params": {"path": "x" * 200},
            }],
        }
        out = render_plan_beautiful(plan, use_color=False)
        self.assertIn("...", out)


class TestExecutionProgress(unittest.TestCase):
    def setUp(self):
        os.environ["NO_COLOR"] = "1"

    def test_progress_completed(self):
        from fr_cli.core.plan_ui import render_execution_progress
        out = render_execution_progress(3, 5, "search_web", "completed", use_color=False)
        self.assertIn("[3/5]", out)
        self.assertIn("search_web", out)
        self.assertIn("完成", out)
        self.assertIn("60%", out)

    def test_progress_running(self):
        from fr_cli.core.plan_ui import render_execution_progress
        out = render_execution_progress(1, 4, "shell", "running", use_color=False)
        self.assertIn("执行中", out)
        self.assertIn("25%", out)

    def test_progress_failed(self):
        from fr_cli.core.plan_ui import render_execution_progress
        out = render_execution_progress(2, 3, "test", "failed", use_color=False)
        self.assertIn("失败", out)

    def test_progress_with_result(self):
        from fr_cli.core.plan_ui import render_execution_progress
        out = render_execution_progress(
            1, 1, "test", "completed",
            result_text="Success line\nMore details", use_color=False,
        )
        self.assertIn("Success line", out)


class TestExecutionSummary(unittest.TestCase):
    def setUp(self):
        os.environ["NO_COLOR"] = "1"

    def test_summary_all_success(self):
        from fr_cli.core.plan_ui import render_execution_summary
        results = [(True, "成功 A"), (True, "成功 B")]
        plan = {
            "steps": [
                {"tool": "step_a"}, {"tool": "step_b"},
            ],
        }
        out = render_execution_summary(results, plan, lang="zh")
        self.assertIn("执行完成", out)
        self.assertIn("2 / 2", out)
        self.assertIn("完美执行", out)

    def test_summary_partial_failure(self):
        from fr_cli.core.plan_ui import render_execution_summary
        results = [(True, "OK"), (False, "失败")]
        plan = {"steps": [{"tool": "a"}, {"tool": "b"}]}
        out = render_execution_summary(results, plan, lang="zh")
        self.assertIn("1 / 2", out)
        self.assertIn("失败", out)
        self.assertIn("⚠️", out)

    def test_summary_all_failed(self):
        from fr_cli.core.plan_ui import render_execution_summary
        results = [(False, "x"), (False, "y")]
        plan = {"steps": [{"tool": "a"}, {"tool": "b"}]}
        out = render_execution_summary(results, plan, lang="zh")
        self.assertIn("0 / 2", out)

    def test_summary_en(self):
        from fr_cli.core.plan_ui import render_execution_summary
        results = [(True, "OK")]
        plan = {"steps": [{"tool": "a"}]}
        out = render_execution_summary(results, plan, lang="en")
        self.assertIn("Execution Complete", out)
        self.assertIn("Success", out)


class TestStepEstimate(unittest.TestCase):
    def test_fast_tool(self):
        from fr_cli.core.plan_ui import _step_estimate
        self.assertLessEqual(_step_estimate("read_file"), 5)

    def test_slow_tool(self):
        from fr_cli.core.plan_ui import _step_estimate
        self.assertGreater(_step_estimate("ai_generate"), 5)

    def test_unknown_tool(self):
        from fr_cli.core.plan_ui import _step_estimate
        self.assertIsInstance(_step_estimate("custom_unknown_xyz"), int)


if __name__ == "__main__":
    unittest.main()