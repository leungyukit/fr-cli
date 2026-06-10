import json
import time
from typing import Dict, List, Any, Optional

from .models import (
    NodeType, EdgeType, WorkflowNode, WorkflowEdge,
    WorkflowExecution, NodeExecutionResult,
)
from .engine import WorkflowEngine

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


