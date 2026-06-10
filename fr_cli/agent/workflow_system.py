"""
Agent 工作流系统（向后兼容 shim）

⚠️ 本模块已拆分为 fr_cli.agent.workflow_system 包。
新代码请从该包导入；本文件仅保留以兼容旧引用。
"""

# 重新导出所有公共符号
from fr_cli.agent.workflow_system.models import (  # noqa: F401
    _safe_eval_condition,
    NodeType, EdgeType,
    WorkflowNode, WorkflowEdge,
    WorkflowExecution, NodeExecutionResult,
)
from fr_cli.agent.workflow_system.engine import WorkflowEngine  # noqa: F401
from fr_cli.agent.workflow_system.manager import WorkflowManager  # noqa: F401
from fr_cli.agent.workflow_system.executor import WorkflowExecutor  # noqa: F401
from fr_cli.agent.workflow_system.monitor import WorkflowMonitor  # noqa: F401
from fr_cli.agent.workflow_system.tools import (  # noqa: F401
    create_workflow_from_template, run_workflow,
    _handle_run_workflow, _handle_create_workflow,
    _handle_workflow_status, _handle_visualize, _handle_list_workflows,
)
