"""
Agent 工作流系统
================

功能：
1. 定义 Agent 工作流拓扑结构
2. 支持顺序、并行、分支、循环等多种执行模式
3. 主 Agent 监控工作流执行
4. Agent 间数据传递
5. 条件判断和动态路由
6. 错误处理和重试机制
7. 执行状态可视化
"""

import json
import time
import uuid
import asyncio
import threading
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict


# ============ 数据结构 ============

class NodeType(Enum):
    """工作流节点类型"""
    AGENT = "agent"           # Agent 节点
    CONDITION = "condition"    # 条件判断节点
    TRANSFORM = "transform"   # 数据转换节点
    MERGE = "merge"          # 数据合并节点
    OUTPUT = "output"        # 输出节点


class EdgeType(Enum):
    """工作流边类型"""
    NORMAL = "normal"         # 普通连接
    CONDITION_TRUE = "true"    # 条件为真
    CONDITION_FALSE = "false"  # 条件为假
    ERROR = "error"           # 错误处理
    TIMEOUT = "timeout"       # 超时处理


@dataclass
class WorkflowNode:
    """工作流节点"""
    id: str
    name: str
    type: NodeType
    config: Dict[str, Any] = field(default_factory=dict)

    # Agent 节点配置
    agent_name: str = ""           # Agent 名称
    input_template: str = ""        # 输入模板（可引用上游输出）
    output_key: str = "result"     # 输出结果的 key

    # 条件节点配置
    condition_expression: str = "" # 条件表达式

    # 执行配置
    timeout: int = 300             # 超时时间（秒）
    retry_count: int = 0           # 重试次数
    retry_delay: float = 1.0        # 重试延迟（秒）


@dataclass
class WorkflowEdge:
    """工作流边"""
    source_id: str
    target_id: str
    edge_type: EdgeType = EdgeType.NORMAL
    label: str = ""


@dataclass
class WorkflowExecution:
    """工作流执行记录"""
    execution_id: str
    workflow_name: str
    status: str = "pending"  # pending/running/completed/failed
    current_node: str = ""
    node_results: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    total_time: float = 0.0


@dataclass
class NodeExecutionResult:
    """节点执行结果"""
    node_id: str
    status: str  # pending/running/completed/failed
    input_data: Any = None
    output_data: Any = None
    error: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    execution_time: float = 0.0


# ============ 工作流引擎 ============

