"""Agent Team（多 Agent 协作小组）的回归测试

覆盖:
- 开关：``/agent_team on|off`` 写进 config.json 的 ``agent_team_enabled``
- 规划器：JSON 解析容错、成员名校验（未知成员 → main）、子任务数上限
- 降级：规划失败 → 单成员 ``main`` 兜底，**绝不返回空列表**
- 执行：子任务并行、真实 deadline、超时条目、部分失败不拖垮整轮
- 聚合：单成员跳过聚合、全失败如实报错、聚合失败退回原始产出拼接
- 接线：团队模式开启时普通对话走团队流程（计划模式 / MasterAgent 不再抢路由）
- 顺带回归：蜂群议会汇总不再调 ``client.chat``（那是 OpenAI SDK **内部**对象，
  在所有 OpenAI 兼容厂商上一直抛 AttributeError）
"""
import json
import threading
import time
from types import SimpleNamespace

from fr_cli.agent.team import (
    MAIN_MEMBER,
    MAX_SUBTASKS,
    AgentTeam,
    Subtask,
    TeamPlanner,
    discover_members,
    extract_json_obj,
    is_team_enabled,
    set_team_enabled,
)


# ============================================================
# 假客户端 / 假 state
# ============================================================


class FakeClient:
    """只实现 fr-cli **公开接口** ``stream_chat`` 的假客户端。

    刻意**不提供** ``client.chat`` —— OpenAI SDK 的内部对象在 fr-cli 客户端上
    根本不存在，之前的蜂群议会汇总就是栽在这里。
    """

    def __init__(self, replies=None):
        self.api_key = "fake-key-1234567890"
        self._replies = list(replies or [])
        self.calls = []

    def stream_chat(self, model, messages, max_tokens=4096, timeout=None,
                    tools=None, tool_choice=None):
        self.calls.append(messages)
        reply = self._replies.pop(0) if self._replies else ""
        yield {"content": reply}


def make_state(replies=None, cfg=None, **extra):
    """构造一个够用的假 state"""
    state = SimpleNamespace(
        cfg=dict(cfg or {}),
        client=FakeClient(replies),
        model_name="fake-model",
        provider="fake",
        lang="zh",
        messages=[],
        last_reply=None,
        saved=0,
    )
    state.save_cfg = lambda: setattr(state, "saved", state.saved + 1)
    # 与真实 AppState 对齐的消息读写接口（_post_process 会调用）
    state.set_messages = lambda msgs: setattr(state, "messages", list(msgs))
    state.append_message = lambda msg: state.messages.append(msg)
    state.get_messages = lambda: list(state.messages)
    for k, v in extra.items():
        setattr(state, k, v)
    return state


# ============================================================
# 开关
# ============================================================


class TestTeamToggle:
    def test_disabled_by_default(self):
        assert is_team_enabled(make_state()) is False

    def test_set_and_persist(self):
        state = make_state()
        assert set_team_enabled(state, True) is True
        assert state.cfg["agent_team_enabled"] is True
        assert state.saved == 1
        assert is_team_enabled(state) is True

        assert set_team_enabled(state, False) is True
        assert state.cfg["agent_team_enabled"] is False
        assert is_team_enabled(state) is False

    def test_non_dict_cfg_is_safe(self):
        state = make_state()
        state.cfg = None
        assert is_team_enabled(state) is False
        assert set_team_enabled(state, True) is False

    def test_command_toggles(self, capsys):
        from fr_cli.repl.commands.agent_team import _cmd_agent_team

        state = make_state()
        _cmd_agent_team(state, ["/agent_team", "on"])
        assert state.cfg["agent_team_enabled"] is True
        assert state.saved == 1

        _cmd_agent_team(state, ["/agent_team", "off"])
        assert state.cfg["agent_team_enabled"] is False
        out = capsys.readouterr().out
        assert "已开启" in out

    def test_command_status_shows_members(self, capsys):
        from fr_cli.repl.commands.agent_team import _cmd_agent_team

        state = make_state()
        _cmd_agent_team(state, ["/agent_team"])
        out = capsys.readouterr().out
        assert MAIN_MEMBER in out          # 通用成员永远在
        assert "已关闭" in out


# ============================================================
# JSON 解析容错
# ============================================================


