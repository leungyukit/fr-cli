import json
import time
import uuid
import asyncio
import threading
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from .models import (
    NodeType, EdgeType, WorkflowNode, WorkflowEdge,
    WorkflowExecution, NodeExecutionResult,
)

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
        """评估条件表达式（安全版：仅支持有限的比较/逻辑运算，不使用 eval）

        支持语法：变量、字符串字面量、数字字面量、==/!=/</<=/>/>=/in/not in/and/or/not
        """
        expression = node.condition_expression

        # 替换变量
        for node_id, result in results.items():
            placeholder = f"{{{node_id}.{node.output_key}}}"
            expression = expression.replace(placeholder, str(result.output_data))

        expression = expression.replace("{input}", str(input_data))

        return _safe_eval_condition(expression)

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