class WorkflowEngine:
    """
    Agent 工作流引擎
    支持多种执行模式和错误处理
    """

    def __init__(self, state=None):
        self.state = state
        self.nodes: Dict[str, WorkflowNode] = {}
        self.edges: List[WorkflowEdge] = []
        self.execution_history: List[WorkflowExecution] = []

    def load_workflow(self, workflow_def: Dict):
        """
        加载工作流定义

        workflow_def 格式:
        {
            "name": "workflow_name",
            "nodes": [
                {
                    "id": "node1",
                    "name": "节点1",
                    "type": "agent",
                    "agent_name": "code-agent",
                    "input_template": "输入: {upstream_result}",
                    "output_key": "result"
                },
                {
                    "id": "node2",
                    "name": "条件节点",
                    "type": "condition",
                    "condition_expression": "{node1.result} > 10"
                }
            ],
            "edges": [
                {"source": "node1", "target": "node2"},
                {"source": "node2", "target": "node3"}
            ]
        }
        """
        self.nodes.clear()
        self.edges.clear()

        # 加载节点
        for node_def in workflow_def.get("nodes", []):
            node = WorkflowNode(
                id=node_def["id"],
                name=node_def.get("name", node_def["id"]),
                type=NodeType(node_def.get("type", "agent")),
                agent_name=node_def.get("agent_name", ""),
                input_template=node_def.get("input_template", ""),
                output_key=node_def.get("output_key", "result"),
                condition_expression=node_def.get("condition_expression", ""),
                timeout=node_def.get("timeout", 300),
                retry_count=node_def.get("retry_count", 0),
                retry_delay=node_def.get("retry_delay", 1.0),
                config=node_def.get("config", {})
            )
            self.nodes[node.id] = node

        # 加载边
        for edge_def in workflow_def.get("edges", []):
            edge = WorkflowEdge(
                source_id=edge_def["source"],
                target_id=edge_def["target"],
                edge_type=EdgeType(edge_def.get("type", "normal")),
                label=edge_def.get("label", "")
            )
            self.edges.append(edge)

    def get_outgoing_edges(self, node_id: str, edge_type: EdgeType = EdgeType.NORMAL) -> List[WorkflowEdge]:
        """获取节点的出边"""
        return [e for e in self.edges if e.source_id == node_id and e.edge_type == edge_type]

    def get_incoming_edges(self, node_id: str) -> List[WorkflowEdge]:
        """获取节点的入边"""
        return [e for e in self.edges if e.target_id == node_id]

    async def execute(self, initial_input: Any = None, workflow_name: str = "workflow") -> WorkflowExecution:
        """
        执行工作流

        参数:
            initial_input: 初始输入
            workflow_name: 工作流名称

        返回:
            WorkflowExecution: 执行记录
        """
        execution = WorkflowExecution(
            execution_id=str(uuid.uuid4()),
            workflow_name=workflow_name,
            status="running"
        )

        # 找出起始节点（无入边的节点）
        start_nodes = self._find_start_nodes()

        if not start_nodes:
            execution.status = "failed"
            execution.errors.append("未找到起始节点")
            return execution

        # 执行起始节点
        results = {}
        errors = []

        for start_node in start_nodes:
            try:
                result = await self._execute_node(start_node, initial_input, results, execution)
                results[start_node.id] = result
            except Exception as e:
                errors.append(f"{start_node.name}: {str(e)}")

        # BFS 遍历执行后续节点
        completed = set(start_nodes)
        queue = list(start_nodes)

        while queue:
            current_node = queue.pop(0)
            current_result = results.get(current_node.id)

            if current_result and current_result.status != "completed":
                continue

            # 获取当前节点的后继节点
            outgoing_edges = self.get_outgoing_edges(current_node.id)
            for edge in outgoing_edges:
                if edge.target_id in completed:
                    continue

                target_node = self.nodes.get(edge.target_id)
                if not target_node:
                    continue

                # 检查是否所有前置节点都已完成
                incoming = self.get_incoming_edges(target_node.id)
                all_predecessors_done = all(
                    pred.source_id in completed for pred in incoming
                )

                if all_predecessors_done:
                    # 准备输入数据
                    input_data = self._prepare_input(
                        target_node,
                        {k: v.output_data for k, v in results.items() if v.output_data},
                        current_result.output_data if current_result else initial_input
                    )

                    # 执行节点
                    try:
                        result = await self._execute_node(target_node, input_data, results, execution)
                        results[target_node.id] = result
                        completed.add(target_node.id)
                        queue.append(target_node)

                        # 更新执行状态
                        execution.node_results[target_node.id] = {
                            "status": result.status,
                            "output": result.output_data,
                            "time": result.execution_time
                        }

                    except Exception as e:
                        errors.append(f"{target_node.name}: {str(e)}")
                        execution.errors.append(f"{target_node.name}: {str(e)}")

        # 完成执行
        execution.end_time = time.time()
        execution.total_time = execution.end_time - execution.start_time
        execution.status = "failed" if errors else "completed"

        if results:
            execution.node_results = {
                k: {
                    "status": v.status,
                    "output": v.output_data,
                    "time": v.execution_time,
                    "error": v.error
                }
                for k, v in results.items()
            }

        self.execution_history.append(execution)
        return execution

    def _find_start_nodes(self) -> List[WorkflowNode]:
        """找出起始节点"""
        start_nodes = []
        for node_id, node in self.nodes.items():
            incoming = self.get_incoming_edges(node_id)
            if not incoming:
                start_nodes.append(node)
        return start_nodes

    def _prepare_input(self, node: WorkflowNode, all_results: Dict, current_output: Any) -> Any:
        """准备节点输入数据"""
        if not node.input_template:
            return current_output

        # 替换模板中的占位符
        template = node.input_template

        # 替换上游节点输出
        for node_id, result in all_results.items():
            placeholder = f"{{{node_id}.output}}"
            template = template.replace(placeholder, str(result))

        # 替换当前输出
        template = template.replace("{upstream_result}", str(current_output))
        template = template.replace("{input}", str(current_output))

        return template

    async def _execute_node(self, node: WorkflowNode, input_data: Any,
                          results: Dict[str, NodeExecutionResult],
                          execution: WorkflowExecution) -> NodeExecutionResult:
        """执行单个节点"""
        result = NodeExecutionResult(
            node_id=node.id,
            status="running",
            input_data=input_data,
            start_time=time.time()
        )

        execution.current_node = node.name

        try:
            if node.type == NodeType.AGENT:
                # 执行 Agent 节点
                output = await self._execute_agent(node, input_data, results)
                result.output_data = output
                result.status = "completed"

            elif node.type == NodeType.CONDITION:
                # 执行条件节点
                condition_result = self._evaluate_condition(node, input_data, results)
                result.output_data = condition_result
                result.status = "completed"

            elif node.type == NodeType.TRANSFORM:
                # 执行数据转换
                transformed = self._transform_data(node, input_data, results)
                result.output_data = transformed
                result.status = "completed"

            elif node.type == NodeType.MERGE:
                # 执行数据合并
                merged = self._merge_data(node, results)
                result.output_data = merged
                result.status = "completed"

            elif node.type == NodeType.OUTPUT:
                # 输出节点
                result.output_data = input_data
                result.status = "completed"

        except Exception as e:
            result.error = str(e)
            result.status = "failed"

            # 处理重试
            if node.retry_count > 0:
                for i in range(node.retry_count):
                    time.sleep(node.retry_delay)
                    try:
                        # 重新执行
                        if node.type == NodeType.AGENT:
                            result.output_data = await self._execute_agent(node, input_data, results)
                            result.status = "completed"
                            result.error = ""
                            break
                    except Exception:
                        continue

        result.end_time = time.time()
        result.execution_time = result.end_time - result.start_time

        return result

    async def _execute_agent(self, node: WorkflowNode, input_data: Any,
                           results: Dict[str, NodeExecutionResult]) -> Any:
        """执行 Agent 节点"""
        from fr_cli.agent.executor import delegate_to_agent

        if not self.state:
            raise Exception("State 未提供")

        # 执行 Agent
        result, error = delegate_to_agent(
            node.agent_name,
            self.state,
            pipeline_input=input_data,
            user_input=input_data
        )

        if error:
            raise Exception(error)

        return result

    def _evaluate_condition(self, node: WorkflowNode, input_data: Any,
                          results: Dict[str, NodeExecutionResult]) -> bool:
        """评估条件表达式"""
        expression = node.condition_expression

        # 替换变量
        for node_id, result in results.items():
            placeholder = f"{{{node_id}.{node.output_key}}}"
            expression = expression.replace(placeholder, str(result.output_data))

        expression = expression.replace("{input}", str(input_data))

        # 评估表达式
        try:
            # 安全评估（只支持基本比较）
            return eval(expression, {"__builtins__": {}})
        except Exception:
            return False

    def _transform_data(self, node: WorkflowNode, input_data: Any,
                      results: Dict[str, NodeExecutionResult]) -> Any:
        """数据转换"""
        transform_type = node.config.get("type", "passthrough")

        if transform_type == "passthrough":
            return input_data

        elif transform_type == "merge":
            return self._merge_data(node, results)

        elif transform_type == "filter":
            filter_key = node.config.get("key", "")
            return {k: v for k, v in input_data.items() if k != filter_key}

        elif transform_type == "template":
            template = node.config.get("template", "{input}")
            return template.replace("{input}", str(input_data))

        return input_data

    def _merge_data(self, node: WorkflowNode, results: Dict[str, NodeExecutionResult]) -> Any:
        """合并数据"""
        merge_type = node.config.get("type", "concat")

        incoming = self.get_incoming_edges(node.id)
        data_list = []

        for edge in incoming:
            if edge.source_id in results:
                data_list.append(results[edge.source_id].output_data)

        if merge_type == "concat":
            return "\n".join(str(d) for d in data_list if d)

        elif merge_type == "dict":
            merged = {}
            for data in data_list:
                if isinstance(data, dict):
                    merged.update(data)
            return merged

        elif merge_type == "list":
            result = []
            for data in data_list:
                if isinstance(data, list):
                    result.extend(data)
                else:
                    result.append(data)
            return result

        return data_list[0] if data_list else None

    def get_workflow_status(self, execution: WorkflowExecution) -> Dict:
        """获取工作流状态"""
        status = {
            "execution_id": execution.execution_id,
            "workflow_name": execution.workflow_name,
            "status": execution.status,
            "current_node": execution.current_node,
            "completed_nodes": [],
            "running_nodes": [],
            "failed_nodes": [],
            "total_time": f"{execution.total_time:.2f}s" if execution.total_time else "N/A"
        }

        for node_id, result in execution.node_results.items():
            node = self.nodes.get(node_id)
            node_name = node.name if node else node_id

            if result.get("status") == "completed":
                status["completed_nodes"].append(node_name)
            elif result.get("status") == "running":
                status["running_nodes"].append(node_name)
            elif result.get("error"):
                status["failed_nodes"].append(f"{node_name}: {result.get('error')}")

        return status


