"""
新功能测试 - 图片模型、并行执行、工作流系统

测试目标：
1. 图片模型配置和使用
2. 终端图片显示
3. 并行任务执行
4. Agent 工作流系统
"""

import pytest
import asyncio


class TestImageModelConfig:
    """测试图片模型配置"""

    def test_image_config_singleton(self):
        """测试 ImageModelConfig 单例"""
        from fr_cli.agent.image_and_parallel import ImageModelConfig

        config1 = ImageModelConfig()
        config2 = ImageModelConfig()

        assert config1 is config2

    def test_list_providers(self):
        """测试列出图片提供商"""
        from fr_cli.agent.image_and_parallel import ImageModelConfig

        config = ImageModelConfig()
        providers = config.list_providers()

        assert len(providers) >= 4  # 至少有 4 个内置提供商

        provider_names = [p["name"] for p in providers]
        assert any("智谱" in name or "CogView" in name for name in provider_names)
        assert any("MiniMax" in name for name in provider_names)

    def test_get_provider(self):
        """测试获取提供商"""
        from fr_cli.agent.image_and_parallel import ImageModelConfig

        config = ImageModelConfig()
        provider = config.get_provider()

        assert provider is not None
        assert provider.name is not None


class TestImageGenerator:
    """测试图片生成器"""

    def test_image_generator_init(self):
        """测试图片生成器初始化"""
        from fr_cli.agent.image_and_parallel import ImageGenerator, ImageModelConfig

        config = ImageModelConfig()
        generator = ImageGenerator()

        assert generator.provider is not None

    def test_generate_with_empty_prompt(self):
        """测试空 prompt 处理"""
        from fr_cli.agent.image_and_parallel import ImageGenerator

        generator = ImageGenerator()
        result = generator.generate("")

        # 应该返回错误而不是崩溃
        assert "success" in result or "error" in result


class TestTerminalImageDisplay:
    """测试终端图片显示"""

    def test_detect_display_method(self):
        """测试显示方法检测"""
        from fr_cli.agent.image_and_parallel import TerminalImageDisplay

        method = TerminalImageDisplay._detect_method()
        assert method in ["kitty", "iterm2", "braille", "ascii"]


class TestParallelExecutor:
    """测试并行执行器"""

    def test_parallel_executor_init(self):
        """测试并行执行器初始化"""
        from fr_cli.agent.image_and_parallel import ParallelExecutor

        executor = ParallelExecutor(max_workers=3)

        assert executor.max_workers == 3
        assert len(executor.tasks) == 0
        assert len(executor.results) == 0

    def test_submit_task(self):
        """测试提交任务"""
        from fr_cli.agent.image_and_parallel import ParallelExecutor

        executor = ParallelExecutor(max_workers=2)

        def sample_task():
            return "result"

        task_id = executor.submit("test_task", "Test Task", sample_task)

        assert task_id == "test_task"
        assert "test_task" in executor.results

        executor.shutdown()

    def test_get_status(self):
        """测试获取状态"""
        from fr_cli.agent.image_and_parallel import ParallelExecutor

        executor = ParallelExecutor(max_workers=2)
        status = executor.get_status()

        assert "max_workers" in status
        assert "running" in status
        assert "completed" in status
        assert "total" in status

        executor.shutdown()


class TestAsyncParallelExecutor:
    """测试异步并行执行器"""

    def test_async_executor_init(self):
        """测试异步执行器初始化"""
        from fr_cli.agent.image_and_parallel import AsyncParallelExecutor

        executor = AsyncParallelExecutor()

        assert len(executor.tasks) == 0
        assert len(executor.results) == 0