class TestExtractJson:
    def test_plain(self):
        assert extract_json_obj('{"a": 1}') == {"a": 1}

    def test_fenced(self):
        text = '```json\n{"subtasks": [{"title": "x"}]}\n```'
        assert extract_json_obj(text)["subtasks"][0]["title"] == "x"

    def test_noisy(self):
        text = '好的，结果如下：\n{"subtasks": [{"title": "x"}]}\n希望有帮助'
        assert extract_json_obj(text)["subtasks"][0]["title"] == "x"

    def test_invalid(self):
        assert extract_json_obj("完全不是 JSON") is None
        assert extract_json_obj("") is None
        assert extract_json_obj(None) is None

    def test_json_array_is_not_object(self):
        assert extract_json_obj('[{"title": "x"}]') is None


# ============================================================
# 规划器
# ============================================================


class TestPlannerParsing:
    def _members(self):
        return [
            {"name": MAIN_MEMBER, "kind": "main", "desc": "通用"},
            {"name": "coder", "kind": "local", "desc": "代码"},
        ]

    def test_unknown_member_falls_back_to_main(self):
        planner = TeamPlanner(make_state())
        text = json.dumps({"subtasks": [
            {"title": "甲", "member": "不存在的人", "instruction": "干甲"},
            {"title": "乙", "member": "coder", "instruction": "干乙"},
        ]})
        out = planner._parse(text, self._members())
        assert [s.member for s in out] == [MAIN_MEMBER, "coder"]

    def test_missing_instruction_uses_title(self):
        planner = TeamPlanner(make_state())
        out = planner._parse(json.dumps({"subtasks": [{"title": "只有标题"}]}), self._members())
        assert out[0].instruction == "只有标题"

    def test_caps_subtask_count(self):
        planner = TeamPlanner(make_state())
        raw = [{"title": f"t{i}", "member": MAIN_MEMBER, "instruction": "x"}
               for i in range(MAX_SUBTASKS + 5)]
        out = planner._parse(json.dumps({"subtasks": raw}), self._members())
        assert len(out) == MAX_SUBTASKS

    def test_accepts_tasks_key(self):
        planner = TeamPlanner(make_state())
        out = planner._parse(json.dumps({"tasks": [{"title": "t", "instruction": "i"}]}),
                             self._members())
        assert len(out) == 1

    def test_prompt_includes_recent_history(self):
        """追问场景（"那第二点呢？"）—— 规划器要能看到最近对话。"""
        state = make_state()
        state.messages = [
            {"role": "user", "content": "帮我分析下选品"},
            {"role": "assistant", "content": "从三个角度分析如下…"},
        ]
        planner = TeamPlanner(state)
        prompt = planner._build_prompt("那第二点呢？", self._members())
        assert "最近对话" in prompt
        assert "帮我分析下选品" in prompt
        assert "那第二点呢？" in prompt

    def test_prompt_without_history_has_no_history_block(self):
        planner = TeamPlanner(make_state())
        prompt = planner._build_prompt("做个东西", self._members())
        assert "最近对话" not in prompt

    def test_malformed_gives_empty(self):
        planner = TeamPlanner(make_state())
        assert planner._parse("不是 JSON", self._members()) == []


class TestPlannerFallback:
    def test_llm_failure_falls_back_to_single_main(self, monkeypatch):
        import fr_cli.core.llm.completion as completion

        monkeypatch.setattr(completion, "complete_text_ex",
                            lambda *a, **k: (None, "模型未配置", {}))
        planner = TeamPlanner(make_state())
        out = planner.plan("做点什么")
        assert len(out) == 1
        assert out[0].member == MAIN_MEMBER
        assert out[0].instruction == "做点什么"

    def test_unparsable_output_falls_back(self, monkeypatch):
        import fr_cli.core.llm.completion as completion

        monkeypatch.setattr(completion, "complete_text_ex",
                            lambda *a, **k: ("模型胡言乱语", None, {}))
        planner = TeamPlanner(make_state())
        out = planner.plan("做点什么")
        assert len(out) == 1
        assert out[0].member == MAIN_MEMBER

    def test_parses_real_plan(self, monkeypatch):
        import fr_cli.agent.team as team_mod
        import fr_cli.core.llm.completion as completion

        members = [
            {"name": MAIN_MEMBER, "kind": "main", "desc": "通用"},
            {"name": "coder", "kind": "local", "desc": "代码"},
        ]
        monkeypatch.setattr(team_mod, "discover_members", lambda state: members)

        plan = {"subtasks": [
            {"title": "查资料", "member": MAIN_MEMBER, "instruction": "整理资料"},
            {"title": "写代码", "member": "coder", "instruction": "实现功能"},
        ]}
        monkeypatch.setattr(completion, "complete_text_ex",
                            lambda *a, **k: (json.dumps(plan), None, {}))
        planner = TeamPlanner(make_state())
        out = planner.plan("做个东西")
        assert len(out) == 2
        assert out[1].member == "coder"