# ============ 工作流管理器 ============

class WorkflowManager:
    """
    工作流管理器
    管理工作流的创建、编辑、删除和执行
    """

    def __init__(self, state=None):
        self.state = state
        self.workflows: Dict[str, WorkflowEngine] = {}
        self.workflow_definitions: Dict[str, Dict] = {}
        self.workflow_dir = None

    def create_workflow(self, name: str, definition: Dict) -> WorkflowEngine:
        """创建工作流"""
        engine = WorkflowEngine(self.state)
        engine.load_workflow(definition)
        engine.workflow_name = name

        self.workflows[name] = engine
        self.workflow_definitions[name] = definition

        return engine

    def get_workflow(self, name: str) -> Optional[WorkflowEngine]:
        """获取工作流"""
        return self.workflows.get(name)

    def list_workflows(self) -> List[Dict]:
        """列出所有工作流"""
        return [
            {
                "name": name,
                "nodes": list(engine.nodes.keys()),
                "status": "loaded"
            }
            for name, engine in self.workflows.items()
        ]

    async def run_workflow(self, name: str, input_data: Any = None) -> WorkflowExecution:
        """运行工作流"""
        engine = self.workflows.get(name)
        if not engine:
            raise Exception(f"工作流不存在: {name}")

        return await engine.execute(input_data, name)

    def visualize_workflow(self, name: str) -> str:
        """可视化工作流（文本格式）"""
        engine = self.workflows.get(name)
        if not engine:
            return f"工作流不存在: {name}"

        lines = [f"\n{'='*60}", f"工作流: {name}", f"{'='*60}\n"]

        # 绘制节点
        for node_id, node in engine.nodes.items():
            incoming = engine.get_incoming_edges(node_id)
            outgoing = engine.get_outgoing_edges(node_id)

            incoming_names = [engine.nodes[e.source_id].name for e in incoming if e.source_id in engine.nodes]
            outgoing_names = [engine.nodes[e.target_id].name for e in outgoing if e.target_id in engine.nodes]

            lines.append(f"📦 {node.name} ({node.type.value})")
            if incoming_names:
                lines.append(f"   ← 来自: {', '.join(incoming_names)}")
            if outgoing_names:
                lines.append(f"   → 去向: {', '.join(outgoing_names)}")
            lines.append("")

        return "\n".join(lines)