class TestWorkflowEngine:
    """测试工作流引擎"""

    def test_workflow_engine_init(self):
        """测试工作流引擎初始化"""
        from fr_cli.agent.workflow_system import WorkflowEngine

        engine = WorkflowEngine()

        assert len(engine.nodes) == 0
        assert len(engine.edges) == 0

    def test_load_workflow(self):
        """测试加载工作流定义"""
        from fr_cli.agent.workflow_system import WorkflowEngine

        engine = WorkflowEngine()

        workflow_def = {
            "name": "test_workflow",
            "nodes": [
                {"id": "node1", "name": "Agent 1", "type": "agent", "agent_name": "test-agent"},
                {"id": "node2", "name": "Agent 2", "type": "agent", "agent_name": "test-agent-2"}
            ],
            "edges": [
                {"source": "node1", "target": "node2"}
            ]
        }

        engine.load_workflow(workflow_def)

        assert len(engine.nodes) == 2
        assert len(engine.edges) == 1
        assert "node1" in engine.nodes
        assert "node2" in engine.nodes

    def test_get_outgoing_edges(self):
        """测试获取出边"""
        from fr_cli.agent.workflow_system import WorkflowEngine, EdgeType

        engine = WorkflowEngine()

        engine.nodes["n1"] = type('Node', (), {'id': 'n1'})()
        engine.nodes["n2"] = type('Node', (), {'id': 'n2'})()
        engine.edges = [
            type('Edge', (), {'source_id': 'n1', 'target_id': 'n2', 'edge_type': EdgeType.NORMAL})()
        ]

        outgoing = engine.get_outgoing_edges("n1")
        assert len(outgoing) == 1
        assert outgoing[0].target_id == "n2"

    def test_get_incoming_edges(self):
        """测试获取入边"""
        from fr_cli.agent.workflow_system import WorkflowEngine, EdgeType

        engine = WorkflowEngine()

        engine.nodes["n1"] = type('Node', (), {'id': 'n1'})()
        engine.nodes["n2"] = type('Node', (), {'id': 'n2'})()
        engine.edges = [
            type('Edge', (), {'source_id': 'n1', 'target_id': 'n2', 'edge_type': EdgeType.NORMAL})()
        ]

        incoming = engine.get_incoming_edges("n2")
        assert len(incoming) == 1
        assert incoming[0].source_id == "n1"


class TestWorkflowManager:
    """测试工作流管理器"""

    def test_workflow_manager_init(self):
        """测试工作流管理器初始化"""
        from fr_cli.agent.workflow_system import WorkflowManager

        manager = WorkflowManager()

        assert len(manager.workflows) == 0

    def test_create_workflow(self):
        """测试创建工作流"""
        from fr_cli.agent.workflow_system import WorkflowManager

        manager = WorkflowManager()

        workflow_def = {
            "name": "test",
            "nodes": [
                {"id": "n1", "name": "Node 1", "type": "agent", "agent_name": "agent1"}
            ],
            "edges": []
        }

        engine = manager.create_workflow("test_workflow", workflow_def)

        assert "test_workflow" in manager.workflows
        assert engine is not None

    def test_list_workflows(self):
        """测试列出工作流"""
        from fr_cli.agent.workflow_system import WorkflowManager

        manager = WorkflowManager()

        workflow_def = {
            "nodes": [{"id": "n1", "name": "N1", "type": "agent"}],
            "edges": []
        }

        manager.create_workflow("wf1", workflow_def)
        manager.create_workflow("wf2", workflow_def)

        workflows = manager.list_workflows()
        assert len(workflows) == 2

    def test_get_workflow(self):
        """测试获取工作流"""
        from fr_cli.agent.workflow_system import WorkflowManager

        manager = WorkflowManager()

        workflow_def = {
            "nodes": [{"id": "n1", "name": "N1", "type": "agent"}],
            "edges": []
        }

        manager.create_workflow("test_wf", workflow_def)
        engine = manager.get_workflow("test_wf")

        assert engine is not None

    def test_visualize_workflow(self):
        """测试可视化工作流"""
        from fr_cli.agent.workflow_system import WorkflowManager

        manager = WorkflowManager()

        workflow_def = {
            "nodes": [
                {"id": "n1", "name": "Start", "type": "agent"},
                {"id": "n2", "name": "End", "type": "agent"}
            ],
            "edges": [{"source": "n1", "target": "n2"}]
        }

        manager.create_workflow("viz_test", workflow_def)
        result = manager.visualize_workflow("viz_test")

        assert "Start" in result
        assert "End" in result


class TestWorkflowExecutor:
    """测试工作流执行器"""

    def test_workflow_executor_init(self):
        """测试工作流执行器初始化"""
        from fr_cli.agent.workflow_system import WorkflowExecutor

        executor = WorkflowExecutor()

        assert executor.manager is not None


