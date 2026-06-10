import json
import time
import uuid
import ast
import asyncio
import threading
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

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


# 安全的条件表达式求值器：仅支持有限语法
_ALLOWED_COMPARE_OPS = {
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.In, ast.NotIn, ast.Is, ast.IsNot,
}
_ALLOWED_BOOL_OPS = {ast.And, ast.Or}
_ALLOWED_UNARY_OPS = {ast.Not, ast.UAdd, ast.USub}


def _safe_eval_condition(expression: str) -> bool:
    """安全求值条件表达式（白名单 AST 求值，替代 eval）。

    支持的语法：变量/字符串/数字字面量、==/!=/</<=/>/>=/in/not in/is/is not、
    and/or/not、一元 +/-、括号。
    """
    if not expression or not expression.strip():
        return False
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return False

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            # 变量名视作字面量
            return node.id
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARY_OPS:
            operand = _eval(node.operand)
            if isinstance(operand, bool):
                operand = int(operand)
            if type(node.op) is ast.Not:
                return not operand
            if type(node.op) is ast.UAdd:
                return +operand
            if type(node.op) is ast.USub:
                return -operand
            raise ValueError("unary op not allowed")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            # 仅允许取模（用于 5 % 2 这样的占位判断）
            left = _eval(node.left)
            right = _eval(node.right)
            return left % right
        if isinstance(node, ast.BoolOp) and type(node.op) in _ALLOWED_BOOL_OPS:
            values = [_eval(v) for v in node.values]
            if isinstance(node.op, ast.And):
                return all(values)
            return any(values)
        if isinstance(node, ast.Compare):
            left = _eval(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                if type(op) not in _ALLOWED_COMPARE_OPS:
                    raise ValueError("compare op not allowed")
                right = _eval(comparator)
                if not _apply_compare(op, left, right):
                    return False
                left = right
            return True
        raise ValueError(f"unsupported expression node: {type(node).__name__}")

    def _apply_compare(op, left, right):
        if isinstance(op, ast.Eq):
            return left == right
        if isinstance(op, ast.NotEq):
            return left != right
        if isinstance(op, ast.Lt):
            return left < right
        if isinstance(op, ast.LtE):
            return left <= right
        if isinstance(op, ast.Gt):
            return left > right
        if isinstance(op, ast.GtE):
            return left >= right
        if isinstance(op, ast.In):
            return left in right
        if isinstance(op, ast.NotIn):
            return left not in right
        if isinstance(op, ast.Is):
            return left is right
        if isinstance(op, ast.IsNot):
            return left is not right
        return False

    try:
        return bool(_eval(tree))
    except Exception:
        return False


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

