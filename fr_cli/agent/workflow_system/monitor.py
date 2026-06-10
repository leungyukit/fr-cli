import time
from typing import Dict, List, Any, Optional

from .models import WorkflowExecution, NodeExecutionResult

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


