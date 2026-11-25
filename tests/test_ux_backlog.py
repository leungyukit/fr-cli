# -*- coding: utf-8 -*-
"""UX 欠账收口测试 —— P2 细节打磨 + 长线 3/4/5

覆盖：
- 统一 token 显示口径（core/usage.py::format_token_usage 是唯一真相源）
- 多行粘贴降级（/paste）
- 未知命令模糊建议（子序列 + 最多 5 条）
- 原生 function calling 多 tool_calls 并发执行
- 并行执行下的安全确认互斥（不能抢终端）
- 会话增量持久化接线（v1 → v2 迁移 / 增量追加 / 截断重写）
"""
import json
import threading
import time
from pathlib import Path

import pytest

from fr_cli.core.result import Result
from fr_cli.core.usage import format_token_usage


# ===================================================================
# 1. 统一 token 口径
# ===================================================================


class TestTokenUsageFormat:

    def test_same_format_everywhere(self):
        """状态栏与回答末尾必须是同一个格式（此前是两个写法）"""
        text = format_token_usage(100, 200, 300)
        assert text == "↓100 ↑200 Σ300"

    def test_pct_appended_only_with_limit(self):
        assert format_token_usage(100, 200, 300, 2000, with_pct=True) == "↓100 ↑200 Σ300 (15%)"
        assert "%)" not in format_token_usage(100, 200, 300, 0, with_pct=True)

    def test_total_falls_back_to_sum(self):
        assert format_token_usage(10, 20, 0) == "↓10 ↑20 Σ30"

    def test_status_bar_uses_same_helper(self):
        """状态栏的 token 项与回答末尾必须逐字一致（除占比）"""
        from fr_cli.ui.prompt.status import StatusState
        s = StatusState()
        s.provider, s.model = "z", "m"
        s.last_input_tokens, s.last_output_tokens, s.last_total_tokens = 100, 200, 300
        text = "".join(t for _, t in s.render(120))
        assert format_token_usage(100, 200, 300) in text

    def test_dead_tokens_used_branch_removed(self):
        """tokens_used / limit 全仓无人写入 —— 那个分支是死代码，必须删掉"""
        from fr_cli.ui.prompt.status import StatusState
        s = StatusState()
        s.provider, s.model = "z", "m"
        s.tokens_used, s.limit = 500, 2000      # 模拟旧字段有值
        text = "".join(t for _, t in s.render(120))
        assert "500/2000" not in text


# ===================================================================
# 2. 多行粘贴降级（/paste）
# ===================================================================


class TestPasteCommand:

    def test_recognized(self):
        from fr_cli.repl.paste import is_paste_command
        assert is_paste_command("/paste") is True
        assert is_paste_command("  /paste  ") is True
        assert is_paste_command("/pastes") is False
        assert is_paste_command("hello") is False

    def test_collects_until_terminator(self, monkeypatch):
        from fr_cli.repl.paste import collect_multiline
        lines = iter(["line1", "line2", ".", "ignored"])
        monkeypatch.setattr("builtins.input", lambda *a, **k: next(lines))
        out = collect_multiline(None)
        assert out == "line1\nline2"

    def test_collects_until_eof(self, monkeypatch):
        from fr_cli.repl.paste import collect_multiline

        lines = iter(["a", "b"])

        def _input(*args, **kwargs):
            try:
                return next(lines)
            except StopIteration:
                raise EOFError
        monkeypatch.setattr("builtins.input", _input)
        out = collect_multiline(None)
        assert out == "a\nb"

    def test_uses_prompt_runner_when_available(self, monkeypatch):
        """TUI 下要挂起渲染再读 stdin，否则会和渲染打架"""
        from fr_cli.repl.paste import collect_multiline

        calls = []

        class _Prompt:
            @staticmethod
            def _run_in_terminal(func):
                calls.append(func)
                func()

        lines = iter(["x"])

        def _input(*args, **kwargs):
            try:
                return next(lines)
            except StopIteration:
                raise EOFError
        monkeypatch.setattr("builtins.input", _input)
        out = collect_multiline(_Prompt())
        assert calls, "没有走 _run_in_terminal"
        assert out == "x"


# ===================================================================
# 3. 未知命令模糊建议
# ===================================================================


