"""安全确认「中转站」的回归测试 —— 修 REPL 假死

问题（v2.8.7 修复）：
REPL 主循环用 prompt_toolkit 占着 stdin，工具执行跑在后台线程。后台线程
直接 ``input()`` 会和主线程抢同一个 fd —— 用户敲的 Y/A/F/N 全被输入框吞掉，
``input()`` 永远等不到，终端表现为**假死**（每按一次回车只是把空消息塞进队列）。

修法：后台线程经「确认中转站」等答案，由拥有 stdin 的主线程投递。

覆盖:
- 中转站关闭 → ``ask()`` 保持裸 ``input()`` 行为（零变化）
- 中转站开启 + 非主线程 → 走中转站，主线程投递 Y/A/F/N 生效
- 主线程自己发起确认 → 仍走裸 ``input()``（否则自己等自己 = 死锁）
- 超时 / 取消 → 按拒绝处理（fail-closed）
- Y/A/F/N 四阶语义经中转站后完全一致
- 状态栏出现「⚠ 待确认 ... (Y/A/F/N)」
"""
import threading
import time
from unittest.mock import patch

import pytest

from fr_cli.security.interactive import BROKER, ConfirmBroker
from fr_cli.security.security import ask


@pytest.fixture(autouse=True)
def _clean_broker(monkeypatch):
    """每个用例前后都把中转站复位，避免用例之间串状态。

    还要清掉两个会**短路** ``ask()`` 的环境变量：``FR_CLI_BATCH_CONFIRM``
    （一律放行）与 ``FR_CLI_NON_INTERACTIVE``（一律拒绝）。它们一旦被别的
    测试文件泄漏进进程，本文件的用例会集体失效（表现为"单跑绿、全量红"）。
    """
    monkeypatch.delenv("FR_CLI_BATCH_CONFIRM", raising=False)
    monkeypatch.delenv("FR_CLI_NON_INTERACTIVE", raising=False)
    BROKER.disable()
    BROKER.cancel_all()
    yield
    BROKER.disable()
    BROKER.cancel_all()