# ============ 工作流执行器 ============

class WorkflowExecutor:
    """
    工作流执行器
    支持并行和串行执行模式
    """

    def __init__(self, state=None):
        self.state = state
        self.manager = WorkflowManager(state)

    async def execute_parallel(self, workflows: List[str], input_data: Any = None) -> Dict[str, WorkflowExecution]:
        """
        并行执行多个工作流

        参数:
            workflows: 工作流名称列表
            input_data: 初始输入

        返回:
            Dict[str, WorkflowExecution]: 工作流执行结果
        """
        tasks = []

        for workflow_name in workflows:
            engine = self.manager.get_workflow(workflow_name)
            if engine:
                task = engine.execute(input_data, workflow_name)
                tasks.append((workflow_name, task))

        results = {}
        for name, coro in tasks:
            try:
                results[name] = await coro
            except Exception as e:
                results[name] = WorkflowExecution(
                    execution_id=str(uuid.uuid4()),
                    workflow_name=name,
                    status="failed",
                    errors=[str(e)]
                )

        return results

    async def execute_sequential(self, workflows: List[str], initial_input: Any = None) -> Dict[str, WorkflowExecution]:
        """
        顺序执行多个工作流（上一个输出作为下一个输入）

        参数:
            workflows: 工作流名称列表
            initial_input: 初始输入

        返回:
            Dict[str, WorkflowExecution]: 工作流执行结果
        """
        results = {}
        current_input = initial_input

        for workflow_name in workflows:
            engine = self.manager.get_workflow(workflow_name)
            if not engine:
                continue

            try:
                execution = await engine.execute(current_input, workflow_name)
                results[workflow_name] = execution

                # 将输出传递给下一个工作流
                if execution.node_results:
                    last_result = list(execution.node_results.values())[-1]
                    if last_result.get("output"):
                        current_input = last_result["output"]

            except Exception as e:
                results[workflow_name] = WorkflowExecution(
                    execution_id=str(uuid.uuid4()),
                    workflow_name=workflow_name,
                    status="failed",
                    errors=[str(e)]
                )
                break

        return results

    def execute_workflow_by_input(self, user_input: str, state) -> str:
        """
        根据用户输入解析和执行工作流

        解析格式：
        [Agent1] -> [Agent2] -> [Agent3]
        [Agent1, Agent2] -> [Agent3]  (前两个并行，然后串行到第三个)
        """
        # 解析工作流定义
        workflow_def = self._parse_workflow_from_input(user_input)

        if not workflow_def:
            return "❌ 无法解析工作流定义"

        # 创建工作流
        workflow_name = f"temp_workflow_{int(time.time())}"
        engine = self.manager.create_workflow(workflow_name, workflow_def)

        # 执行
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        execution = loop.run_until_complete(engine.execute(user_input, workflow_name))

        # 输出结果
        if execution.status == "completed":
            return self._format_execution_result(execution, engine)
        else:
            return f"❌ 工作流执行失败: {execution.errors}"

    def _parse_workflow_from_input(self, user_input: str) -> Optional[Dict]:
        """从用户输入解析工作流定义"""
        # 简单解析格式: [Agent1] -> [Agent2] -> [Agent3]

        try:
            # 移除空格
            user_input = user_input.replace(" ", "")

            # 分割节点
            if "->" in user_input:
                parts = user_input.split("->")
            elif "," in user_input:
                parts = user_input.split(",")
            else:
                parts = [user_input]

            nodes = []
            edges = []

            for i, part in enumerate(parts):
                # 解析节点名
                agent_name = part.strip("[]{}")
                if not agent_name:
                    continue

                node_id = f"node_{i+1}"
                node = {
                    "id": node_id,
                    "name": agent_name,
                    "type": "agent",
                    "agent_name": agent_name,
                    "input_template": "{upstream_result}" if i > 0 else "{input}"
                }
                nodes.append(node)

                # 创建边
                if i > 0:
                    edges.append({
                        "source": f"node_{i}",
                        "target": node_id
                    })

            if not nodes:
                return None

            return {
                "name": "parsed_workflow",
                "nodes": nodes,
                "edges": edges
            }

        except Exception:
            return None

    def _format_execution_result(self, execution: WorkflowExecution, engine: WorkflowEngine) -> str:
        """格式化执行结果"""
        lines = ["\n" + "="*60, "🔄 工作流执行结果", "="*60 + "\n"]

        lines.append(f"状态: {'✅ 完成' if execution.status == 'completed' else '❌ 失败'}")
        lines.append(f"总耗时: {execution.total_time:.2f}s")
        lines.append("")

        for node_id, result in execution.node_results.items():
            node = engine.nodes.get(node_id)
            node_name = node.name if node else node_id

            lines.append(f"📦 {node_name}:")
            if result.get("status") == "completed":
                lines.append(f"   ✅ 完成 (耗时: {result.get('time', 0):.2f}s)")
                if result.get("output"):
                    output = result["output"]
                    if isinstance(output, str) and len(output) > 200:
                        output = output[:200] + "..."
                    lines.append(f"   输出: {output}")
            else:
                lines.append(f"   ❌ 失败: {result.get('error', '未知错误')}")
            lines.append("")

        if execution.errors:
            lines.append("错误:")
            for error in execution.errors:
                lines.append(f"  • {error}")

        return "\n".join(lines)


