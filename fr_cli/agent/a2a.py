"""
Agent2Agent Protocol (A2A) - Agent 互操作协议

实现 Agent 之间的互操作，支持：
1. Agent 发现与注册
2. 能力描述与匹配
3. 任务委托与执行
4. 结果返回与状态同步
"""
import json
import time
import uuid
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentCapability(Enum):
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    DATA_ANALYSIS = "data_analysis"
    WEB_SEARCH = "web_search"
    FILE_OPERATION = "file_operation"
    DATABASE = "database"
    IMAGE_PROCESSING = "image_processing"
    TEXT_GENERATION = "text_generation"
    TRANSLATION = "translation"
    GENERAL = "general"


@dataclass
class AgentInfo:
    name: str
    type: str
    description: str
    capabilities: List[str]
    endpoint: Optional[str] = None
    auth_token: Optional[str] = None
    version: str = "1.0"
    status: str = "online"
    last_heartbeat: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'AgentInfo':
        return cls(**data)


@dataclass
class TaskRequest:
    task_id: str
    agent_name: str
    user_input: str
    context: Dict[str, Any] = field(default_factory=dict)
    timeout: int = 300
    priority: int = 0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'TaskRequest':
        return cls(**data)


@dataclass
class TaskResult:
    task_id: str
    status: TaskStatus
    result: Any = None
    error: Optional[str] = None
    execution_time: float = 0.0
    completed_at: Optional[float] = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data['status'] = self.status.value if isinstance(self.status, TaskStatus) else self.status
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'TaskResult':
        if isinstance(data.get('status'), str):
            data['status'] = TaskStatus(data['status'])
        return cls(**data)


