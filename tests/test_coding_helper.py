"""
代码助手功能测试
"""

import pytest


class TestCodeUnderstanding:
    """测试代码理解系统"""

    def test_language_detection(self):
        """测试语言识别"""
        from fr_cli.agent.coding_helper import CodeUnderstanding

        cu = CodeUnderstanding(".")
        lang = cu._get_language('.py')
        assert lang == 'Python'

        lang = cu._get_language('.js')
        assert lang == 'JavaScript'

        lang = cu._get_language('.go')
        assert lang == 'Go'

    def test_framework_detection(self):
        """测试框架检测"""
        from fr_cli.agent.coding_helper import CodeUnderstanding

        cu = CodeUnderstanding(".")
        fw = cu._detect_framework('package.json', '/path')
        assert fw == 'Node.js'

        fw = cu._detect_framework('requirements.txt', '/path')
        assert fw == 'Python'

    def test_analyze_structure(self):
        """测试结构分析"""
        from fr_cli.agent.coding_helper import CodeUnderstanding
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建测试文件
            with open(os.path.join(tmpdir, 'test.py'), 'w') as f:
                f.write('import os\nprint("test")')

            cu = CodeUnderstanding(tmpdir)
            structure = cu.analyze_structure()

            assert 'Python' in structure['languages']
            assert len(structure['files']) > 0


class TestCodeReviewer:
    """测试代码审查"""

    def test_review_finding_creation(self):
        """测试审查发现创建"""
        from fr_cli.agent.coding_helper import ReviewFinding

        finding = ReviewFinding(
            severity='high',
            file='test.py',
            line=10,
            message='Test issue',
            suggestion='Test suggestion'
        )

        assert finding.severity == 'high'
        assert finding.file == 'test.py'

    def test_format_report_empty(self):
        """测试空报告格式化"""
        from fr_cli.agent.coding_helper import CodeReviewer

        reviewer = CodeReviewer()
        report = reviewer.format_report([])
        assert '未发现问题' in report


class TestLearningTutor:
    """测试学习辅导"""

    def test_explain_oop(self):
        """测试解释 OOP"""
        from fr_cli.agent.coding_helper import LearningTutor

        tutor = LearningTutor()
        result = tutor.explain_concept('oop')

        assert '封装' in result
        assert '继承' in result
        assert '多态' in result

    def test_explain_closure(self):
        """测试解释闭包"""
        from fr_cli.agent.coding_helper import LearningTutor

        tutor = LearningTutor()
        result = tutor.explain_concept('closure')

        assert '闭包' in result

    def test_generate_decorator_example(self):
        """测试生成装饰器示例"""
        from fr_cli.agent.coding_helper import LearningTutor

        tutor = LearningTutor()
        result = tutor.generate_example('decorator')

        assert '装饰器' in result or '@' in result

    def test_learning_path_beginner(self):
        """测试初级路径"""
        from fr_cli.agent.coding_helper import LearningTutor

        tutor = LearningTutor()
        path = tutor.suggest_learning_path('beginner')

        assert 'Python' in path or 'JavaScript' in path


class TestGitIntegration:
    """测试 Git 集成"""

    def test_status_command(self):
        """测试 git status"""
        from fr_cli.agent.coding_helper import GitIntegration

        git = GitIntegration()
        status = git.get_status()
        assert isinstance(status, str)

    def test_get_branches(self):
        """测试获取分支"""
        from fr_cli.agent.coding_helper import GitIntegration

        git = GitIntegration()
        branches = git.get_branches()
        assert isinstance(branches, list)


class TestMultiFileEditor:
    """测试多文件编辑器"""

    def test_add_edit(self):
        """测试添加编辑"""
        from fr_cli.agent.coding_helper import MultiFileEditor

        editor = MultiFileEditor(dry_run=True)
        editor.add_edit('test.txt', 'create', 'content')
        editor.add_edit('main.py', 'edit', 'new content')

        assert len(editor.edits) == 2
        assert editor.edits[0].action == 'create'
        assert editor.edits[1].action == 'edit'


class TestPlanExecution:
    """测试计划执行系统"""

    def test_create_plan_analysis(self):
        """测试创建分析计划"""
        from fr_cli.agent.coding_helper import PlanExecutionSystem

        pes = PlanExecutionSystem()
        steps = pes.create_plan("分析代码")

        assert len(steps) >= 1
        assert steps[0].action == 'analyze'

    def test_create_plan_edit(self):
        """测试创建编辑计划"""
        from fr_cli.agent.coding_helper import PlanExecutionSystem

        pes = PlanExecutionSystem()
        steps = pes.create_plan("修改代码")

        assert any(s.action == 'edit' for s in steps)

    def test_approve_step(self):
        """测试批准步骤"""
        from fr_cli.agent.coding_helper import PlanExecutionSystem

        pes = PlanExecutionSystem()
        pes.create_plan("分析代码")

        assert pes.approve_step(1)
        assert pes.steps[0].approved

    def test_get_next_pending_step(self):
        """测试获取待执行步骤"""
        from fr_cli.agent.coding_helper import PlanExecutionSystem

        pes = PlanExecutionSystem()
        pes.create_plan("分析代码")
        pes.approve_step(1)

        next_step = pes.get_next_pending_step()
        assert next_step is not None
        assert next_step.step_id == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