class TestSimilarCmdSuggestions:

    CMDS = ["/help", "/model", "/status", "/usage", "/key", "/limit",
            "/session_list", "/mode", "/exit", "/hermes", "/gatekeeper"]

    def test_subsequence_abbreviation(self):
        """``/mdl`` → ``/model``：子序列匹配（此前一条都匹配不上）"""
        from fr_cli.repl.router import _cmd_similarity
        assert _cmd_similarity("/mdl", "/model") >= 0.6

    def test_prefix_ranks_first(self):
        from fr_cli.repl.router import _cmd_similarity
        assert _cmd_similarity("/stat", "/status") > _cmd_similarity("/stat", "/save")

    def test_short_abbreviation_prefers_real_command(self):
        """``/kee`` 应该是 ``/key`` 而不是 ``/gatekeeper``"""
        from fr_cli.repl.router import _cmd_similarity
        assert _cmd_similarity("/kee", "/key") > _cmd_similarity("/kee", "/gatekeeper")

    def test_garbage_has_no_suggestion(self):
        from fr_cli.repl.router import _cmd_similarity
        assert _cmd_similarity("/zzzzzz", "/model") < 0.4

    def test_at_most_five_suggestions(self, capsys):
        from fr_cli.repl.router import _print_similar_cmds
        _print_similar_cmds("/s", self.CMDS + ["/save", "/start", "/status"])
        out = capsys.readouterr().out
        assert "你是不是想" in out
        assert len([ln for ln in out.splitlines() if ln.strip().startswith("/")]) <= 5


# ===================================================================
# 4. 原生 function calling 并发执行
# ===================================================================


class _FakeExecutor:
    """最小 executor 替身：记录调用 + 模拟耗时"""

    def __init__(self, delay=0.05):
        self.delay = delay
        self.calls = []

    def invoke_tool(self, tool_name, kwargs, msgs=None, skip_security=False,
                    client=None, model_name=None, source=None):
        self.calls.append((tool_name, kwargs))
        time.sleep(self.delay)
        return Result.ok(f"{tool_name}-ok")


class TestParallelNativeToolCalls:

    def test_executes_concurrently(self):
        from fr_cli.command.parallel import ParallelExecutor
        ex = _FakeExecutor(delay=0.1)
        par = ParallelExecutor(ex, max_workers=4)
        start = time.time()
        results = par.execute_parsed([("a", {}), ("b", {}), ("c", {})])
        elapsed = time.time() - start
        assert len(results) == 3
        assert elapsed < 0.25, f"并发没生效（耗时 {elapsed:.2f}s）"

    def test_results_keep_input_order(self):
        """结果必须按调用顺序 —— ``role="tool"`` 消息要与请求一一对应"""
        from fr_cli.command.parallel import ParallelExecutor
        ex = _FakeExecutor(delay=0.02)
        par = ParallelExecutor(ex, max_workers=4)
        results = par.execute_parsed([("a", {}), ("b", {}), ("c", {})])
        assert [r.unwrap() for r in results] == ["a-ok", "b-ok", "c-ok"]

    def test_bad_kwargs_become_failure_not_crash(self):
        from fr_cli.command.parallel import ParallelExecutor
        ex = _FakeExecutor()
        par = ParallelExecutor(ex)
        results = par.execute_parsed([("a", None)])
        assert results[0].is_fail()

    def test_execute_parsed_isolates_msgs(self):
        """每个线程一份 msgs 副本"""
        from fr_cli.command.parallel import ParallelExecutor
        seen = []

        class _Ex:
            def invoke_tool(self, tool_name, kwargs, msgs=None, **kw):
                seen.append(msgs)          # 保留引用（id() 会被复用，不能只存 id）
                if msgs:
                    msgs.append({"role": "user", "content": "x"})
                return Result.ok("ok")

        par = ParallelExecutor(_Ex(), max_workers=2)
        shared = [{"role": "user", "content": "a"}]
        par.execute_parsed([("a", {}), ("b", {})], msgs=shared)
        assert len({id(m) for m in seen}) == 2, "msgs 未隔离"
        assert len(shared) == 1, "原始 msgs 被改动了"


# ===================================================================
# 5. 并行下的安全确认互斥
# ===================================================================


