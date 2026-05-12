#!/usr/bin/env python3
"""
fr-cli 全面功能测试脚本
"""

import sys
import os
sys.path.insert(0, '/Users/liangyj/workspace/github_fr-cli/fr-cli')

results = []

def test(name, func):
    try:
        func()
        results.append((name, "PASS", None))
        print(f"✅ {name}")
    except Exception as e:
        results.append((name, "FAIL", str(e)))
        print(f"❌ {name}: {e}")

def test_core_imports():
    from fr_cli.core.llm import list_providers
    from fr_cli.core.model_factory import get_model_factory
    print(f"   Providers: {len(list_providers())}")

def test_model_factory_imports():
    from fr_cli.core.model_factory import get_model_factory
    factory = get_model_factory()
    assert len(factory.list_providers()) >= 0

def test_agent_imports():
    from fr_cli.agent.shell_mode import get_shell_manager, ShellMode
    from fr_cli.agent.a2a import AgentRegistry
    from fr_cli.agent.acp import ACPServer

def test_hermes_imports():
    from fr_cli.agent.hermes import (
        TaskManager, Analytics, GoalTracker, ConfigManager, CronScheduler
    )

def test_skills_imports():
    from fr_cli.agent.skills import SkillManager, get_skill_manager

def test_personality_imports():
    from fr_cli.agent.personality import PersonalityManager, get_personality_manager

def test_context_imports():
    from fr_cli.agent.context_files import ContextFilesManager, get_context_manager

def test_mcp_imports():
    from fr_cli.weapon.mcp import MCPServerManager, get_mcp_manager

def test_gateway_imports():
    from fr_cli.agent.gateway import GatewayManager

def test_workflow_imports():
    from fr_cli.agent.workflow_system import WorkflowEngine

def test_image_imports():
    from fr_cli.agent.image_and_parallel import ImageGenerator, ParallelExecutor

def test_shell_mode():
    from fr_cli.agent.shell_mode import ShellModeManager, ShellMode
    mgr = ShellModeManager()
    mgr.current_mode = ShellMode.SHELL
    output, code = mgr.execute_command("echo 'test'")
    assert "test" in output

def test_hermes_task():
    from fr_cli.agent.hermes import TaskManager
    tm = TaskManager()
    task = tm.create_task("测试任务")
    assert task.id is not None

def test_hermes_analytics():
    from fr_cli.agent.hermes import Analytics
    an = Analytics()
    an.record_request("glm-4-flash", 100, 0.01)
    stats = an.get_stats()
    assert stats["total_requests"] == 1

def test_skills():
    from fr_cli.agent.skills import SkillManager
    sm = SkillManager()
    skill = sm.create_skill("test", "测试技能", "测试内容")
    assert skill.name == "test"

def test_personality():
    from fr_cli.agent.personality import PersonalityManager
    pm = PersonalityManager()
    personalities = pm.list_personalities()
    assert len(personalities) > 0

def test_context_files():
    from fr_cli.agent.context_files import ContextFilesManager
    cm = ContextFilesManager()
    cm.add_pattern("*.py")
    assert "*.py" in cm.patterns

def test_mcp_manager():
    from fr_cli.weapon.mcp import MCPServerManager
    mcp = MCPServerManager()
    assert mcp is not None

print("=" * 60)
print("fr-cli 全面功能测试")
print("=" * 60)

print("\n【导入测试】")
test("core.llm", test_core_imports)
test("core.model_factory", test_model_factory_imports)
test("agent.shell_mode", test_agent_imports)
test("hermes", test_hermes_imports)
test("skills", test_skills_imports)
test("personality", test_personality_imports)
test("context_files", test_context_imports)
test("mcp", test_mcp_imports)
test("gateway", test_gateway_imports)
test("workflow", test_workflow_imports)
test("image_parallel", test_image_imports)

print("\n【功能测试】")
test("shell_mode", test_shell_mode)
test("hermes_task", test_hermes_task)
test("hermes_analytics", test_hermes_analytics)
test("skills", test_skills)
test("personality", test_personality)
test("context_files", test_context_files)
test("mcp_manager", test_mcp_manager)

print("\n" + "=" * 60)
print("测试报告")
print("=" * 60)

passed = sum(1 for r in results if "PASS" in r[1])
failed = [r for r in results if "FAIL" in r[1]]

print(f"\n总计: {len(results)} | PASS: {passed} | FAIL: {len(failed)}")

if failed:
    print("\n失败项:")
    for name, _, error in failed:
        print(f"  ❌ {name}")
        print(f"     {error[:200]}")