class AgentRegistry:
    """
    Agent 注册表 - 管理所有可用的 Agent
    支持本地 Agent 和远程 Agent 的注册与发现
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._agents: Dict[str, AgentInfo] = {}
        self._tasks: Dict[str, TaskResult] = {}
        self._registry_file = Path.home() / ".fr_cli_agent_registry.json"
        self._load_registry()
        self._initialized = True

    def _load_registry(self):
        """从磁盘加载注册表"""
        if self._registry_file.exists():
            try:
                data = json.loads(self._registry_file.read_text(encoding="utf-8"))
                for agent_data in data.get("agents", []):
                    agent = AgentInfo.from_dict(agent_data)
                    self._agents[agent.name] = agent
            except (json.JSONDecodeError, PermissionError):
                pass

    def _save_registry(self):
        """保存注册表到磁盘"""
        data = {
            "agents": [agent.to_dict() for agent in self._agents.values()],
            "updated_at": time.time()
        }
        try:
            self._registry_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except PermissionError:
            pass

    def register(self, agent_info: AgentInfo) -> bool:
        """注册一个 Agent"""
        self._agents[agent_info.name] = agent_info
        self._save_registry()
        return True

    def unregister(self, agent_name: str) -> bool:
        """取消注册一个 Agent"""
        if agent_name in self._agents:
            del self._agents[agent_name]
            self._save_registry()
            return True
        return False

    def get_agent(self, agent_name: str) -> Optional[AgentInfo]:
        """获取指定 Agent 的信息"""
        return self._agents.get(agent_name)

    def list_agents(self, capability: Optional[str] = None) -> List[AgentInfo]:
        """列出所有 Agent，可按能力过滤"""
        agents = list(self._agents.values())
        if capability:
            agents = [a for a in agents if capability in a.capabilities]
        return agents

    def find_best_agent(self, task_description: str, required_capabilities: List[str]) -> Optional[AgentInfo]:
        """
        根据任务描述和能力需求找到最合适的 Agent

        匹配策略：
        1. 优先匹配所有必需能力
        2. 其次匹配任务描述中的关键词
        3. 考虑 Agent 的在线状态
        """
        candidates = []

        for agent in self._agents.values():
            if agent.status != "online":
                continue

            capability_match = all(cap in agent.capabilities for cap in required_capabilities)

            keyword_score = 0
            description_lower = agent.description.lower()
            for keyword in task_description.lower().split():
                if len(keyword) > 3 and keyword in description_lower:
                    keyword_score += 1

            if capability_match or keyword_score > 0:
                score = capability_match * 10 + keyword_score
                candidates.append((score, agent))

        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1] if candidates else None

    def update_heartbeat(self, agent_name: str):
        """更新 Agent 的心跳时间"""
        if agent_name in self._agents:
            self._agents[agent_name].last_heartbeat = time.time()
            self._save_registry()

    def get_online_agents(self) -> List[AgentInfo]:
        """获取所有在线的 Agent"""
        return [a for a in self._agents.values() if a.status == "online"]


class A2AClient:
    """
    A2A 客户端 - 用于向其他 Agent 发送任务请求
    支持本地和远程 Agent 的调用
    """

    def __init__(self, registry: Optional[AgentRegistry] = None):
        self.registry = registry or AgentRegistry()
        self._pending_tasks: Dict[str, TaskRequest] = {}

    def submit_task(self, agent_name: str, user_input: str, context: Dict[str, Any] = None) -> str:
        """提交任务到指定 Agent，返回任务 ID"""
        task_id = str(uuid.uuid4())
        task = TaskRequest(
            task_id=task_id,
            agent_name=agent_name,
            user_input=user_input,
            context=context or {}
        )
        self._pending_tasks[task_id] = task
        return task_id

    def get_task_result(self, task_id: str) -> Optional[TaskResult]:
        """获取任务结果"""
        return self.registry._tasks.get(task_id)

    async def call_agent(self, agent_name: str, user_input: str, context: Dict[str, Any] = None, timeout: int = 300) -> TaskResult:
        """
        调用 Agent 并等待结果（异步版本）

        Args:
            agent_name: 目标 Agent 名称
            user_input: 用户输入/任务描述
            context: 额外的上下文信息
            timeout: 超时时间（秒）

        Returns:
            TaskResult: 任务结果
        """
        agent = self.registry.get_agent(agent_name)
        if not agent:
            return TaskResult(
                task_id="",
                status=TaskStatus.FAILED,
                error=f"Agent not found: {agent_name}"
            )

        task_id = self.submit_task(agent_name, user_input, context)
        start_time = time.time()

        try:
            if agent.endpoint:
                result = await self._call_remote_agent(agent, user_input, context, timeout)
            else:
                result = await self._call_local_agent(agent_name, user_input, context)
        except Exception as e:
            result = TaskResult(
                task_id=task_id,
                status=TaskStatus.FAILED,
                error=str(e),
                execution_time=time.time() - start_time
            )

        self.registry._tasks[task_id] = result
        return result

    async def _call_remote_agent(self, agent: AgentInfo, user_input: str, context: Dict[str, Any], timeout: int) -> TaskResult:
        """调用远程 Agent"""
        import aiohttp

        headers = {"Content-Type": "application/json"}
        if agent.auth_token:
            headers["Authorization"] = f"Bearer {agent.auth_token}"

        payload = {
            "task_id": context.get("task_id", ""),
            "user_input": user_input,
            "context": context
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    agent.endpoint + "/a2a/execute",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return TaskResult.from_dict(data)
                    else:
                        error_text = await response.text()
                        return TaskResult(
                            task_id=context.get("task_id", ""),
                            status=TaskStatus.FAILED,
                            error=f"Remote agent error: {response.status} - {error_text}"
                        )
        except Exception as e:
            return TaskResult(
                task_id=context.get("task_id", ""),
                status=TaskStatus.FAILED,
                error=f"Connection error: {str(e)}"
            )

    async def _call_local_agent(self, agent_name: str, user_input: str, context: Dict[str, Any]) -> TaskResult:
        """调用本地 Agent"""
        from fr_cli.agent.executor import delegate_to_agent

        try:
            from fr_cli.core.core import AppState
            state = context.get("state")

            if state is None:
                return TaskResult(
                    task_id=context.get("task_id", ""),
                    status=TaskStatus.FAILED,
                    error="State not provided for local agent call"
                )

            result, error = delegate_to_agent(
                agent_name,
                state,
                pipeline_input=context.get("pipeline_input"),
                **context.get("kwargs", {})
            )

            if error:
                return TaskResult(
                    task_id=context.get("task_id", ""),
                    status=TaskStatus.FAILED,
                    error=error
                )

            return TaskResult(
                task_id=context.get("task_id", ""),
                status=TaskStatus.COMPLETED,
                result=result
            )
        except Exception as e:
            return TaskResult(
                task_id=context.get("task_id", ""),
                status=TaskStatus.FAILED,
                error=f"Local agent execution error: {str(e)}"
            )

    def call_agent_sync(self, agent_name: str, user_input: str, context: Dict[str, Any] = None, timeout: int = 300) -> TaskResult:
        """同步调用 Agent"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(self.call_agent(agent_name, user_input, context, timeout))


