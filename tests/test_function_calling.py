"""
原生 function calling 测试（P0-3）

覆盖：
  - ToolCallAccumulator：流式分片归并、JSON 解析失败、多工具并行
  - build_tools_payload / client_supports_tools
  - tool_calls_to_messages：OpenAI 协议回填消息
  - 端到端：provider 返回 tool_calls → 本地执行工具 → 结果回填 → 第二轮
  - 降级：provider 不支持 tools 时自动退回文本标记路径
"""
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fr_cli.core.llm.function_calling import (
    ToolCall,
    ToolCallAccumulator,
    build_tools_payload,
    client_supports_tools,
    tool_calls_to_messages,
)


# ------------------------------------------------------------------
# 夹具
# ------------------------------------------------------------------

class _Fn:
    """模拟 provider 的 function 字段。"""

    def __init__(self, name=None, arguments=None):
        self.name = name
        self.arguments = arguments


class _Delta:
    """模拟 OpenAI SDK 的 tool_call 分片。"""

    def __init__(self, index=0, call_id=None, name=None, arguments=None):
        self.index = index
        self.id = call_id
        self.type = "function"
        self.function = _Fn(name, arguments)


def _delta(index=0, call_id=None, name=None, arguments=None):
    return _Delta(index, call_id, name, arguments)


# ==================================================================
# ToolCallAccumulator
# ==================================================================

class TestToolCallAccumulator:

    def test_empty(self):
        acc = ToolCallAccumulator()
        assert acc.finish() == []
        assert len(acc) == 0

    def test_single_call_one_delta(self):
        acc = ToolCallAccumulator()
        acc.add_delta([_delta(0, "call_1", "search_web", '{"q":"hi"}')])
        calls = acc.finish()
        assert len(calls) == 1
        assert calls[0].id == "call_1"
        assert calls[0].name == "search_web"
        assert calls[0].arguments == {"q": "hi"}
        assert calls[0].ok is True

    def test_arguments_split_across_chunks(self):
        """参数 JSON 分片下发 —— 必须正确拼接"""
        acc = ToolCallAccumulator()
        acc.add_delta([_delta(0, "call_1", "read_file", '{"pa')])
        acc.add_delta([_delta(0, arguments='th": "a.txt"}')])
        calls = acc.finish()
        assert len(calls) == 1
        assert calls[0].arguments == {"path": "a.txt"}
        assert calls[0].raw_arguments == '{"path": "a.txt"}'

    def test_parallel_calls(self):
        """多个工具并行请求 —— 按 index 归并"""
        acc = ToolCallAccumulator()
        acc.add_delta([_delta(0, "c1", "tool_a", '{"x":1}')])
        acc.add_delta([_delta(1, "c2", "tool_b", '{"y":2')])
        acc.add_delta([_delta(1, arguments='}')])
        calls = acc.finish()
        assert len(calls) == 2
        assert calls[0].name == "tool_a"
        assert calls[1].name == "tool_b"
        assert calls[1].arguments == {"y": 2}

    def test_broken_json_reports_error(self):
        acc = ToolCallAccumulator()
        acc.add_delta([_delta(0, "c1", "tool_a", '{"x": ')])
        calls = acc.finish()
        assert len(calls) == 1
        assert calls[0].error is not None
        assert calls[0].ok is False

    def test_non_object_arguments_reports_error(self):
        acc = ToolCallAccumulator()
        acc.add_delta([_delta(0, "c1", "tool_a", '[1,2,3]')])
        calls = acc.finish()
        assert calls[0].error is not None

    def test_dict_shape_delta(self):
        """兼容 dict 形态的分片（部分 SDK 返回 dict）"""
        acc = ToolCallAccumulator()
        acc.add_delta([{
            "index": 0, "id": "c1",
            "function": {"name": "tool_a", "arguments": '{"x":1}'},
        }])
        calls = acc.finish()
        assert calls[0].name == "tool_a"
        assert calls[0].arguments == {"x": 1}

    def test_add_none_is_safe(self):
        acc = ToolCallAccumulator()
        acc.add_delta(None)
        acc.add_delta([])
        assert acc.finish() == []