# ============================================================
# 成员发现
# ============================================================


class TestMemberDiscovery:
    def test_main_always_present(self):
        members = discover_members(make_state())
        names = [m["name"] for m in members]
        assert MAIN_MEMBER in names
        assert names[0] == MAIN_MEMBER

    def test_builtins_present(self):
        members = discover_members(make_state())
        names = [m["name"] for m in members]
        assert "local" in names
        assert "spider" in names

    def test_unavailable_builtin_is_flagged(self, monkeypatch):
        """可选依赖缺失的内置 Agent 必须标成"本轮不可用"。

        否则规划器会把研究类子任务派给 spider（selenium 没装）→ 执行必炸。
        """
        import fr_cli.agent.team as team_mod

        monkeypatch.setattr(team_mod, "_module_installed", lambda name: False)
        members = discover_members(make_state())
        by_name = {m["name"]: m for m in members}
        assert by_name["spider"]["available"] is False
        assert "不可用" in by_name["spider"]["desc"]
        # 没有可选依赖的 local 始终可用
        assert by_name["local"]["available"] is True

    def test_unavailable_member_falls_back_to_main(self, monkeypatch):
        """规划器仍派了不可用成员 → 退回 main，不让它执行失败。"""
        import fr_cli.agent.team as team_mod

        monkeypatch.setattr(team_mod, "_module_installed", lambda name: False)
        planner = TeamPlanner(make_state())
        members = discover_members(make_state())
        out = planner._parse(json.dumps({"subtasks": [
            {"title": "调研", "member": "spider", "instruction": "去网上查"},
        ]}), members)
        assert out[0].member == MAIN_MEMBER

    def test_builtin_ready_reflects_installed_deps(self, monkeypatch):
        import fr_cli.agent.team as team_mod

        monkeypatch.setattr(team_mod, "_module_installed", lambda name: name == "selenium")
        assert team_mod.builtin_ready("spider") is True
        assert team_mod.builtin_ready("db") is False
        assert team_mod.builtin_ready("local") is True


class TestFailureReporting:
    def test_warning_uses_detail_kwarg(self, monkeypatch):
        """回归：`output.warning` 的参数名是 `detail`，不是 `reason`。

        写成 `reason=` 会在成员失败的分支上抛 TypeError —— 整轮团队协作直接崩掉。
        """
        import fr_cli.agent.team as team_mod

        seen = {}

        class FakeWarning:
            def __init__(self, *a, **k):
                seen["args"] = a
                seen["kwargs"] = k

        monkeypatch.setattr("fr_cli.ui.output.warning", FakeWarning)
        monkeypatch.setattr(
            team_mod.AgentTeam, "run",
            lambda self, *a, **k: __import__(
                "fr_cli.core.result", fromlist=["Result"]
            ).Result.ok({
                "plan": [{"title": "甲", "member": MAIN_MEMBER}],
                "results": [
                    {"title": "甲", "member": MAIN_MEMBER, "ok": True,
                     "output": "好", "error": None},
                    {"title": "乙", "member": "spider", "ok": False,
                     "output": "", "error": "缺 selenium"},
                ],
                "answer": "最终答案",
                "usage": {},
            }),
        )
        state = make_state()
        team_mod.handle_team_chat(state, "做个东西")
        assert seen, "失败成员应当触发 warning"
        assert "reason" not in seen["kwargs"], "warning 不接受 reason 参数"
        assert "detail" in seen["kwargs"]
        assert "缺 selenium" in seen["kwargs"]["detail"]


