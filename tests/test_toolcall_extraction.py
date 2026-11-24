"""工具调用容错提取回归测试。

固化 live 实测问题: step-5-preview 实际输出的是 tool_call XML 标签包裹的
JSON(以及裸 JSON / 普通围栏), 而 master_loop._extract_tool_calls 旧实现
只认 ```tool 围栏 + 【调用：】, 于是工具调用被当成"最终答案"、
ReAct 循环一步退出、工具从未执行(静默失败)。

XML 工具标签在测试里用字符串拼接构造, 不在源码里写死闭合标签。
"""
from fr_cli.agent.master_loop import MasterAgentLoopMixin
from fr_cli.core.plan.toolcalls import extract_tool_calls

TO = "<" + "tool" + "_call" + ">"
TC = "<" + "/" + "tool" + "_call" + ">"


def _names(calls):
    return [c["tool"] for c in calls]


class TestExtractToolCalls:
    """core.plan.toolcalls.extract_tool_calls 的多形态容错"""

    def test_legacy_tool_fence(self):
        text = '```tool\n{"tool": "list_files", "params": {"path": "."}}\n```'
        assert extract_tool_calls(text) == [
            {"tool": "list_files", "params": {"path": "."}}
        ]

    def test_xml_tool_call_tag(self):
        text = TO + '\n{"tool": "list_files", "params": {"path": "."}}\n' + TC
        assert extract_tool_calls(text) == [
            {"tool": "list_files", "params": {"path": "."}}
        ]

    def test_bare_json_with_cot_around(self):
        text = '我先看一下目录。\n{"tool": "list_files", "params": {"path": "."}}\n然后汇总。'
        assert _names(extract_tool_calls(text)) == ["list_files"]

    def test_plain_json_fence(self):
        text = '```json\n{"tool": "read_file", "params": {"path": "a.txt"}}\n```'
        assert _names(extract_tool_calls(text)) == ["read_file"]

    def test_name_and_arguments_keys(self):
        text = '{"name": "update_check", "arguments": {}}'
        assert extract_tool_calls(text) == [{"tool": "update_check", "params": {}}]

    def test_openai_function_style(self):
        text = '{"function": {"name": "list_files", "arguments": {"path": "."}}}'
        assert _names(extract_tool_calls(text)) == ["list_files"]

    def test_missing_params_defaults_empty(self):
        text = '{"tool": "update_check"}'
        assert extract_tool_calls(text) == [{"tool": "update_check", "params": {}}]

    def test_array_of_calls(self):
        text = '[{"tool": "list_files", "params": {}}, {"tool": "update_check"}]'
        assert _names(extract_tool_calls(text)) == ["list_files", "update_check"]

    def test_dedup_identical_calls(self):
        text = TO + '{"tool":"update_check"}' + TC + TO + '{"tool":"update_check"}' + TC
        assert extract_tool_calls(text) == [{"tool": "update_check", "params": {}}]

    def test_prose_returns_empty(self):
        assert extract_tool_calls("好的，我来帮你查一下版本号。") == []

    def test_empty_text_returns_empty(self):
        assert extract_tool_calls("") == []

    def test_object_with_steps_key_is_not_a_call(self):
        # 计划 JSON(带 steps)本身不是工具调用
        text = '{"tool": "list_files", "params": {}, "steps": [{"description": "d"}]}'
        assert extract_tool_calls(text) == []


class TestMasterLoopExtractToolCalls:
    """MasterAgentLoopMixin._extract_tool_calls 端到端契约"""

    def test_xml_tag_reaches_master_loop(self):
        text = TO + '\n{"tool": "list_files", "params": {"path": "."}}\n' + TC
        calls = MasterAgentLoopMixin._extract_tool_calls(text)
        assert calls == [{"tool": "list_files", "params": {"path": "."}}]

    def test_legacy_call_syntax_still_works(self):
        text = '【调用：list_files({"path": "."})】'
        calls = MasterAgentLoopMixin._extract_tool_calls(text)
        assert calls == [{"tool": "list_files", "params": {"path": "."}}]

    def test_bare_json_reaches_master_loop(self):
        text = '先看看。\n{"tool": "update_check", "params": {}}\n完。'
        calls = MasterAgentLoopMixin._extract_tool_calls(text)
        assert calls == [{"tool": "update_check", "params": {}}]

    def test_prose_is_treated_as_final_answer(self):
        assert MasterAgentLoopMixin._extract_tool_calls("没有工具可调用") == []