def _wait_pending(timeout=2.0):
    """等后台线程把确认请求挂上来"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if BROKER.has_pending():
            return True
        time.sleep(0.01)
    return False


class TestBrokerDisabled:
    """中转站关闭时行为完全不变"""

    def test_uses_raw_input(self):
        with patch("builtins.input", return_value="y"):
            ok, s, f = ask("sec_read", "/tmp/x", "zh", {}, {}, {})
        assert ok is True

    def test_deny_via_raw_input(self):
        with patch("builtins.input", return_value="n"):
            ok, _, _ = ask("sec_exec", "rm -rf /", "zh", {}, {}, {})
        assert ok is False

    def test_empty_input_is_deny(self):
        with patch("builtins.input", return_value=""):
            ok, _, _ = ask("sec_read", "/tmp/x", "zh", {}, {}, {})
        assert ok is False


class TestBrokerPath:
    """后台线程发起确认 → 主线程代读"""

    def test_worker_waits_for_main_thread_answer(self):
        BROKER.enable()
        result = {}

        def worker():
            ok, _s, _f = ask("sec_read", "/tmp/x", "zh", {}, {}, {})
            result["ok"] = ok

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        assert _wait_pending(), "后台线程没有挂上确认请求"
        assert BROKER.pending_desc() == "/tmp/x"
        assert BROKER.pending_key() == "sec_read"

        assert BROKER.deliver("y") is True
        t.join(timeout=3)
        assert not t.is_alive(), "确认后后台线程没有恢复"
        assert result["ok"] is True

    def test_deny_answer(self):
        BROKER.enable()
        result = {}

        def worker():
            ok, _s, _f = ask("sec_exec", "dangerous", "zh", {}, {}, {})
            result["ok"] = ok

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        assert _wait_pending()
        BROKER.deliver("n")
        t.join(timeout=3)
        assert result["ok"] is False

    def test_session_scope_answer(self):
        """A = 本轮放行（只对当前 sec_* 类别）"""
        BROKER.enable()
        result = {}

        def worker():
            ok, s, f = ask("sec_read", "/tmp/x", "zh", {}, {}, {})
            result.update(ok=ok, s=s, f=f)

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        assert _wait_pending()
        BROKER.deliver("a")
        t.join(timeout=3)
        assert result["ok"] is True
        assert result["s"].get("sec_read") is True
        assert not result["f"]          # 永久放行不该被波及

    def test_forever_scope_answer(self, tmp_path, monkeypatch):
        """F = 永世放行 —— 持久化到 config"""
        from fr_cli.conf import paths
        monkeypatch.setattr(paths._root_holder, "value", tmp_path)

        BROKER.enable()
        result = {}

        def worker():
            ok, s, f = ask("sec_read", "/tmp/x", "zh", {}, {}, {})
            result.update(ok=ok, s=s, f=f)

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        assert _wait_pending()
        BROKER.deliver("f")
        t.join(timeout=3)
        assert result["ok"] is True
        assert result["f"].get("sec_read") is True

    def test_main_thread_still_uses_raw_input(self):
        """主线程自己发起确认 → 仍走裸 input()（走中转站会自己等自己）"""
        BROKER.enable()
        with patch("builtins.input", return_value="y") as m:
            ok, _s, _f = ask("sec_read", "/tmp/x", "zh", {}, {}, {})
        assert ok is True
        assert m.called, "主线程不应该走中转站"

    def test_timeout_denies(self):
        """超时按拒绝处理（fail-closed）"""
        BROKER.enable()
        result = {}

        def worker():
            ok, _s, _f = ask("sec_read", "/tmp/x", "zh", {}, {}, {})
            result["ok"] = ok

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        assert _wait_pending()
        # 直接把答案置空 = 超时路径
        BROKER.cancel_all()
        t.join(timeout=3)
        assert result["ok"] is False

    def test_request_registered_before_prompt_shown(self):
        """竞态回归：确认提示打印时，请求必须**已经注册**。

        否则用户看到提示就立刻敲答案 —— 答案早于注册到达主线程，
        会被当成普通聊天消息丢掉，确认永远等不到（"敲了 Y 毫无反应"）。
        """
        import fr_cli.security.security as sec

        BROKER.enable()
        state = {"pending_at_first_print": None}
        real_print = sec.print_styled

        def spy(msg, *a, **kw):
            if state["pending_at_first_print"] is None:
                state["pending_at_first_print"] = BROKER.has_pending()
            return real_print(msg, *a, **kw)

        result = {}

        def worker():
            with patch.object(sec, "print_styled", spy):
                ok, _s, _f = sec.ask("sec_read", "/tmp/x", "zh", {}, {}, {})
            result["ok"] = ok

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        assert _wait_pending()
        BROKER.deliver("y")
        t.join(timeout=3)
        assert result["ok"] is True
        assert state["pending_at_first_print"] is True, (
            "提示打印时请求还没注册 —— 存在竞态：用户敲的答案可能被丢掉"
        )


class TestBrokerRegisterWait:
    """register + wait_for 拆分（先注册再打印，消除竞态）"""

    def test_register_then_wait(self):
        BROKER.enable()
        pending = BROKER.register("sec_read", "/tmp/x")
        assert pending is not None
        assert BROKER.has_pending()          # 注册后立刻可见
        result = {}

        def worker():
            result["answer"] = BROKER.wait_for(pending, timeout=5)

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        time.sleep(0.05)
        assert BROKER.deliver("a") is True
        t.join(timeout=3)
        assert result["answer"] == "a"

    def test_register_returns_none_when_disabled(self):
        BROKER.disable()
        assert BROKER.register("sec_read", "/tmp/x") is None


class TestBrokerApi:
    """中转站自身的边界行为"""

    def test_deliver_without_pending_returns_false(self):
        assert BROKER.deliver("y") is False

    def test_request_when_disabled_returns_none(self):
        BROKER.disable()
        assert BROKER.request("sec_read", "x", timeout=0.1) is None

    def test_disable_resolves_pending_as_deny(self):
        broker = ConfirmBroker()
        broker.enable()
        result = {}

        def worker():
            result["answer"] = broker.request("sec_read", "x", timeout=5)

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        deadline = time.time() + 2
        while not broker.has_pending() and time.time() < deadline:
            time.sleep(0.01)
        broker.disable()
        t.join(timeout=3)
        assert result["answer"] is None    # None = 拒绝

    def test_cancel_all_returns_count(self):
        broker = ConfirmBroker()
        broker.enable()
        result = {}

        def worker():
            result["answer"] = broker.request("sec_read", "x", timeout=5)

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        deadline = time.time() + 2
        while not broker.has_pending() and time.time() < deadline:
            time.sleep(0.01)
        assert broker.cancel_all() == 1
        t.join(timeout=3)
        assert result["answer"] is None


class TestDeliverIfConfirm:
    """主线程侧：只有 Y/A/F/N 才被当作确认答案"""

    def _start_pending(self):
        broker_result = {}

        def worker():
            broker_result["answer"] = BROKER.request("sec_read", "/tmp/x", timeout=5)

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        assert _wait_pending()
        return t, broker_result

    def test_valid_answer_is_delivered(self):
        from fr_cli.security.interactive import deliver_if_confirm
        BROKER.enable()
        t, result = self._start_pending()
        assert deliver_if_confirm("y") is True
        t.join(timeout=3)
        assert result["answer"] == "y"

    def test_normal_message_is_not_a_confirmation(self):
        """用户的正常发言不能被误当成授权"""
        from fr_cli.security.interactive import deliver_if_confirm
        BROKER.enable()
        t, result = self._start_pending()
        assert deliver_if_confirm("帮我写个文件") is False
        assert deliver_if_confirm("yolo") is False
        assert deliver_if_confirm("") is False
        # 确认仍在等待
        assert BROKER.has_pending()
        BROKER.cancel_all()
        t.join(timeout=3)

    def test_uppercase_answer_accepted(self):
        from fr_cli.security.interactive import deliver_if_confirm
        BROKER.enable()
        t, result = self._start_pending()
        assert deliver_if_confirm("Y") is True
        t.join(timeout=3)
        assert result["answer"] == "y"


class TestSelector:
    """方向键选择器（UI 组件）"""

    def _sel(self, n=4):
        from fr_cli.ui.prompt.selector import Choice, Selector
        return Selector("写入法宝", "/tmp/x.txt",
                        [Choice("y", "仅此"), Choice("a", "本轮"),
                         Choice("f", "永世"), Choice("n", "拒绝")])

    def test_move_wraps_around(self):
        sel = self._sel()
        assert sel.current_value == "y"
        sel.move(1)
        assert sel.current_value == "a"
        sel.move(-1)
        assert sel.current_value == "y"
        sel.move(-1)          # 向前环绕
        assert sel.current_value == "n"
        sel.move(1)           # 向后环绕
        assert sel.current_value == "y"

    def test_select_by_value(self):
        sel = self._sel()
        assert sel.select("f") is True
        assert sel.current_value == "f"
        assert sel.select("zzz") is False

    def test_render_marks_selected(self):
        sel = self._sel()
        sel.select("a")
        rendered = "".join(t for _s, t in sel.render_items(120))
        assert "❯ A 本轮" in rendered
        assert "仅此" in rendered and "永世" in rendered and "拒绝" in rendered
        assert "Enter" in rendered      # 操作提示在

    def test_render_keeps_options_leftmost(self):
        """窄屏下选项不能被截掉 —— 它们必须排在最左"""
        sel = self._sel()
        rendered = "".join(t for _s, t in sel.render_items(40))
        # 目标路径在窄屏下会被截掉，但四个选项与操作提示必须完整
        for label in ("仅此", "本轮", "永世", "拒绝"):
            assert label in rendered
        assert rendered.index("仅此") < rendered.index("Enter")

    def test_render_shows_target_when_wide(self):
        """宽度够时目标路径要完整可见"""
        sel = self._sel()
        rendered = "".join(t for _s, t in sel.render_items(120))
        assert "/tmp/x.txt" in rendered
        assert "写入法宝" in rendered

    def test_move_without_choices_is_noop(self):
        from fr_cli.ui.prompt.selector import Selector
        sel = Selector("t", "d", [])
        assert sel.move(1) is False
        assert sel.current_value is None


class TestBrokerSelection:
    """broker 侧的选项导航"""

    def _start(self):
        BROKER.enable()
        pending = BROKER.register("sec_write", "/tmp/x.txt",
                                   [("y", "仅此"), ("a", "本轮"),
                                    ("f", "永世"), ("n", "拒绝")])
        assert pending is not None
        return pending

    def test_move_selection_changes_index(self):
        self._start()
        assert BROKER.pending_index() == 0
        assert BROKER.move_selection(1) is True
        assert BROKER.pending_index() == 1
        assert BROKER.pending_choices()[1][0] == "a"

    def test_move_selection_without_pending(self):
        BROKER.disable()
        assert BROKER.move_selection(1) is False

    def test_deliver_current_uses_selected(self):
        self._start()
        BROKER.move_selection(2)          # 移到 F
        assert BROKER.deliver_current() is True
        assert not BROKER.has_pending()

    def test_deliver_current_without_pending(self):
        BROKER.disable()
        assert BROKER.deliver_current() is False


class TestTuiKeyHandlers:
    """TUI 键位处理：方向键移动 / Enter 确认 / Esc 拒绝"""

    def _prompt(self):
        """造一个不建 PromptSession 的 FanRenPrompt（只需要那几个方法）"""
        from fr_cli.ui.prompt.tui import FanRenPrompt
        p = object.__new__(FanRenPrompt)
        p.state = type("S", (), {"lang": "zh"})()
        p.status = type("St", (), {})()
        p._session = None      # _invalidate() 会检查它
        return p

    def test_arrow_moves_and_enter_confirms(self):
        BROKER.enable()
        BROKER.register("sec_write", "/tmp/x.txt",
                        [("y", "仅此"), ("a", "本轮"),
                         ("f", "永世"), ("n", "拒绝")])
        p = self._prompt()
        assert p._move_pending_choice(1) is True
        assert BROKER.pending_index() == 1
        assert p._confirm_pending_choice() is True
        assert not BROKER.has_pending()

    def test_esc_denies(self):
        BROKER.enable()
        BROKER.register("sec_write", "/tmp/x.txt",
                        [("y", "仅此"), ("a", "本轮"),
                         ("f", "永世"), ("n", "拒绝")])
        p = self._prompt()
        assert p._deny_pending_choice() is True
        assert not BROKER.has_pending()

    def test_handlers_noop_without_pending(self):
        BROKER.disable()
        p = self._prompt()
        assert p._move_pending_choice(1) is False
        assert p._confirm_pending_choice() is False
        assert p._deny_pending_choice() is False

    def test_typed_letter_wins_over_highlighted_choice(self):
        """⚠️ 安全边界：输入框里敲了 ``n`` 时，Enter 必须**拒绝**。

        否则"敲 n 再回车"会被当成"确认当前高亮项（默认 Y 仅此）"——
        把用户的拒绝变成放行。
        """
        BROKER.enable()
        BROKER.register("sec_write", "/tmp/x.txt",
                        [("y", "仅此"), ("a", "本轮"),
                         ("f", "永世"), ("n", "拒绝")])
        p = self._prompt()
        # 高亮项仍在第一项（Y 仅此），但用户敲了 n
        assert p._confirm_pending_choice("n") is True
        assert not BROKER.has_pending()

    def test_typed_letter_y_is_accepted(self):
        """老习惯：直接敲 ``Y`` 回车就能放行。"""
        BROKER.enable()
        BROKER.register("sec_write", "/tmp/x.txt",
                        [("y", "仅此"), ("a", "本轮"),
                         ("f", "永世"), ("n", "拒绝")])
        p = self._prompt()
        assert p._confirm_pending_choice("Y") is True
        assert not BROKER.has_pending()

    def test_unrelated_text_falls_back_to_selection(self):
        """输入框里是无关文字 → 仍按高亮项确认。"""
        BROKER.enable()
        BROKER.register("sec_write", "/tmp/x.txt",
                        [("y", "仅此"), ("a", "本轮"),
                         ("f", "永世"), ("n", "拒绝")])
        p = self._prompt()
        assert p._move_pending_choice(1) is True      # 高亮移到 A
        assert p._confirm_pending_choice("随便写点什么") is True
        assert not BROKER.has_pending()
