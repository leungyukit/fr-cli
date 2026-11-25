"""脚本化 Mock LLM（``fr_cli.core.llm.mock``）的单元测试。

覆盖：
* 向后兼容 —— ``MockLLMClient`` 的回声行为**一个字都没变**
* 序列模式 —— 第 n 次调用返回第 n 条脚本
* 匹配模式 —— 按输入内容匹配（子串 / 正则 / 可调用对象）
* 录制 / 回放 —— ``RecordingClient`` 录成 fixture，``ScriptedMockClient`` 回放
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_EVAL_DIR = Path(__file__).resolve().parent
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from fr_cli.core.llm.mock import (  # noqa: E402  (路径引导必须在 import 之前)
    DEFAULT_SCRIPTED_RESPONSE,
    MockClient,
    MockLLMClient,
    RecordingClient,
    ScriptedMockClient,
)


def _turn(client, messages, model="mock"):
    """跑一轮 LLM，把流式 chunk 拼成完整文本。"""
    return "".join(
        chunk.get("content", "")
        for chunk in client.stream_chat(model, messages)
    )


# ------------------------------------------------------------------
# 向后兼容
# ------------------------------------------------------------------
class TestBackwardCompatibility:
    def test_echo_behavior_unchanged(self):
        """回声式 mock 的三种既有分支必须原样保留。"""
        client = MockLLMClient()
        assert "【Mock 模式】" in _turn(client, [{"role": "user", "content": "你好"}])
        assert "你输入了命令" in _turn(client, [{"role": "user", "content": "/ls"}])
        assert "没收到你的输入" in _turn(client, [{"role": "user", "content": ""}])

    def test_mock_client_alias(self):
        """``MockClient`` 是 ``MockLLMClient`` 的别名。"""
        assert MockClient is MockLLMClient

    def test_default_model_name_unchanged(self):
        client = MockLLMClient()
        assert client.model == "mock-echo"
        assert client.is_mock is True
        assert client.SUPPORTS_TOOLS is False

    def test_usage_chunk_still_present(self):
        """最后一个 chunk 仍然带 usage。"""
        chunks = list(MockLLMClient().stream_chat("m", [{"role": "user", "content": "x"}]))
        assert chunks[-1]["usage"] is not None
        assert "total_tokens" in chunks[-1]["usage"]

    def test_scripted_params_opt_in(self):
        """传了 script 才切脚本化 —— 不传就是老行为。"""
        client = MockLLMClient(script=["A", "B"])
        assert _turn(client, [{"role": "user", "content": "q"}]) == "A"
        assert _turn(client, [{"role": "user", "content": "q"}]) == "B"


# ------------------------------------------------------------------
# 序列模式
# ------------------------------------------------------------------
class TestSequenceMode:
    def test_nth_call_returns_nth_script(self):
        client = ScriptedMockClient(script=["A", "B", "C"])
        assert _turn(client, [{"role": "user", "content": "x"}]) == "A"
        assert _turn(client, [{"role": "user", "content": "x"}]) == "B"
        assert _turn(client, [{"role": "user", "content": "x"}]) == "C"

    def test_fallback_after_script_exhausted(self):
        client = ScriptedMockClient(script=["A"])
        _turn(client, [{"role": "user", "content": "x"}])
        assert _turn(client, [{"role": "user", "content": "x"}]) == DEFAULT_SCRIPTED_RESPONSE

    def test_custom_default_response(self):
        client = ScriptedMockClient(default_response="兜底")
        assert _turn(client, [{"role": "user", "content": "x"}]) == "兜底"

    def test_push_appends(self):
        client = ScriptedMockClient()
        client.push("第一条").push("第二条")
        assert _turn(client, [{"role": "user", "content": "x"}]) == "第一条"
        assert _turn(client, [{"role": "user", "content": "x"}]) == "第二条"

    def test_reset_restarts_sequence(self):
        client = ScriptedMockClient(script=["A", "B"])
        _turn(client, [{"role": "user", "content": "x"}])
        client.reset()
        assert client.call_index == 0
        assert _turn(client, [{"role": "user", "content": "x"}]) == "A"


# ------------------------------------------------------------------
# 匹配模式
# ------------------------------------------------------------------
class TestMatchMode:
    def test_substring_match(self):
        client = ScriptedMockClient(rules=[("关键词", "命中")])
        assert _turn(client, [{"role": "user", "content": "这里有关键词啊"}]) == "命中"

    def test_regex_match(self):
        client = ScriptedMockClient(rules=[(re.compile(r"^tool"), "命中")])
        assert _turn(client, [{"role": "user", "content": "tool xxx"}]) == "命中"

    def test_callable_match(self):
        client = ScriptedMockClient(
            rules=[(lambda msgs: msgs[-1]["content"].endswith("?"), "问句")]
        )
        assert _turn(client, [{"role": "user", "content": "在吗?"}]) == "问句"

    def test_dict_rule_form(self):
        client = ScriptedMockClient(rules=[{"pattern": "abc", "response": "命中"}])
        assert _turn(client, [{"role": "user", "content": "xxabcxx"}]) == "命中"

    def test_rule_wins_over_script(self):
        """规则优先于序列。"""
        client = ScriptedMockClient(script=["脚本"], rules=[("关键词", "规则")])
        assert _turn(client, [{"role": "user", "content": "关键词"}]) == "规则"

    def test_first_matching_rule_wins(self):
        client = ScriptedMockClient(rules=[("a", "第一条"), ("b", "第二条")])
        assert _turn(client, [{"role": "user", "content": "ab"}]) == "第一条"

    def test_match_first_user_message_in_multiturn(self):
        """多轮流程里，第一条 user 消息（任务输入）仍能命中规则。"""
        client = ScriptedMockClient(rules=[("原始任务", "命中")])
        messages = [
            {"role": "user", "content": "原始任务"},
            {"role": "user", "content": "[工具结果] write_file 执行成功"},
        ]
        assert _turn(client, messages) == "命中"

    def test_on_method_appends_rule(self):
        client = ScriptedMockClient()
        client.on("关键词", "命中")
        assert _turn(client, [{"role": "user", "content": "关键词"}]) == "命中"


# ------------------------------------------------------------------
# 录制 / 回放
# ------------------------------------------------------------------
class TestRecordReplay:
    def test_recording_captures_responses(self):
        recorder = RecordingClient(ScriptedMockClient(script=["R1", "R2"]))
        _turn(recorder, [{"role": "user", "content": "一"}])
        _turn(recorder, [{"role": "user", "content": "二"}])
        assert len(recorder.calls) == 2
        assert recorder.calls[0]["response"] == "R1"
        assert recorder.calls[1]["messages"][0]["content"] == "二"

    def test_save_and_replay_by_sequence(self, tmp_path):
        recorder = RecordingClient(ScriptedMockClient(script=["R1", "R2"]))
        _turn(recorder, [{"role": "user", "content": "一"}])
        _turn(recorder, [{"role": "user", "content": "二"}])
        path = recorder.save_fixture(tmp_path / "fx.json")
        assert path.exists()

        player = ScriptedMockClient.load_fixture(path)
        assert _turn(player, [{"role": "user", "content": "一"}]) == "R1"
        assert _turn(player, [{"role": "user", "content": "二"}]) == "R2"

    def test_save_and_replay_by_match(self, tmp_path):
        recorder = RecordingClient(ScriptedMockClient(script=["R1", "R2"]))
        _turn(recorder, [{"role": "user", "content": "唯一输入"}])
        path = recorder.save_fixture(tmp_path / "fx.json")

        player = ScriptedMockClient.load_fixture(path, mode="match")
        assert _turn(player, [{"role": "user", "content": "唯一输入"}]) == "R1"

    def test_fixture_roundtrip_preserves_format(self, tmp_path):
        recorder = RecordingClient(ScriptedMockClient(script=["中文响应"]))
        _turn(recorder, [{"role": "user", "content": "输入"}])
        path = recorder.save_fixture(tmp_path / "fx.json")
        payload = __import__("json").loads(path.read_text(encoding="utf-8"))
        assert payload["kind"] == "fr_cli.llm.fixture"
        assert payload["calls"][0]["response"] == "中文响应"

    def test_load_rejects_non_fixture(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text('{"kind": "other", "calls": []}', encoding="utf-8")
        with pytest.raises(ValueError):
            ScriptedMockClient.load_fixture(bad)


# ------------------------------------------------------------------
# 其他
# ------------------------------------------------------------------
class TestMisc:
    def test_calls_are_recorded(self):
        client = ScriptedMockClient(script=["A"])
        _turn(client, [{"role": "user", "content": "x"}])
        assert len(client.calls) == 1
        assert client.last_response == "A"

    def test_usage_payload_present(self):
        chunks = list(ScriptedMockClient(script=["A"]).stream_chat(
            "m", [{"role": "user", "content": "x"}]
        ))
        assert chunks[-1]["usage"]["total_tokens"] >= 0

    def test_custom_usage_payload(self):
        client = ScriptedMockClient(script=["A"], usage={"total_tokens": 42})
        chunks = list(client.stream_chat("m", [{"role": "user", "content": "x"}]))
        assert chunks[-1]["usage"]["total_tokens"] == 42