class TestSecurityConfirmLock:

    def test_concurrent_confirms_do_not_interleave(self, monkeypatch):
        """两个线程同时确认时，不能同时占用 input() —— 否则用户的 Y/A/F/N
        可能落到另一个工具上（安全问题，不只是显示问题）"""
        from fr_cli.security.security import ask

        # 自防御：这两个开关会直接短路 ask()，不能被外部环境带进来
        monkeypatch.delenv("FR_CLI_BATCH_CONFIRM", raising=False)
        monkeypatch.delenv("FR_CLI_NON_INTERACTIVE", raising=False)

        state = {"active": 0, "max": 0}
        guard = threading.Lock()

        def fake_input(prompt=""):
            with guard:
                state["active"] += 1
                state["max"] = max(state["max"], state["active"])
            time.sleep(0.05)
            with guard:
                state["active"] -= 1
            return "y"

        monkeypatch.setattr("builtins.input", fake_input)

        results = []
        threads = [
            threading.Thread(target=lambda i=i: results.append(
                ask("sec_read", f"/f{i}", "zh", {}, {}, {})))
            for i in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(results) == 4
        assert state["max"] == 1, f"确认提示并发重入（max={state['max']}）"

    def test_eof_denies_instead_of_raising(self, monkeypatch):
        """EOF（管道关闭）按拒绝处理，不能让整批工具卡死"""
        from fr_cli.security.security import ask

        monkeypatch.delenv("FR_CLI_BATCH_CONFIRM", raising=False)
        monkeypatch.delenv("FR_CLI_NON_INTERACTIVE", raising=False)

        def _eof(*a, **k):
            raise EOFError
        monkeypatch.setattr("builtins.input", _eof)
        ok, _, _ = ask("sec_exec", "rm -rf /", "zh", {}, {}, {})
        assert ok is False


# ===================================================================
# 6. 会话增量持久化接线
# ===================================================================


class TestIncrementalSessionWiring:

    def _session_dir(self, tmp_home):
        return Path(tmp_home) / ".fr_cli" / "sessions" / "auto"

    def test_update_appends_delta_not_whole_file(self, tmp_home, monkeypatch):
        from fr_cli.memory import session as sess

        d = self._session_dir(tmp_home)
        d.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(sess, "SESSION_DIR", d)

        msgs = lambda n: [{"role": "user", "content": f"m{i}"} for i in range(n)]
        path = sess.create_session(msgs(3))
        sess.update_session(path, msgs(5))

        delta = Path(path).with_suffix(".delta")
        assert delta.exists(), "没有生成增量文件"
        assert len(delta.read_text(encoding="utf-8").strip().splitlines()) == 2

    def test_load_merges_snapshot_and_delta(self, tmp_home, monkeypatch):
        from fr_cli.memory import session as sess

        d = self._session_dir(tmp_home)
        d.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(sess, "SESSION_DIR", d)

        msgs = lambda n: [{"role": "user", "content": f"m{i}"} for i in range(n)]
        path = sess.create_session(msgs(3))
        sess.update_session(path, msgs(5))

        ok, loaded, _ = sess.load_session(1)
        assert ok is True
        assert len(loaded) == 5
        assert sess.list_sessions()[0]["msg_count"] == 5

    def test_shrink_triggers_full_rewrite(self, tmp_home, monkeypatch):
        """``/undo`` 截断历史后，增量语义不成立 → 必须全量重写"""
        from fr_cli.memory import session as sess

        d = self._session_dir(tmp_home)
        d.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(sess, "SESSION_DIR", d)

        msgs = lambda n: [{"role": "user", "content": f"m{i}"} for i in range(n)]
        path = sess.create_session(msgs(5))
        sess.update_session(path, msgs(2))

        ok, loaded, _ = sess.load_session(1)
        assert len(loaded) == 2
        assert not Path(path).with_suffix(".delta").exists()

    def test_in_place_edit_triggers_full_rewrite(self, tmp_home, monkeypatch):
        """条数不变但内容被改（原地改写 / system prompt 替换）——
        增量语义不成立，必须全量重写，否则磁盘上是旧内容"""
        from fr_cli.memory import session as sess

        d = self._session_dir(tmp_home)
        d.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(sess, "SESSION_DIR", d)

        path = sess.create_session([{"role": "user", "content": "hi"}])
        sess.update_session(path, [{"role": "user", "content": "updated"}])

        ok, loaded, _ = sess.load_session(1)
        assert [m["content"] for m in loaded] == ["updated"]

    def test_v1_file_is_migrated(self, tmp_home, monkeypatch):
        """存量 v1 文件（messages 直接躺在 json 里）必须能正常读，且不被重复计数"""
        from fr_cli.memory import session as sess

        d = self._session_dir(tmp_home)
        d.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(sess, "SESSION_DIR", d)

        legacy = d / "2020-01-01_01.json"
        legacy.write_text(json.dumps({
            "filename": legacy.name,
            "created_at": "2020-01-01 00:00:00",
            "updated_at": "2020-01-01 00:00:00",
            "messages": [{"role": "user", "content": "old"}],
        }), encoding="utf-8")

        ok, loaded, _ = sess.load_session(1)
        assert ok is True
        assert [m["content"] for m in loaded] == ["old"]

        # 迁移后再增量追加，不能把老消息重复一遍
        msgs = [{"role": "user", "content": "old"}, {"role": "assistant", "content": "new"}]
        sess.update_session(str(legacy), msgs)
        ok, loaded, _ = sess.load_session(1)
        assert [m["content"] for m in loaded] == ["old", "new"]

    def test_delete_removes_side_files(self, tmp_home, monkeypatch):
        from fr_cli.memory import session as sess

        d = self._session_dir(tmp_home)
        d.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(sess, "SESSION_DIR", d)

        msgs = lambda n: [{"role": "user", "content": f"m{i}"} for i in range(n)]
        path = sess.create_session(msgs(1))
        sess.update_session(path, msgs(3))
        assert Path(path).with_suffix(".delta").exists()

        assert sess.delete_session(1) is True
        assert not Path(path).exists()
        assert not Path(path).with_suffix(".delta").exists()
        assert not Path(path).with_suffix(".meta").exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