# ============ 监控和可视化 ============

class WorkflowMonitor:
    """
    工作流监控器
    实时监控工作流执行状态
    """

    def __init__(self):
        self.active_executions: Dict[str, WorkflowExecution] = {}

    def register_execution(self, execution: WorkflowExecution):
        """注册执行记录"""
        self.active_executions[execution.execution_id] = execution

    def get_execution_status(self, execution_id: str) -> Optional[Dict]:
        """获取执行状态"""
        execution = self.active_executions.get(execution_id)
        if not execution:
            return None

        return {
            "execution_id": execution_id,
            "workflow_name": execution.workflow_name,
            "status": execution.status,
            "current_node": execution.current_node,
            "completed_steps": len([r for r in execution.node_results.values() if r.get("status") == "completed"]),
            "total_steps": len(execution.node_results),
            "total_time": f"{execution.total_time:.2f}s" if execution.total_time else "N/A",
            "errors": execution.errors
        }

    def list_active_executions(self) -> List[Dict]:
        """列出所有活跃执行"""
        return [
            self.get_execution_status(eid)
            for eid in self.active_executions
            if self.get_execution_status(eid)
        ]

    def format_status_display(self, execution_id: str) -> str:
        """格式化状态显示"""
        status = self.get_execution_status(execution_id)
        if not status:
            return "执行记录不存在"

        lines = [f"\n{'='*50}",
                f"执行ID: {status['execution_id']}",
                f"工作流: {status['workflow_name']}",
                f"状态: {status['status']}",
                f"当前节点: {status['current_node']}",
                f"进度: {status['completed_steps']}/{status['total_steps']}",
                f"耗时: {status['total_time']}"]

        if status.get("errors"):
            lines.append("错误:")
            for error in status["errors"]:
                lines.append(f"  • {error}")

        lines.append("="*50)
        return "\n".join(lines)


