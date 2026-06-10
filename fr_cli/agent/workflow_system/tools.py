import json
import time
from typing import Dict, List, Any, Optional

from .models import (
    NodeType, EdgeType, WorkflowNode, WorkflowEdge,
    WorkflowExecution, NodeExecutionResult,
)
from .engine import WorkflowEngine
from .manager import WorkflowManager
from .executor import WorkflowExecutor
from .monitor import WorkflowMonitor

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