# ==================================================================
# tools payload
# ==================================================================

class TestToolsPayload:

    def test_build_from_registry(self):
        payload = build_tools_payload()
        assert isinstance(payload, list)
        assert payload, "注册表里应有工具"
        first = payload[0]
        assert first["type"] == "function"
        assert "name" in first["function"]
        assert first["function"]["parameters"]["type"] == "object"

    def test_limit(self):
        payload = build_tools_payload(limit=2)
        assert len(payload) <= 2

    def test_client_supports_tools(self):
        assert client_supports_tools(SimpleNamespace(SUPPORTS_TOOLS=True)) is True
        assert client_supports_tools(SimpleNamespace(SUPPORTS_TOOLS=False)) is False
        assert client_supports_tools(object()) is False


# ==================================================================
# 协议回填
# ==================================================================

class TestToolCallsToMessages:

    def test_empty(self):
        assert tool_calls_to_messages([], []) == []

    def test_messages_shape(self):
        calls = [
            ToolCall(id="c1", name="tool_a", arguments={"x": 1}, raw_arguments='{"x":1}'),
        ]
        msgs = tool_calls_to_messages(calls, ["结果A"])
        assert len(msgs) == 2
        assert msgs[0]["role"] == "assistant"
        assert msgs[0]["tool_calls"][0]["function"]["name"] == "tool_a"
        assert msgs[1]["role"] == "tool"
        assert msgs[1]["tool_call_id"] == "c1"
        assert msgs[1]["content"] == "结果A"

    def test_result_count_mismatch_is_tolerated(self):
        calls = [ToolCall(id="c1", name="a"), ToolCall(id="c2", name="b")]
        msgs = tool_calls_to_messages(calls, ["只有一个"])
        assert len(msgs) == 3
        assert msgs[2]["content"] == ""


# ==================================================================
# 端到端：provider 返回 tool_calls → 执行 → 回填 → 第二轮
# ==================================================================

class _ToolCallingClient:
    """模拟支持原生 function calling 的 provider。"""

    SUPPORTS_TOOLS = True
    DEFAULT_TIMEOUT = 60
    api_key = "sk-testtesttest"

    def __init__(self, tool_name="demo_tool", arguments=None):
        self.calls = []
        self.rounds = 0
        self._tool_name = tool_name
        self._arguments = arguments if arguments is not None else {"value": "原样"}

    def stream_chat(self, model, messages, max_tokens=4096, timeout=None,
                    tools=None, tool_choice=None):
        self.calls.append({
            "model": model, "messages": list(messages),
            "tools": tools, "tool_choice": tool_choice,
        })
        self.rounds += 1
        if self.rounds == 1:
            # 第一轮：请求调用工具
            yield {"content": "", "usage": None, "tool_calls": [
                _delta(0, "call_abc", self._tool_name,
                       json.dumps(self._arguments, ensure_ascii=False)),
            ]}
        else:
            # 第二轮：基于工具结果作答
            yield {"content": "工具结果已消化", "usage": None}
        yield {"content": "", "usage": {"total_tokens": 10}}


class _RecordingExecutor:
    """记录被调用的工具。"""

    def __init__(self, payload="工具返回值"):
        self.payload = payload
        self.invocations = []

    def invoke_tool(self, tool_name, kwargs):
        self.invocations.append((tool_name, dict(kwargs or {})))
        from fr_cli.core.result import Result
        return Result.ok(self.payload)


def _make_state(client, executor):
    return SimpleNamespace(
        client=client,
        model_name="test-model",
        provider="test",
        lang="zh",
        limit=1024,
        cfg={"function_calling": True},
        executor=executor,
        vfs=SimpleNamespace(cwd=None),
        security=None,
        plugins={},
        messages=[],
        get_messages=lambda: [],
    )