# ============ 主入口 ============

def create_workflow_from_template(template_name: str) -> Dict:
    """
    从模板创建工作流

    模板：
    - code_review: 代码审查工作流
    - data_analysis: 数据分析工作流
    - multi_agent_chat: 多 Agent 对话
    """

    templates = {
        "code_review": {
            "name": "代码审查",
            "nodes": [
                {"id": "analyze", "name": "代码分析", "type": "agent", "agent_name": "code-analyzer"},
                {"id": "suggest", "name": "优化建议", "type": "agent", "agent_name": "code-suggester"},
                {"id": "report", "name": "生成报告", "type": "agent", "agent_name": "doc-writer"}
            ],
            "edges": [
                {"source": "analyze", "target": "suggest"},
                {"source": "suggest", "target": "report"}
            ]
        },
        "data_analysis": {
            "name": "数据分析",
            "nodes": [
                {"id": "collect", "name": "数据收集", "type": "agent", "agent_name": "data-collector"},
                {"id": "clean", "name": "数据清洗", "type": "agent", "agent_name": "data-cleaner"},
                {"id": "analyze", "name": "分析", "type": "agent", "agent_name": "data-analyzer"},
                {"id": "visualize", "name": "可视化", "type": "agent", "agent_name": "chart-maker"}
            ],
            "edges": [
                {"source": "collect", "target": "clean"},
                {"source": "clean", "target": "analyze"},
                {"source": "analyze", "target": "visualize"}
            ]
        },
        "multi_agent_chat": {
            "name": "多 Agent 协作",
            "nodes": [
                {"id": "planner", "name": "规划师", "type": "agent", "agent_name": "planner-agent"},
                {"id": "executor1", "name": "执行者1", "type": "agent", "agent_name": "executor-1"},
                {"id": "executor2", "name": "执行者2", "type": "agent", "agent_name": "executor-2"},
                {"id": "synthesizer", "name": "综合器", "type": "agent", "agent_name": "synthesizer"}
            ],
            "edges": [
                {"source": "planner", "target": "executor1"},
                {"source": "planner", "target": "executor2"},
                {"source": "executor1", "target": "synthesizer"},
                {"source": "executor2", "target": "synthesizer"}
            ]
        }
    }

    return templates.get(template_name, {})