class TestWorkflowMonitor:
    """测试工作流监控器"""

    def test_monitor_init(self):
        """测试监控器初始化"""
        from fr_cli.agent.workflow_system import WorkflowMonitor

        monitor = WorkflowMonitor()

        assert len(monitor.active_executions) == 0

    def test_get_execution_status_not_found(self):
        """测试获取不存在的执行状态"""
        from fr_cli.agent.workflow_system import WorkflowMonitor

        monitor = WorkflowMonitor()
        status = monitor.get_execution_status("nonexistent")

        assert status is None

    def test_list_active_executions(self):
        """测试列出活跃执行"""
        from fr_cli.agent.workflow_system import WorkflowMonitor

        monitor = WorkflowMonitor()
        executions = monitor.list_active_executions()

        assert isinstance(executions, list)


class TestCreateWorkflowFromTemplate:
    """测试从模板创建工作流"""

    def test_code_review_template(self):
        """测试代码审查模板"""
        from fr_cli.agent.workflow_system import create_workflow_from_template

        template = create_workflow_from_template("code_review")

        assert template is not None
        assert "nodes" in template
        assert "edges" in template
        assert len(template["nodes"]) == 3

    def test_data_analysis_template(self):
        """测试数据分析模板"""
        from fr_cli.agent.workflow_system import create_workflow_from_template

        template = create_workflow_from_template("data_analysis")

        assert template is not None
        assert len(template["nodes"]) == 4

    def test_multi_agent_chat_template(self):
        """测试多 Agent 协作模板"""
        from fr_cli.agent.workflow_system import create_workflow_from_template

        template = create_workflow_from_template("multi_agent_chat")

        assert template is not None
        assert len(template["nodes"]) == 4

    def test_unknown_template(self):
        """测试未知模板"""
        from fr_cli.agent.workflow_system import create_workflow_from_template

        template = create_workflow_from_template("unknown_template")

        assert template == {}


class TestPowerfulAgentTemplate:
    """测试强大 Agent 模板"""

    def test_tool_registry_singleton(self):
        """测试工具注册表单例"""
        from fr_cli.agent.builtins.powerful_agent_template import ToolRegistry

        reg1 = ToolRegistry()
        reg2 = ToolRegistry()

        assert reg1 is reg2

    def test_list_tools(self):
        """测试列出工具"""
        from fr_cli.agent.builtins.powerful_agent_template import ToolRegistry

        registry = ToolRegistry()
        tools = registry.list_tools()

        assert len(tools) >= 10  # 至少有 10 个内置工具

        tool_names = [t["name"] for t in tools]
        assert "read_file" in tool_names
        assert "web_search" in tool_names
        assert "call_agent" in tool_names

    def test_memory_system_init(self):
        """测试记忆系统初始化"""
        from fr_cli.agent.builtins.powerful_agent_template import MemorySystem

        memory = MemorySystem("test_agent")

        assert memory.agent_name == "test_agent"
        assert len(memory.short_term) == 0
        assert len(memory.long_term) == 0

    def test_add_memory(self):
        """测试添加记忆"""
        from fr_cli.agent.builtins.powerful_agent_template import MemorySystem

        memory = MemorySystem("test")
        memory.add_memory("测试内容", importance=0.5, source="test")

        assert len(memory.short_term) == 1

    def test_recall(self):
        """测试回忆"""
        from fr_cli.agent.builtins.powerful_agent_template import MemorySystem

        memory = MemorySystem("test")
        memory.add_memory("Python 编程")
        memory.add_memory("JavaScript 开发")

        results = memory.recall("Python")
        assert len(results) >= 1

    def test_evolution_system(self):
        """测试进化系统"""
        from fr_cli.agent.builtins.powerful_agent_template import EvolutionSystem

        evolution = EvolutionSystem("test")

        evolution.record_success("任务1", "方法A", "结果")
        evolution.record_success("任务2", "方法B", "结果")

        stats = evolution.get_evolution_stats()
        assert stats["successes"] == 2
        assert stats["success_rate"] == "100.0%"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])