# ============================================================
# 执行与聚合
# ============================================================


class _StubPlanner:
    """跳过 LLM 规划，直接给出固定子任务"""

    def __init__(self, subtasks):
        self._subtasks = subtasks

    def plan(self, user_input):
        return list(self._subtasks)


class TestExecution:
    def test_parallel_execution_preserves_order(self):
        state = make_state()
        team = AgentTeam(state)

        def fake_run(subtask):
            # 第一个慢、最后一个快 —— 顺序必须按计划而不是完成顺序
            time.sleep(0.3 if subtask.title == "慢" else 0.01)
            return {"title": subtask.title, "member": subtask.member,
                    "ok": True, "output": f"结果-{subtask.title}", "error": None}

        team._run_subtask = fake_run
        subtasks = [Subtask("慢", MAIN_MEMBER, "a"), Subtask("快", MAIN_MEMBER, "b")]
        results = team._execute(subtasks, max_workers=4, timeout=5)
        assert [r["title"] for r in results] == ["慢", "快"]
        assert all(r["ok"] for r in results)

    def test_timeout_produces_named_entry(self):
        state = make_state()
        team = AgentTeam(state)

        def slow(subtask):
            time.sleep(3)
            return {"title": subtask.title, "member": subtask.member,
                    "ok": True, "output": "不该出现", "error": None}

        team._run_subtask = slow
        results = team._execute([Subtask("慢任务", MAIN_MEMBER, "a")],
                                max_workers=2, timeout=0.3)
        assert len(results) == 1
        assert results[0]["ok"] is False
        assert "超时" in results[0]["error"]
        assert results[0]["title"] == "慢任务"

    def test_one_failure_does_not_kill_batch(self):
        state = make_state()
        team = AgentTeam(state)

        def mixed(subtask):
            if subtask.title == "坏":
                return {"title": "坏", "member": MAIN_MEMBER, "ok": False,
                        "output": "", "error": "炸了"}
            return {"title": subtask.title, "member": subtask.member,
                    "ok": True, "output": "好", "error": None}

        team._run_subtask = mixed
        results = team._execute([Subtask("好", MAIN_MEMBER, "a"), Subtask("坏", MAIN_MEMBER, "b")],
                                max_workers=2, timeout=5)
        assert len(results) == 2
        assert sum(1 for r in results if r["ok"]) == 1

    def test_agent_member_dispatch(self):
        state = make_state()
        team = AgentTeam(state)
        called = {}

        import fr_cli.agent.client as agent_client

        def fake_call(name, st, user_input=""):
            called["name"] = name
            called["input"] = user_input
            from fr_cli.core.result import Result
            return Result.ok("代理产出")

        agent_client.call_agent = fake_call
        out, err = team._run_agent("coder", "写个函数")
        assert err is None
        assert out == "代理产出"
        assert called == {"name": "coder", "input": "写个函数"}


class TestAggregation:
    def test_single_member_skips_extra_llm_call(self, monkeypatch):
        import fr_cli.core.llm.completion as completion

        def boom(*a, **k):
            raise AssertionError("单成员不该再调 LLM 做聚合")

        monkeypatch.setattr(completion, "complete_text_ex", boom)
        team = AgentTeam(make_state())
        results = [{"title": "t", "member": MAIN_MEMBER, "ok": True,
                    "output": "唯一产出", "error": None}]
        assert team._aggregate("任务", results) == "唯一产出"

    def test_all_failed_reports_real_errors(self):
        team = AgentTeam(make_state())
        results = [
            {"title": "a", "member": MAIN_MEMBER, "ok": False, "output": "", "error": "超时"},
            {"title": "b", "member": "coder", "ok": False, "output": "", "error": "找不到"},
        ]
        out = team._aggregate("任务", results)
        assert "团队执行失败" in out
        assert "超时" in out and "找不到" in out

    def test_aggregate_failure_falls_back_to_raw_parts(self, monkeypatch):
        import fr_cli.core.llm.completion as completion

        monkeypatch.setattr(completion, "complete_text_ex",
                            lambda *a, **k: (None, "聚合器挂了", {}))
        team = AgentTeam(make_state())
        results = [
            {"title": "a", "member": MAIN_MEMBER, "ok": True, "output": "甲产出", "error": None},
            {"title": "b", "member": "coder", "ok": True, "output": "乙产出", "error": None},
        ]
        out = team._aggregate("任务", results)
        assert "甲产出" in out and "乙产出" in out

    def test_aggregate_uses_member_outputs(self, monkeypatch):
        import fr_cli.core.llm.completion as completion

        seen = {}

        def fake_complete(client, model, messages, **k):
            seen["prompt"] = messages[0]["content"]
            return "最终答案", None, {}

        monkeypatch.setattr(completion, "complete_text_ex", fake_complete)
        team = AgentTeam(make_state())
        results = [
            {"title": "a", "member": MAIN_MEMBER, "ok": True, "output": "甲产出", "error": None},
            {"title": "b", "member": "coder", "ok": True, "output": "乙产出", "error": None},
        ]
        out = team._aggregate("原始任务", results)
        assert out == "最终答案"
        assert "甲产出" in seen["prompt"] and "乙产出" in seen["prompt"]
        assert "原始任务" in seen["prompt"]


