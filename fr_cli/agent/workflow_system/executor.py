import json
import time
import uuid
import asyncio
from typing import Dict, List, Any, Optional, Callable

from .models import (
    NodeType, EdgeType, WorkflowNode, WorkflowEdge,
    WorkflowExecution, NodeExecutionResult,
)
from .engine import WorkflowEngine
from .manager import WorkflowManager

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