def run_workflow(context: Dict, **kwargs) -> str:
    """
    工作流入口（可被 Agent 调用）

    使用示例：
    【调用：run_workflow({"workflow": "code_review", "input": "代码内容"})】
    【调用：create_workflow({"template": "multi_agent_chat"})】
    【调用：workflow_status({"execution_id": "xxx"})】
    """
    action = kwargs.get("action", kwargs.get("workflow"))

    if action == "run" or kwargs.get("workflow"):
        return _handle_run_workflow(kwargs)

    elif action == "create":
        return _handle_create_workflow(kwargs)

    elif action == "status":
        return _handle_workflow_status(kwargs)

    elif action == "visualize":
        return _handle_visualize(kwargs)

    elif action == "list":
        return _handle_list_workflows(kwargs)

    else:
        return "未知操作。可用操作: run, create, status, visualize, list"


def _handle_run_workflow(kwargs) -> str:
    """处理工作流运行"""
    workflow_name = kwargs.get("workflow")
    input_data = kwargs.get("input", "")
    state = kwargs.get("state")

    if not workflow_name:
        return "❌ 未指定工作流"

    executor = WorkflowExecutor(state)

    if workflow_name in ["code_review", "data_analysis", "multi_agent_chat"]:
        workflow_def = create_workflow_from_template(workflow_name)
        if workflow_def:
            name = f"{workflow_name}_{int(time.time())}"
            executor.manager.create_workflow(name, workflow_def)
            workflow_name = name

    result = executor.execute_workflow_by_input(workflow_name, state)
    return result


def _handle_create_workflow(kwargs) -> str:
    """处理创建工作流"""
    template = kwargs.get("template")
    definition = kwargs.get("definition")

    if template:
        workflow_def = create_workflow_from_template(template)
        if workflow_def:
            return f"✅ 已从模板创建工作流: {workflow_def['name']}\n节点: {[n['name'] for n in workflow_def['nodes']]}"
        return f"❌ 未知模板: {template}"

    return "❌ 请提供 template 或 definition 参数"


def _handle_workflow_status(kwargs) -> str:
    """处理状态查询"""
    execution_id = kwargs.get("execution_id")

    if not execution_id:
        return "❌ 未提供 execution_id"

    monitor = WorkflowMonitor()
    return monitor.format_status_display(execution_id)


def _handle_visualize(kwargs) -> str:
    """处理可视化"""
    workflow_name = kwargs.get("workflow")
    state = kwargs.get("state")

    if not workflow_name:
        return "❌ 未提供 workflow 参数"

    executor = WorkflowExecutor(state)
    return executor.manager.visualize_workflow(workflow_name)


def _handle_list_workflows(kwargs) -> str:
    """处理列出工作流"""
    state = kwargs.get("state")
    executor = WorkflowExecutor(state)

    workflows = executor.manager.list_workflows()

    if not workflows:
        return "暂无工作流"

    lines = ["\n可用工作流:"]
    for wf in workflows:
        lines.append(f"  • {wf['name']}: {len(wf['nodes'])} 个节点")

    return "\n".join(lines)


if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                        Agent 工作流系统                                    ║
╚══════════════════════════════════════════════════════════════════════════════╝

功能：
  🔄 工作流编排: 定义节点和边的拓扑结构
  🤖 Agent 执行: 支持多种 Agent 类型
  📊 状态监控: 实时跟踪执行状态
  🔗 数据传递: 节点间数据流动
  ⚡ 并行/串行: 多种执行模式
  🛡️ 错误处理: 重试和异常处理

工作流节点类型：
  • agent: Agent 执行节点
  • condition: 条件判断节点
  • transform: 数据转换节点
  • merge: 数据合并节点
  • output: 输出节点

工作流模板：
  • code_review: 代码审查流程
  • data_analysis: 数据分析流程
  • multi_agent_chat: 多 Agent 协作

使用示例：

  # 解析用户输入创建工作流
  executor = WorkflowExecutor(state)
  result = executor.execute_workflow_by_input(
      "[分析] -> [处理] -> [输出]", state
  )

  # 使用模板创建工作流
  workflow_def = create_workflow_from_template("code_review")

  # 监控执行状态
  monitor = WorkflowMonitor()
  status = monitor.get_execution_status("execution_id")

工具调用格式：
  【调用：run_workflow({"workflow": "code_review", "input": "..."})】
  【调用：create_workflow({"template": "multi_agent_chat"})】
  【调用：workflow_status({"execution_id": "xxx"})】
""")