class A2AServer:
    """
    A2A 服务器 - 提供 Agent 的 HTTP 接口
    允许其他 Agent 通过 HTTP 调用本地的 Agent
    """

    def __init__(self, agent_name: str, agent_module=None, host: str = "127.0.0.1", port: int = None):
        self.agent_name = agent_name
        self.agent_module = agent_module
        self.host = host
        self.port = port or self._get_default_port(agent_name)
        self._app = None
        self._server = None

    def _get_default_port(self, agent_name: str) -> int:
        """根据 Agent 名称生成默认端口"""
        hash_val = sum(ord(c) for c in agent_name)
        return 8000 + (hash_val % 1000)

    def _create_app(self):
        """创建 Flask/aiohttp 应用"""
        try:
            from aiohttp import web
            self._app = web.Application()
            self._setup_routes()
            return web
        except ImportError:
            from flask import Flask
            self._app = Flask(__name__)
            self._setup_flask_routes()
            return None

    def _setup_routes(self):
        """设置 aiohttp 路由"""
        self._app.router.add_post('/a2a/execute', self.handle_execute)
        self._app.router.add_get('/a2a/status/{task_id}', self.handle_status)
        self._app.router.add_get('/a2a/agents', self.handle_list_agents)
        self._app.router.add_post('/a2a/register', self.handle_register)

    async def handle_execute(self, request):
        """处理任务执行请求"""
        try:
            data = await request.json()
            task_id = data.get("task_id", str(uuid.uuid4()))
            user_input = data.get("user_input", "")
            context = data.get("context", {})

            context["task_id"] = task_id

            result = await self._execute_task(user_input, context)

            return web.json_response(result.to_dict())
        except Exception as e:
            return web.json_response({
                "error": str(e),
                "status": TaskStatus.FAILED.value
            }, status=500)

    async def handle_status(self, request):
        """获取任务状态"""
        task_id = request.match_info['task_id']
        return web.json_response({"task_id": task_id, "status": "completed"})

    async def handle_list_agents(self, request):
        """列出所有可用 Agent"""
        registry = AgentRegistry()
        agents = [a.to_dict() for a in registry.list_agents()]
        return web.json_response({"agents": agents})

    async def handle_register(self, request):
        """注册 Agent"""
        data = await request.json()
        agent_info = AgentInfo.from_dict(data)
        registry = AgentRegistry()
        registry.register(agent_info)
        return web.json_response({"success": True})

    async def _execute_task(self, user_input: str, context: Dict[str, Any]) -> TaskResult:
        """执行任务"""
        start_time = time.time()

        try:
            if hasattr(self.agent_module, "run"):
                result = self.agent_module.run(context, user_input=user_input)
                return TaskResult(
                    task_id=context.get("task_id", ""),
                    status=TaskStatus.COMPLETED,
                    result=result,
                    execution_time=time.time() - start_time
                )
            else:
                return TaskResult(
                    task_id=context.get("task_id", ""),
                    status=TaskStatus.FAILED,
                    error="Agent module does not have 'run' method",
                    execution_time=time.time() - start_time
                )
        except Exception as e:
            return TaskResult(
                task_id=context.get("task_id", ""),
                status=TaskStatus.FAILED,
                error=str(e),
                execution_time=time.time() - start_time
            )

    async def start(self):
        """启动 A2A 服务器"""
        web = self._create_app()
        runner = web.AppRunner(self._app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        self._server = runner
        return runner

    def start_sync(self):
        """同步启动服务器"""
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.start())

    async def stop(self):
        """停止服务器"""
        if self._server:
            await self._server.cleanup()


def discover_all_agents() -> List[Dict[str, Any]]:
    """
    发现所有可用的 Agent（本地 + 远程）
    返回 Agent 列表及其元数据
    """
    registry = AgentRegistry()

    local_agents = _discover_local_agents()
    remote_agents = [
        {
            "name": agent.name,
            "type": agent.type,
            "description": agent.description,
            "capabilities": agent.capabilities,
            "endpoint": agent.endpoint,
            "status": agent.status,
        }
        for agent in registry.list_agents()
        if agent.endpoint
    ]

    return local_agents + remote_agents


def _discover_local_agents() -> List[Dict[str, Any]]:
    """发现本地 Agent"""
    from fr_cli.agent.manager import list_agents

    agents = list_agents()
    return [
        {
            "name": agent["name"],
            "type": "local",
            "description": f"本地 Agent: {agent['name']}",
            "capabilities": _infer_capabilities(agent),
            "endpoint": None,
            "status": "online",
        }
        for agent in agents
    ]


def _infer_capabilities(agent: dict) -> List[str]:
    """根据 Agent 的 persona 和 skills 推断其能力"""
    capabilities = [AgentCapability.GENERAL.value]

    persona = agent.get("persona", "") or ""
    skills = agent.get("skills", "") or ""

    text = (persona + " " + skills).lower()

    capability_keywords = {
        "code": AgentCapability.CODE_GENERATION.value,
        "代码": AgentCapability.CODE_GENERATION.value,
        "review": AgentCapability.CODE_REVIEW.value,
        "审查": AgentCapability.CODE_REVIEW.value,
        "data": AgentCapability.DATA_ANALYSIS.value,
        "数据": AgentCapability.DATA_ANALYSIS.value,
        "database": AgentCapability.DATABASE.value,
        "数据库": AgentCapability.DATABASE.value,
        "web": AgentCapability.WEB_SEARCH.value,
        "搜索": AgentCapability.WEB_SEARCH.value,
        "image": AgentCapability.IMAGE_PROCESSING.value,
        "图像": AgentCapability.IMAGE_PROCESSING.value,
    }

    for keyword, capability in capability_keywords.items():
        if keyword in text:
            if capability not in capabilities:
                capabilities.append(capability)

    return capabilities