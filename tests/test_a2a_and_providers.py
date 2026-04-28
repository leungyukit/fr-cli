"""
新 Provider 和 A2A 协议测试

测试目标：
1. 验证新增的 StepFun 系列 Provider
2. 验证 A2A 协议功能
3. 验证 Agent 发现和注册功能
"""
import pytest
import time
from fr_cli.core.llm import (
    _PROVIDERS,
    create_llm_client_for,
    list_providers,
    get_provider_info,
    resolve_provider_model
)


class TestStepFunProviders:
    """测试 StepFun 相关 provider"""

    def test_stepfun_provider_exists(self):
        """验证 stepfun provider 存在"""
        assert "stepfun" in _PROVIDERS
        info = _PROVIDERS["stepfun"]
        assert info["name"] == "阶跃星辰 (StepFun)"
        assert info["default_model"] == "step-1-8k"
        assert info["base_url"] == "https://api.stepfun.com/v1"

    def test_step_1_provider_exists(self):
        """验证 step-1 provider 存在"""
        assert "step-1" in _PROVIDERS
        info = _PROVIDERS["step-1"]
        assert info["name"] == "Step-1 (阶跃星辰)"
        assert info["default_model"] == "step-1-8k"
        assert info["base_url"] == "https://api.stepfun.com/v1"

    def test_step_2_provider_exists(self):
        """验证 step-2 provider 存在"""
        assert "step-2" in _PROVIDERS
        info = _PROVIDERS["step-2"]
        assert info["name"] == "Step-2 (阶跃星辰)"
        assert info["default_model"] == "step-2-16k"
        assert info["base_url"] == "https://api.stepfun.com/v1"

    def test_step_3_provider_exists(self):
        """验证 step-3 provider 存在"""
        assert "step-3" in _PROVIDERS
        info = _PROVIDERS["step-3"]
        assert info["name"] == "Step-3 (阶跃星辰)"
        assert info["default_model"] == "step-3-auto"
        assert info["base_url"] == "https://api.stepfun.com/v1"

    def test_step_audio_provider_exists(self):
        """验证 step-audio provider 存在"""
        assert "step-audio" in _PROVIDERS
        info = _PROVIDERS["step-audio"]
        assert info["name"] == "Step-Audio (实时语音)"
        assert info["default_model"] == "step-audio-2"
        assert info["base_url"] == "https://api.stepfun.com/v1"

    def test_create_stepfun_client(self):
        """测试创建 StepFun 客户端"""
        cfg = {
            "providers": {
                "stepfun": {"key": "test-key"}
            }
        }
        client, provider, model = create_llm_client_for("stepfun", "step-1-8k", cfg)
        assert provider == "stepfun"
        assert model == "step-1-8k"
        assert client.api_key == "test-key"

    def test_create_step_3_client(self):
        """测试创建 Step-3 客户端"""
        cfg = {
            "providers": {
                "step-3": {"key": "test-key"}
            }
        }
        client, provider, model = create_llm_client_for("step-3", "step-3-auto", cfg)
        assert provider == "step-3"
        assert model == "step-3-auto"
        assert client.api_key == "test-key"


class TestStepFunProviderManagement:
    """测试 StepFun provider 管理功能"""

    def test_list_providers_includes_stepfun(self):
        """验证列表包含 StepFun provider"""
        providers = list_providers()
        provider_ids = [p["id"] for p in providers]

        assert "stepfun" in provider_ids
        assert "step-1" in provider_ids
        assert "step-2" in provider_ids
        assert "step-3" in provider_ids
        assert "step-audio" in provider_ids

    def test_get_stepfun_provider_info(self):
        """验证可以获取 StepFun provider 的信息"""
        info = get_provider_info("stepfun")
        assert info is not None
        assert info["name"] == "阶跃星辰 (StepFun)"

        info = get_provider_info("step-3")
        assert info is not None
        assert info["name"] == "Step-3 (阶跃星辰)"

    def test_resolve_stepfun_model(self):
        """测试解析 StepFun 模型"""
        provider, model = resolve_provider_model("stepfun:step-1-8k")
        assert provider == "stepfun"
        assert model == "step-1-8k"

    def test_resolve_step_3_model(self):
        """测试解析 Step-3 模型"""
        provider, model = resolve_provider_model("step-3:step-3-auto")
        assert provider == "step-3"
        assert model == "step-3-auto"