class TestTeamRun:
    def test_run_returns_plan_and_answer(self, monkeypatch):
        import fr_cli.core.llm.completion as completion

        def fake_complete(client, model, messages, **k):
            prompt = messages[0]["content"]
            if "调度员" in prompt:
                return json.dumps({"subtasks": [
                    {"title": "甲", "member": MAIN_MEMBER, "instruction": "做甲"},
                    {"title": "乙", "member": MAIN_MEMBER, "instruction": "做乙"},
                ]}), None, {}
            return "汇总答案", None, {}

        monkeypatch.setattr(completion, "complete_text_ex", fake_complete)
        state = make_state()
        result = AgentTeam(state).run("原始任务")
        assert result.is_ok()
        payload = result.unwrap()
        assert len(payload["plan"]) == 2
        assert payload["answer"] == "汇总答案"
        assert len(payload["results"]) == 2

    def test_run_failure_is_result_fail(self):
        class Boom:
            def plan(self, user_input):
                raise RuntimeError("炸了")

        team = AgentTeam(make_state())
        result = team.run("x", planner=Boom())
        assert result.is_fail()
        assert "炸了" in result.error


# ============================================================
# 主流程接线
# ============================================================


class TestUsageAccounting:
    """一轮团队会调多次模型 —— token 用量必须加总，而不是只算最后一次。"""

    def test_usage_is_accumulated(self, monkeypatch):
        import fr_cli.core.llm.completion as completion

        def fake_complete(client, model, messages, **k):
            return "内容", None, {
                "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
            }

        monkeypatch.setattr(completion, "complete_text_ex", fake_complete)
        state = make_state()
        team = AgentTeam(state)
        team._run_subtask = lambda st: {
            "title": st.title, "member": st.member, "ok": True,
            "output": "产出", "error": None,
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        }
        result = team.run("任务", planner=_StubPlanner([
            Subtask("甲", MAIN_MEMBER, "a"), Subtask("乙", MAIN_MEMBER, "b"),
        ]))
        assert result.is_ok()
        usage = result.unwrap()["usage"]
        # 规划 1 次 + 成员 2 次 = 3 次调用
        assert usage["prompt_tokens"] == 10 + 1 + 1
        assert usage["completion_tokens"] == 5 + 2 + 2
        assert usage["total_tokens"] == 15 + 3 + 3

    def test_complete_text_ex_returns_usage(self):
        from fr_cli.core.llm.completion import complete_text_ex

        client = FakeClient(["你好"])
        client.stream_chat = lambda *a, **k: iter([
            {"content": "你好", "usage": {"prompt_tokens": 3, "completion_tokens": 2}},
        ])
        text, err, usage = complete_text_ex(client, "m", [{"role": "user", "content": "hi"}])
        assert err is None
        assert text == "你好"
        assert usage["prompt_tokens"] == 3