class TestNativeToolCallingFlow:

    def test_tool_executed_and_result_fed_back(self):
        from fr_cli.core.chat.pipeline_respond import _stream_and_respond

        client = _ToolCallingClient()
        executor = _RecordingExecutor("答案是 42")
        state = _make_state(client, executor)

        messages = [{"role": "user", "content": "帮我算一下"}]
        txt, usage, rt = _stream_and_respond(state, messages, "帮我算一下", "zh")

        assert executor.invocations == [("demo_tool", {"value": "原样"})]
        assert txt == "工具结果已消化"
        # 协议回填：assistant(tool_calls) + role="tool"
        roles = [m.get("role") for m in messages]
        assert "tool" in roles
        tool_msg = next(m for m in messages if m.get("role") == "tool")
        assert tool_msg["tool_call_id"] == "call_abc"
        assert tool_msg["content"] == "答案是 42"

    def test_tools_payload_sent_to_provider(self):
        from fr_cli.core.chat.pipeline_respond import _stream_and_respond

        client = _ToolCallingClient()
        state = _make_state(client, _RecordingExecutor())
        _stream_and_respond(state, [{"role": "user", "content": "x"}], "x", "zh")
        first = client.calls[0]
        assert first["tools"], "应把 function schema 传给 provider"
        assert first["tool_choice"] == "auto"

    def test_disabled_by_config_falls_back_to_text_markers(self):
        from fr_cli.core.chat.pipeline_respond import _stream_and_respond

        client = _ToolCallingClient()
        state = _make_state(client, _RecordingExecutor())
        state.cfg = {"function_calling": False}
        _stream_and_respond(state, [{"role": "user", "content": "x"}], "x", "zh")
        assert client.calls[0]["tools"] is None, "关闭后不应发送 tools"

    def test_client_without_support_sends_no_tools(self):
        from fr_cli.core.chat.pipeline_respond import _stream_and_respond

        client = _ToolCallingClient()
        client.SUPPORTS_TOOLS = False
        state = _make_state(client, _RecordingExecutor())
        _stream_and_respond(state, [{"role": "user", "content": "x"}], "x", "zh")
        assert client.calls[0]["tools"] is None

    def test_tool_error_is_fed_back_to_model(self):
        """工具失败也要回填 —— 模型才能自己纠正"""
        from fr_cli.core.chat.pipeline_respond import _stream_and_respond

        class _FailingExecutor:
            def invoke_tool(self, tool_name, kwargs):
                from fr_cli.core.result import Result
                return Result.fail("参数缺失")

        client = _ToolCallingClient()
        state = _make_state(client, _FailingExecutor())
        messages = [{"role": "user", "content": "x"}]
        _stream_and_respond(state, messages, "x", "zh")
        tool_msg = next(m for m in messages if m.get("role") == "tool")
        assert "参数缺失" in tool_msg["content"]


class TestProviderRejectionFallback:
    """provider 不接受 tools 时必须自动退回，而不是整轮失败。"""

    def test_rejection_retries_without_tools(self):
        from fr_cli.core.stream import stream_cnt

        class _RejectingClient:
            SUPPORTS_TOOLS = True
            DEFAULT_TIMEOUT = 60
            api_key = "sk-testtesttest"

            def __init__(self):
                self.attempts = []

            def stream_chat(self, model, messages, max_tokens=4096, timeout=None,
                            tools=None, tool_choice=None):
                self.attempts.append(tools)
                if tools:
                    raise RuntimeError("Invalid parameter: 'tools' is not supported")
                yield {"content": "退回成功", "usage": None}

        client = _RejectingClient()
        txt, _, _, _ = stream_cnt(
            client, "m", [{"role": "user", "content": "hi"}], "zh",
            silent=True, tools=[{"type": "function"}], retry=0,
        )
        assert txt == "退回成功"
        assert len(client.attempts) == 2
        assert client.attempts[0] is not None
        assert client.attempts[1] is None