class TestA2AProtocol:
    """测试 A2A 协议功能"""

    def test_agent_info_creation(self):
        """测试 AgentInfo 创建"""
        from fr_cli.agent.a2a import AgentInfo

        agent = AgentInfo(
            name="test-agent",
            type="local",
            description="Test agent for unit testing",
            capabilities=["code_generation", "general"]
        )

        assert agent.name == "test-agent"
        assert agent.type == "local"
        assert "code_generation" in agent.capabilities
        assert agent.status == "online"

    def test_agent_info_to_dict(self):
        """测试 AgentInfo 序列化"""
        from fr_cli.agent.a2a import AgentInfo

        agent = AgentInfo(
            name="test-agent",
            type="remote",
            description="Remote test agent",
            capabilities=["web_search"]
        )

        data = agent.to_dict()
        assert data["name"] == "test-agent"
        assert data["type"] == "remote"
        assert "web_search" in data["capabilities"]

    def test_agent_info_from_dict(self):
        """测试 AgentInfo 反序列化"""
        from fr_cli.agent.a2a import AgentInfo

        data = {
            "name": "test-agent",
            "type": "local",
            "description": "Test agent",
            "capabilities": ["general"]
        }

        agent = AgentInfo.from_dict(data)
        assert agent.name == "test-agent"
        assert agent.type == "local"

    def test_task_request_creation(self):
        """测试 TaskRequest 创建"""
        from fr_cli.agent.a2a import TaskRequest

        task = TaskRequest(
            task_id="test-task-123",
            agent_name="test-agent",
            user_input="Do something"
        )

        assert task.task_id == "test-task-123"
        assert task.agent_name == "test-agent"
        assert task.user_input == "Do something"
        assert task.timeout == 300

    def test_task_result_creation(self):
        """测试 TaskResult 创建"""
        from fr_cli.agent.a2a import TaskResult, TaskStatus

        result = TaskResult(
            task_id="test-task-123",
            status=TaskStatus.COMPLETED,
            result="Success"
        )

        assert result.task_id == "test-task-123"
        assert result.status == TaskStatus.COMPLETED
        assert result.result == "Success"

    def test_task_result_to_dict(self):
        """测试 TaskResult 序列化"""
        from fr_cli.agent.a2a import TaskResult, TaskStatus

        result = TaskResult(
            task_id="test-task-123",
            status=TaskStatus.FAILED,
            error="Test error"
        )

        data = result.to_dict()
        assert data["task_id"] == "test-task-123"
        assert data["status"] == "failed"

    def test_agent_registry_singleton(self):
        """测试 AgentRegistry 单例模式"""
        from fr_cli.agent.a2a import AgentRegistry

        registry1 = AgentRegistry()
        registry2 = AgentRegistry()

        assert registry1 is registry2

    def test_agent_registry_register(self):
        """测试 Agent 注册"""
        from fr_cli.agent.a2a import AgentRegistry, AgentInfo

        registry = AgentRegistry()
        agent = AgentInfo(
            name="test-register-agent",
            type="local",
            description="Test agent for registry",
            capabilities=["general"]
        )

        result = registry.register(agent)
        assert result is True

        retrieved = registry.get_agent("test-register-agent")
        assert retrieved is not None
        assert retrieved.name == "test-register-agent"

    def test_agent_registry_unregister(self):
        """测试 Agent 取消注册"""
        from fr_cli.agent.a2a import AgentRegistry, AgentInfo

        registry = AgentRegistry()
        agent = AgentInfo(
            name="test-unregister-agent",
            type="local",
            description="Test agent for unregister",
            capabilities=["general"]
        )

        registry.register(agent)
        result = registry.unregister("test-unregister-agent")
        assert result is True

        retrieved = registry.get_agent("test-unregister-agent")
        assert retrieved is None

    def test_agent_registry_list_agents(self):
        """测试列出所有 Agent"""
        from fr_cli.agent.a2a import AgentRegistry, AgentInfo

        registry = AgentRegistry()

        agents_before = len(registry.list_agents())

        agent = AgentInfo(
            name="test-list-agent",
            type="local",
            description="Test agent for listing",
            capabilities=["code_generation"]
        )
        registry.register(agent)

        agents = registry.list_agents()
        assert len(agents) >= agents_before

    def test_agent_registry_find_best_agent(self):
        """测试查找最佳 Agent"""
        from fr_cli.agent.a2a import AgentRegistry, AgentInfo

        registry = AgentRegistry()

        agent = AgentInfo(
            name="test-code-agent",
            type="local",
            description="A code generation agent",
            capabilities=["code_generation", "code_review"]
        )
        registry.register(agent)

        best = registry.find_best_agent(
            task_description="Generate Python code for me",
            required_capabilities=["code_generation"]
        )

        if best:
            assert "code_generation" in best.capabilities