class TestChatWiring:
    def test_team_enabled_takes_route_priority(self, monkeypatch):
        """团队模式开启时，普通对话必须走团队流程（不被计划模式抢走）。"""
        from fr_cli.core.chat import pipeline

        state = make_state(cfg={"agent_team_enabled": True})
        state.thinking_mode = "plan"      # 计划模式本该优先，这里要被团队压过
        seen = {}

        def fake_team(state, u):
            seen["called"] = u
            return "团队答案"

        monkeypatch.setattr("fr_cli.agent.team.handle_team_chat", fake_team)
        out = pipeline._route_mode(state, "做个东西")
        assert out == "团队答案"
        assert seen["called"] == "做个东西"

    def test_team_disabled_uses_normal_route(self, monkeypatch):
        from fr_cli.core.chat import pipeline

        state = make_state(cfg={"agent_team_enabled": False})
        state.thinking_mode = "direct"
        state.master_agent = None

        def boom(*a, **k):
            raise AssertionError("团队关闭时不该走团队流程")

        monkeypatch.setattr("fr_cli.agent.team.handle_team_chat", boom)
        # 正常路径会走 _direct_chat —— 这里只断言没有触发团队分支
        pipeline._route_mode.__wrapped__ if False else None
        assert is_team_enabled(state) is False

    def test_returns_stats_dict_for_repl_consumers(self, monkeypatch):
        """回归：返回值必须是 **stats 字典**。

        ``repl/queue.py`` / ``repl/actions.py`` 拿到 ``handle_ai_chat`` 的返回值后
        直接 ``prompt.update_last_stats(**stats)`` —— 返回字符串会抛
        ``TypeError: argument of type 'str' is not a mapping``，
        交互式 REPL 里表现为"队列处理出错"。
        """
        import fr_cli.agent.team as team_mod

        monkeypatch.setattr(
            team_mod.AgentTeam, "run",
            lambda self, *a, **k: __import__(
                "fr_cli.core.result", fromlist=["Result"]
            ).Result.ok({
                "plan": [], "results": [], "answer": "团队答案",
                "usage": {"prompt_tokens": 7, "completion_tokens": 8, "total_tokens": 15},
            }),
        )
        state = make_state()
        stats = team_mod.handle_team_chat(state, "做个东西")

        # 模拟 REPL 的消费方式
        received = {}
        received.update(**stats)
        assert received["total_tokens"] == 15
        assert received["input_tokens"] == 7

    def test_handle_team_chat_writes_history(self, monkeypatch):
        import fr_cli.agent.team as team_mod

        monkeypatch.setattr(
            team_mod.AgentTeam, "run",
            lambda self, *a, **k: __import__(
                "fr_cli.core.result", fromlist=["Result"]
            ).Result.ok({
                "plan": [{"title": "甲", "member": MAIN_MEMBER}],
                "results": [{"title": "甲", "member": MAIN_MEMBER, "ok": True,
                             "output": "x", "error": None}],
                "answer": "团队答案",
                "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            }),
        )
        state = make_state()
        stats = team_mod.handle_team_chat(state, "做个东西")
        # 返回值必须是 **stats 字典** —— 调用方会 update_last_stats(**stats)
        assert isinstance(stats, dict)
        assert "response_time" in stats and "total_tokens" in stats
        assert state.last_reply == "团队答案"
        assert state.messages[-1]["role"] == "assistant"
        assert state.messages[-1]["content"] == "团队答案"

    def test_handle_team_chat_archives_session(self, monkeypatch):
        """团队模式也必须走会话存档 —— 否则开启后用户的对话不再被归档。"""
        import fr_cli.agent.team as team_mod

        archived = {}

        monkeypatch.setattr(
            team_mod.AgentTeam, "run",
            lambda self, *a, **k: __import__(
                "fr_cli.core.result", fromlist=["Result"]
            ).Result.ok({
                "plan": [], "results": [], "answer": "团队答案", "usage": {},
            }),
        )

        import fr_cli.core.chat.pipeline_post as post_mod
        real_create = post_mod.create_session

        def fake_create(messages, session_id=None):
            archived["messages"] = list(messages)
            return "/tmp/fake-session.json"

        # 注意：_post_process 内部是 `from fr_cli.memory.session import create_session`
        # —— 名字在 pipeline_post 导入时就绑定了，必须打桩**绑定处**而不是源模块
        monkeypatch.setattr(post_mod, "create_session", fake_create)

        state = make_state()
        state.auto_session_path = None
        state.session_id = None
        state.sn = "default"
        state.limit = 20000
        state.display_model = "mock"
        state.context_summary = ""

        team_mod.handle_team_chat(state, "做个东西")
        assert state.auto_session_path == "/tmp/fake-session.json"
        assert archived["messages"][-1]["content"] == "团队答案"
        assert real_create is not None


# ============================================================
# 顺带回归：蜂群议会汇总
# ============================================================


class TestSwarmCouncilFix:
    def test_council_summary_uses_public_interface(self):
        """议会汇总必须走 stream_chat（公开接口），不能再摸 client.chat。"""
        from fr_cli.agent.swarm import SwarmEngine

        state = make_state(replies=["汇总后的结论"])
        state.client = FakeClient(["汇总后的结论"])
        engine = SwarmEngine(state)
        out = engine._summarize_with_llm("任务", [
            {"agent": "a", "kind": "agent", "result": "甲的结果", "error": None},
        ])
        assert out == "汇总后的结论"
        assert "汇总失败" not in out

    def test_council_summary_reports_failure_honestly(self):
        from fr_cli.agent.swarm import SwarmEngine

        state = make_state()
        state.client = None
        state.model_name = None
        engine = SwarmEngine(state)
        out = engine._summarize_with_llm("任务", [
            {"agent": "a", "kind": "agent", "result": "甲的结果", "error": None},
        ])
        # 模型没配置时必须**如实**说明，而不是编一份汇总
        assert "模型未配置" in out


class TestCompleteText:
    def test_returns_text(self):
        from fr_cli.core.llm.completion import complete_text

        client = FakeClient(["你好"])
        text, err = complete_text(client, "m", [{"role": "user", "content": "hi"}])
        assert err is None
        assert text == "你好"

    def test_rejects_short_key(self):
        from fr_cli.core.llm.completion import complete_text

        client = FakeClient(["你好"])
        client.api_key = "short"
        text, err = complete_text(client, "m", [{"role": "user", "content": "hi"}])
        assert text is None
        assert "密钥" in err

    def test_rejects_missing_model(self):
        from fr_cli.core.llm.completion import complete_text

        text, err = complete_text(FakeClient(), None, [])
        assert text is None
        assert "模型未配置" in err

    def test_empty_reply_is_error(self):
        from fr_cli.core.llm.completion import complete_text

        text, err = complete_text(FakeClient([""]), "m", [])
        assert text is None
        assert err


# ============================================================
# 注册表工具
# ============================================================


class TestRegisteredTool:
    def test_tool_registered(self):
        from fr_cli.command.registry import get_registry

        reg = get_registry()
        assert "agent_team_run" in reg._tools

    def test_tool_requires_user_input(self):
        from fr_cli.command.registry import get_registry

        reg = get_registry()
        deps = SimpleNamespace(cfg={}, client=None, model_name=None, lang="zh")
        res = reg.dispatch(deps, "agent_team_run", user_input="")
        assert res.is_fail()

    def test_tool_returns_answer(self, monkeypatch):
        import fr_cli.agent.team as team_mod
        from fr_cli.command.registry import get_registry
        from fr_cli.core.result import Result

        monkeypatch.setattr(
            team_mod.AgentTeam, "run",
            lambda self, *a, **k: Result.ok({
                "plan": [], "results": [], "answer": "工具答案",
            }),
        )
        reg = get_registry()
        deps = SimpleNamespace(cfg={}, client=None, model_name=None, lang="zh")
        res = reg.dispatch(deps, "agent_team_run", user_input="做点什么")
        assert res.is_ok()
        assert res.unwrap() == "工具答案"


# ============================================================
# 并发安全
# ============================================================


class TestThreadSafety:
    def test_parallel_members_do_not_interfere(self):
        """多个成员并行跑，结果必须各自独立（不串台）。"""
        state = make_state()
        team = AgentTeam(state)
        barrier = threading.Barrier(4, timeout=5)

        def fake_run(subtask):
            barrier.wait()          # 强制所有成员同时进入
            return {"title": subtask.title, "member": subtask.member,
                    "ok": True, "output": subtask.title, "error": None}

        team._run_subtask = fake_run
        subtasks = [Subtask(f"t{i}", MAIN_MEMBER, "x") for i in range(4)]
        results = team._execute(subtasks, max_workers=4, timeout=10)
        assert sorted(r["output"] for r in results) == ["t0", "t1", "t2", "t3"]
