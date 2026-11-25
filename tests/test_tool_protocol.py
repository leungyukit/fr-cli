"""
统一工具调用协议层（fr_cli.core.tool_protocol）测试

覆盖：三级参数回退、全格式提取、去重、两条历史路径行为一致性。
"""

from fr_cli.core.tool_protocol import (
    ToolCall,
    extract_calls,
    extract_marker_calls,
    loose_parse_kwargs,
    normalize_tool_call,
    parse_tool_args,
)


class TestParseToolArgs:
    """参数解析三级回退"""

    def test_strict_json(self):
        assert parse_tool_args('{"path": "/a.txt", "n": 3}') == {"path": "/a.txt", "n": 3}

    def test_python_literal(self):
        """单引号 / True / False —— 第二级 ast.literal_eval"""
        assert parse_tool_args("{'path': '/a.txt', 'flag': True}") == {
            "path": "/a.txt", "flag": True
        }

    def test_loose_unquoted_keys(self):
        """无引号的 key —— 第三级宽松回退（旧实现匹配不到，是真实缺陷）"""
        result = parse_tool_args("{path: /a.txt, content: hello}")
        assert result == {"path": "/a.txt", "content": "hello"}

    def test_loose_mixed_types(self):
        result = parse_tool_args("{a: True, b: 2, c: null, d: 1.5}")
        assert result == {"a": True, "b": 2, "c": None, "d": 1.5}

    def test_empty_string_returns_empty_dict(self):
        assert parse_tool_args("") == {}

    def test_unparseable_returns_none(self):
        assert parse_tool_args("完全不是参数") is None

    def test_raw_newline_in_json_string_escaped(self):
        """模型偶尔在 JSON 字符串里直接换行"""
        result = parse_tool_args('{"content": "line1\nline2"}')
        assert result is not None
        assert "line1" in result["content"]


class TestLooseParseKwargs:
    def test_requires_at_least_one_key(self):
        assert loose_parse_kwargs("没有冒号") is None

    def test_quoted_and_unquoted_keys(self):
        assert loose_parse_kwargs('{"a": 1}') == {"a": 1}
        assert loose_parse_kwargs("{a: 1}") == {"a": 1}


class TestNormalizeToolCall:
    def test_tool_params(self):
        assert normalize_tool_call({"tool": "x", "params": {"a": 1}}) == {
            "tool": "x", "params": {"a": 1}
        }

    def test_name_arguments(self):
        assert normalize_tool_call({"name": "x", "arguments": {"a": 1}}) == {
            "tool": "x", "params": {"a": 1}
        }

    def test_openai_function_style(self):
        obj = {"function": {"name": "x", "arguments": '{"a": 1}'}}
        assert normalize_tool_call(obj) == {"tool": "x", "params": {"a": 1}}

    def test_arguments_as_json_string(self):
        obj = {"tool": "x", "arguments": '{"a": 1}'}
        assert normalize_tool_call(obj) == {"tool": "x", "params": {"a": 1}}

    def test_plan_json_is_not_a_tool_call(self):
        assert normalize_tool_call({"goal": "x", "steps": [1], "summary": "y"}) is None

    def test_non_dict(self):
        assert normalize_tool_call("string") is None


class TestExtractMarkerCalls:
    def test_basic(self):
        calls = extract_marker_calls('【调用：read_file({"path": "/a"})】')
        assert len(calls) == 1
        assert calls[0][0] == "read_file"
        assert calls[0][1] == '{"path": "/a"}'

    def test_nested_parentheses_ignored_in_strings(self):
        calls = extract_marker_calls('【调用：cmd({"cmd": "echo (a) b"})】')
        assert calls[0][1] == '{"cmd": "echo (a) b"}'

    def test_unbalanced_does_not_hang(self):
        """括号未闭合时必须跳过而不是死循环"""
        calls = extract_marker_calls('【调用：broken({"a": 1】')
        assert calls == [] or len(calls) <= 1


class TestExtractCalls:
    """全格式提取"""

    def _one(self, text):
        calls = extract_calls(text)
        assert len(calls) == 1, f"期望 1 个调用, 实际 {len(calls)}: {calls}"
        return calls[0]

    def test_marker_json(self):
        c = self._one('【调用：write_file({"path": "/a.txt"})】')
        assert c.tool == "write_file"
        assert c.params == {"path": "/a.txt"}
        assert c.fmt == "marker"

    def test_marker_loose_fallback(self):
        """ReAct 路径过去的缺口：非严格 JSON 也能解析出来"""
        c = self._one("【调用：write_file({path: /a.txt})】")
        assert c.tool == "write_file"
        assert c.params == {"path": "/a.txt"}

    def test_xml_tag(self):
        c = self._one('<tool_call>{"tool": "read_file", "params": {"path": "/x"}}</tool_call>')
        assert c.tool == "read_file"
        assert c.params == {"path": "/x"}

    def test_code_fence(self):
        c = self._one('```tool\n{"tool": "ls", "params": {}}\n```')
        assert c.tool == "ls"

    def test_bare_json(self):
        c = self._one('{"tool": "grep", "arguments": {"q": "x"}}')
        assert c.tool == "grep"
        assert c.params == {"q": "x"}

    def test_json_array(self):
        calls = extract_calls('[{"tool": "a", "params": {}}, {"tool": "b", "params": {}}]')
        assert {c.tool for c in calls} == {"a", "b"}

    def test_prose_is_not_a_call(self):
        assert extract_calls("今天天气不错，我们继续讨论。") == []

    def test_plan_json_not_a_call(self):
        assert extract_calls('{"goal": "x", "steps": [1], "summary": "y"}') == []

    def test_dedup_same_tool_same_params(self):
        text = '【调用：x({"a": 1})】 【调用：x({"a": 1})】'
        assert len(extract_calls(text)) == 1

    def test_different_params_not_deduped(self):
        text = '【调用：x({"a": 1})】 【调用：x({"a": 2})】'
        assert len(extract_calls(text)) == 2

    def test_parse_error_is_reported_not_swallowed(self):
        """参数解析失败要留下 error，不能静默丢弃"""
        calls = extract_calls("【调用：x(完全不是参数)】")
        assert len(calls) == 1
        assert calls[0].error


class TestToolCallStruct:
    def test_to_dict(self):
        c = ToolCall("x", {"a": 1})
        assert c.to_dict() == {"tool": "x", "params": {"a": 1}}

    def test_eq_with_dict(self):
        assert ToolCall("x", {"a": 1}) == {"tool": "x", "params": {"a": 1}}


class TestPathParity:
    """两条历史路径必须行为一致（这是本次改造的核心目的）"""

    def test_executor_mixin_delegates(self):
        from fr_cli.command.executor_parse import CommandParseMixin
        mixin = CommandParseMixin()
        text = '【调用：write_file({path: /a.txt})】'
        calls = mixin._extract_tool_calls(text)
        assert len(calls) == 1
        assert mixin._parse_tool_kwargs(calls[0][1]) == {"path": "/a.txt"}

    def test_master_loop_delegates(self):
        from fr_cli.agent.master_loop import MasterAgentLoopMixin
        text = '【调用：write_file({path: /a.txt})】'
        calls = MasterAgentLoopMixin._extract_tool_calls(text)
        assert len(calls) == 1
        assert calls[0]["tool"] == "write_file"
        assert calls[0]["params"] == {"path": "/a.txt"}
