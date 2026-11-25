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


class TestStatusIndicator:
    """状态栏要能看见「待确认」—— 看不见就永远等下去"""

    def test_status_shows_pending_confirm(self):
        from fr_cli.ui.prompt.status import StatusState
        st = StatusState()
        st.confirm_pending = "generate_image"
        rendered = "".join(text for _style, text in st.render(0))
        assert "待确认" in rendered
        assert "generate_image" in rendered
        assert "Y/A/F/N" in rendered

    def test_status_prefers_tool_name(self):
        """工具名比路径好读 —— 优先显示工具名"""
        from fr_cli.ui.prompt.status import StatusState
        st = StatusState()
        st.tool_name = "write_file"
        st.confirm_pending = "/Users/someone/very/long/path/to/file.txt"
        rendered = "".join(text for _style, text in st.render(0))
        assert "待确认 write_file" in rendered
        assert "/Users/someone" not in rendered

    def test_status_keeps_confirm_visible_with_tool_item(self):
        """工具状态与待确认同时存在时 —— 待确认排在右栏首位（不会被宽度裁掉）"""
        from fr_cli.ui.prompt.status import StatusState
        st = StatusState()
        st.model = "step-5-preview"
        st.provider = "stepfun"
        st.tool_name = "write_file"
        st.tool_source = "master"
        st.confirm_pending = "/tmp/x.txt"
        rendered = "".join(text for _style, text in st.render(120))
        assert "待确认" in rendered
        assert rendered.index("待确认") < rendered.index("[master] write_file")

    def test_status_clean_when_no_pending(self):
        from fr_cli.ui.prompt.status import StatusState
        st = StatusState()
        rendered = "".join(text for _style, text in st.render(0))
        assert "待确认" not in rendered
