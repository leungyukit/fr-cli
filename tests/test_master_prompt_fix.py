"""
master_prompt.py 修复测试

测试目标：确保 JSON 格式化不会触发 KeyError
背景：之前的问题是在提示词模板中，JSON 代码块中的花括号 { 和 }
         被 Python 的 .format() 方法错误解释为格式化占位符。
"""
import json
import pytest


class TestMasterPromptFormatFix:
    """测试 master_prompt.py 中的 JSON 格式化修复"""

    def test_chinese_prompt_format_no_key_error(self):
        """测试中文提示词模板格式化不会抛出 KeyError"""
        from fr_cli.agent.master_prompt import MASTER_SYSTEM_PROMPT_ZH

        tools_desc = "- test_tool: 这是一个测试工具"
        try:
            result = MASTER_SYSTEM_PROMPT_ZH.format(tools_desc=tools_desc)
            assert result is not None
            assert len(result) > 0
        except KeyError as e:
            pytest.fail(f"格式化时出现 KeyError: {e}，JSON 花括号未正确转义")

    def test_english_prompt_format_no_key_error(self):
        """测试英文提示词模板格式化不会抛出 KeyError"""
        from fr_cli.agent.master_prompt import MASTER_SYSTEM_PROMPT_EN

        tools_desc = "- test_tool: This is a test tool"
        try:
            result = MASTER_SYSTEM_PROMPT_EN.format(tools_desc=tools_desc)
            assert result is not None
            assert len(result) > 0
        except KeyError as e:
            pytest.fail(f"格式化时出现 KeyError: {e}，JSON 花括号未正确转义")

    def test_json_tool_call_format_preserved(self):
        """测试 JSON 工具调用格式在格式化后保持正确"""
        from fr_cli.agent.master_prompt import MASTER_SYSTEM_PROMPT_ZH

        tools_desc = "- tool1: 工具1\n- tool2: 工具2"
        result = MASTER_SYSTEM_PROMPT_ZH.format(tools_desc=tools_desc)

        # 验证格式化后 JSON 格式正确（花括号应该被正确转义）
        assert '{"tool":' in result or "{'tool':" not in result, \
            "JSON 格式应该被正确保留，不应该有多余的单引号"

        # 检查实际的 JSON 工具调用格式
        assert '```tool' in result, "应该包含工具调用代码块标记"
        assert '"tool": "工具名"' in result, "应该包含工具名示例"
        assert '"params":' in result, "应该包含 params 字段"

    def test_agent_call_format_preserved(self):
        """测试 Agent 调用格式在格式化后保持正确"""
        from fr_cli.agent.master_prompt import MASTER_SYSTEM_PROMPT_ZH

        tools_desc = "- agent1: 代理1"
        result = MASTER_SYSTEM_PROMPT_ZH.format(tools_desc=tools_desc)

        # 验证 Agent 调用格式
        assert 'agent_call' in result, "应该包含 agent_call"
        assert '"name": "Agent名"' in result, "应该包含 Agent 名称示例"
        assert '"user_input": "任务描述"' in result, "应该包含任务描述示例"

    def test_empty_tools_desc(self):
        """测试空工具描述"""
        from fr_cli.agent.master_prompt import MASTER_SYSTEM_PROMPT_ZH

        tools_desc = ""
        result = MASTER_SYSTEM_PROMPT_ZH.format(tools_desc=tools_desc)
        assert result is not None
        assert "可用工具清单：" in result

    def test_complex_tools_desc(self):
        """测试复杂的工具描述"""
        from fr_cli.agent.master_prompt import MASTER_SYSTEM_PROMPT_ZH

        tools_desc = """=== MCP 外部神通 ===
- mcp_tool1: 描述1  (服务器: server1)
- mcp_tool2: 描述2  (服务器: server2)

调用方式: mcp_call({"server": "服务器名", "tool": "工具名", "arguments": {...}})"""

        result = MASTER_SYSTEM_PROMPT_ZH.format(tools_desc=tools_desc)
        assert result is not None
        assert "mcp_tool1" in result
        assert "server1" in result

    def test_both_language_prompts_consistent(self):
        """测试中英文提示词的 JSON 格式一致性"""
        from fr_cli.agent.master_prompt import (
            MASTER_SYSTEM_PROMPT_ZH,
            MASTER_SYSTEM_PROMPT_EN
        )

        tools_desc = "Test tools"

        zh_result = MASTER_SYSTEM_PROMPT_ZH.format(tools_desc=tools_desc)
        en_result = MASTER_SYSTEM_PROMPT_EN.format(tools_desc=tools_desc)

        # 两者都应该成功格式化
        assert zh_result is not None
        assert en_result is not None

        # 都应该包含工具调用格式
        assert '```tool' in zh_result
        assert '```tool' in en_result

        # 都应该包含 JSON 格式的 tool 字段
        assert '"tool":' in zh_result
        assert '"tool":' in en_result

    def test_multiple_format_calls(self):
        """测试多次格式化调用"""
        from fr_cli.agent.master_prompt import MASTER_SYSTEM_PROMPT_ZH

        # 第一次格式化
        tools_desc_1 = "- tool1: 工具1"
        result1 = MASTER_SYSTEM_PROMPT_ZH.format(tools_desc=tools_desc_1)

        # 第二次格式化（使用不同的工具描述）
        tools_desc_2 = "- tool1: 工具1\n- tool2: 工具2\n- tool3: 工具3"
        result2 = MASTER_SYSTEM_PROMPT_ZH.format(tools_desc=tools_desc_2)

        assert result1 is not None
        assert result2 is not None
        assert len(result2) > len(result1), "更多工具应该产生更长的输出"

    def test_planning_prompt_format(self):
        """测试规划提示词模板格式化"""
        from fr_cli.agent.master_prompt import PLANNING_PROMPT_ZH

        user_input = "帮我写一个测试"
        cwd = "/test/path"
        tool_list = "tool1, tool2"

        result = PLANNING_PROMPT_ZH.format(
            user_input=user_input,
            cwd=cwd,
            tool_list=tool_list
        )

        assert result is not None
        assert user_input in result
        assert cwd in result
        assert tool_list in result

    def test_reflection_prompt_format(self):
        """测试反思提示词模板格式化"""
        from fr_cli.agent.master_prompt import REFLECTION_PROMPT_ZH

        result = REFLECTION_PROMPT_ZH.format(
            task="测试任务",
            steps="步骤1\n步骤2",
            result="成功",
            success="是"
        )

        assert result is not None
        assert "测试任务" in result
        assert "步骤1" in result
        assert "成功" in result
        assert "是" in result


class TestMasterAgentBuildSystemPrompt:
    """测试 MasterAgent 的 _build_system_prompt 方法"""

    def test_master_agent_import(self):
        """测试 MasterAgent 可以正常导入"""
        try:
            from fr_cli.agent.master import MasterAgent
            assert MasterAgent is not None
        except Exception as e:
            pytest.fail(f"导入 MasterAgent 时出错: {e}")

    def test_system_prompt_contains_tools_section(self):
        """测试系统提示词包含工具部分"""
        from fr_cli.agent.master_prompt import MASTER_SYSTEM_PROMPT_ZH

        tools_desc = "=== 可用工具 ===\n- file_read: 读取文件"
        result = MASTER_SYSTEM_PROMPT_ZH.format(tools_desc=tools_desc)

        assert "可用工具清单：" in result
        assert "file_read" in result
        assert "读取文件" in result


if __name__ == "__main__":
    # 可以直接运行此文件进行测试
    pytest.main([__file__, "-v"])