class TestA2AClient:
    """测试 A2A 客户端功能"""

    def test_a2a_client_creation(self):
        """测试 A2AClient 创建"""
        from fr_cli.agent.a2a import A2AClient

        client = A2AClient()
        assert client is not None
        assert client.registry is not None

    def test_submit_task(self):
        """测试提交任务"""
        from fr_cli.agent.a2a import A2AClient

        client = A2AClient()
        task_id = client.submit_task(
            agent_name="test-agent",
            user_input="Test task"
        )

        assert task_id is not None
        assert len(task_id) > 0

    def test_submit_task_with_context(self):
        """测试带上下文提交任务"""
        from fr_cli.agent.a2a import A2AClient

        client = A2AClient()
        task_id = client.submit_task(
            agent_name="test-agent",
            user_input="Test task with context",
            context={"key": "value", "number": 42}
        )

        assert task_id is not None


class TestA2AServer:
    """测试 A2A 服务器功能"""

    def test_a2a_server_creation(self):
        """测试 A2AServer 创建"""
        from fr_cli.agent.a2a import A2AServer

        server = A2AServer(agent_name="test-server", agent_module=None)
        assert server.agent_name == "test-server"
        assert server.host == "127.0.0.1"

    def test_default_port_generation(self):
        """测试默认端口生成"""
        from fr_cli.agent.a2a import A2AServer

        server1 = A2AServer(agent_name="agent-alpha", agent_module=None)
        server2 = A2AServer(agent_name="agent-beta", agent_module=None)

        assert server1.port != server2.port
        assert 8000 <= server1.port <= 9000


class TestDiscoverAllAgents:
    """测试 Agent 发现功能"""

    def test_discover_local_agents(self):
        """测试发现本地 Agent"""
        from fr_cli.agent.a2a import _discover_local_agents

        agents = _discover_local_agents()
        assert isinstance(agents, list)

    def test_discover_all_agents(self):
        """测试发现所有 Agent"""
        from fr_cli.agent.a2a import discover_all_agents

        agents = discover_all_agents()
        assert isinstance(agents, list)

        for agent in agents:
            assert "name" in agent
            assert "type" in agent
            assert "description" in agent
            assert "capabilities" in agent
            assert "status" in agent


class TestCapabilityInference:
    """测试能力推断功能"""

    def test_infer_capabilities_code(self):
        """测试推断代码能力"""
        from fr_cli.agent.a2a import _infer_capabilities

        agent = {
            "persona": "I am a code generation expert",
            "skills": "Python, JavaScript, React"
        }

        caps = _infer_capabilities(agent)
        assert "code_generation" in caps

    def test_infer_capabilities_data(self):
        """测试推断数据能力"""
        from fr_cli.agent.a2a import _infer_capabilities

        agent = {
            "persona": "数据分析专家",
            "skills": "SQL, Pandas, 数据可视化"
        }

        caps = _infer_capabilities(agent)
        assert "data_analysis" in caps


if __name__ == "__main__":
    pytest.main([__file__, "-v"])