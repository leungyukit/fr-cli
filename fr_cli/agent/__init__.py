"""
Agent 分身系统
支持创建、管理、执行由 AI 自动生成的独立 Agent
"""
from pathlib import Path

AGENTS_DIR = Path.home() / ".fr_cli_agents"

__all__ = ["AGENTS_DIR"]
