"""
交互式确认的中转站 —— 主线程读输入，后台线程等答案

v2.8.7 新增（修 REPL 假死）。

问题背景
--------
REPL 主循环用 prompt_toolkit 占着 stdin（raw 模式），而工具执行跑在**后台线程**
（``repl/queue.py`` 的 worker）。工具需要安全确认时，原实现直接 ``input()``：

    后台线程   input()               ←── 抢同一个 fd
    主线程     PromptSession.prompt() ←── 一直在 read()

两个读者抢同一个 stdin：prompt_toolkit 的读取器先拿到按键，用户敲的
Y / A / F / N 全被吞进输入框，``input()`` 永远等不到 —— 终端看起来
**完全没反应**（每按一次回车只是把一条空消息塞进对话队列）。

修法
----
把"读输入"这件事交回给**拥有 stdin 的主线程**：

- 后台线程：``BROKER.request(key, desc)`` 阻塞等答案
- 主线程：拿到用户输入后 ``BROKER.deliver(answer)`` 把答案送回去

安全边界
--------
* 只有**非主线程**发起的请求才走中转站 —— 主线程自己发起的确认（例如斜杠
  命令里触发的高危操作）此刻并没有 prompt_toolkit 在读 stdin，裸 ``input()``
  才是对的，走中转站反而会自己等自己。
* 中转站禁用时（非 TTY / 批处理 / HTTP 服务 / bot）保持原来的裸 ``input()``
  行为，**零行为变化**。
* 等待超时（默认 300s）或被取消一律按**拒绝**处理（fail-closed）。
"""
from __future__ import annotations

import threading

__all__ = [
    "PendingConfirm",
    "ConfirmBroker",
    "BROKER",
    "DEFAULT_TIMEOUT",
    "VALID_ANSWERS",
    "deliver_if_confirm",
]

#: 等待确认答案的默认超时（秒）。超时按**拒绝**处理（fail-closed）。
DEFAULT_TIMEOUT = 300.0

#: 合法的确认答案（小写）。主线程只把这些值当作"确认回答"，
#: 其余输入一律当普通对话消息处理 —— 免得把用户的正常发言误当成授权。
VALID_ANSWERS = ("y", "yes", "a", "f", "n", "no")


class PendingConfirm:
    """一次待确认的请求（后台线程等待，主线程投递答案）。"""

    __slots__ = ("key", "desc", "answer", "_event")

    def __init__(self, key: str, desc: str):
        self.key = key
        self.desc = desc
        #: 答案（'y'/'a'/'f'/'n'）；超时或取消时为 None（按拒绝处理）
        self.answer = None
        self._event = threading.Event()

    def resolve(self, answer) -> None:
        """给出答案并唤醒等待方。"""
        self.answer = answer
        self._event.set()

    def wait(self, timeout: float = None) -> bool:
        """等待答案。返回 False 表示超时。"""
        return self._event.wait(timeout)

    @property
    def resolved(self) -> bool:
        return self._event.is_set()


class ConfirmBroker:
    """确认请求中转站（进程内单例 :data:`BROKER`）。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._pending: PendingConfirm = None
        self._enabled = False

    # ---------- 开关 ----------

    def enable(self) -> None:
        """开启中转（REPL 有 prompt_toolkit 输入框时调用）。"""
        with self._lock:
            self._enabled = True

    def disable(self) -> None:
        """关闭中转 —— 正在等待的请求按拒绝处理（不丢请求）。"""
        with self._lock:
            self._enabled = False
            pending = self._pending
            self._pending = None
        if pending is not None:
            pending.resolve(None)

    @property
    def enabled(self) -> bool:
        with self._lock:
            return self._enabled

    # ---------- 待确认状态 ----------

    def has_pending(self) -> bool:
        """当前是否有待确认的请求（主线程据此决定输入的含义）。"""
        with self._lock:
            return self._pending is not None

    def pending_desc(self) -> str:
        """待确认请求的描述（状态栏展示用）。"""
        with self._lock:
            return self._pending.desc if self._pending else ""

    def pending_key(self) -> str:
        """待确认请求的安全类别（sec_*）。"""
        with self._lock:
            return self._pending.key if self._pending else ""

    # ---------- 请求 / 投递 ----------

    def register(self, key: str, desc: str):
        """挂上一个待确认请求（**不等待**）。

        为什么要把"注册"和"等待"拆开：

        用户看到确认提示就可能**立刻**敲答案。若"先打印提示、后注册请求"，
        主线程读到的答案会早于请求注册 —— 答案被当成普通聊天消息丢掉，
        确认永远等不到（终端表现为"敲了 Y 毫无反应"，比假死更难查）。
        先注册再打印，用户看到提示时请求必然已就绪。

        Returns:
            PendingConfirm | None: None 表示中转站未启用（调用方应回落裸 input()）
        """
        pending = PendingConfirm(key, desc)
        with self._lock:
            if not self._enabled:
                return None
            self._pending = pending
        return pending

    def wait_for(self, pending, timeout: float = DEFAULT_TIMEOUT):
        """等待**已注册**的请求返回答案。

        Returns:
            str | None: 答案；超时 / 被取消返回 None（调用方按拒绝处理）
        """
        if pending is None:
            return None
        try:
            if not pending.wait(timeout):
                return None
            return pending.answer
        finally:
            with self._lock:
                if self._pending is pending:
                    self._pending = None

    def request(self, key: str, desc: str, timeout: float = DEFAULT_TIMEOUT):
        """注册并阻塞等待答案（register + wait_for 的组合）。

        Returns:
            str | None: 答案（'y'/'a'/'f'/'n'）；超时或被取消返回 None
                         —— 调用方必须按**拒绝**处理。
        """
        pending = self.register(key, desc)
        if pending is None:
            # 中转站没开 —— 调用方应回退到裸 input()
            return None
        return self.wait_for(pending, timeout)

    def deliver(self, answer: str) -> bool:
        """主线程把用户的输入送给等待中的请求。

        Returns:
            bool: 是否成功投递（没有待确认请求 / 已超时 → False）
        """
        with self._lock:
            pending = self._pending
            if pending is None:
                return False
            self._pending = None
        pending.resolve(answer)
        return True

    def cancel_all(self) -> int:
        """取消所有待确认请求（按拒绝处理）—— 退出 / 中断时调用。

        Returns:
            int: 取消掉的请求数
        """
        with self._lock:
            pending = self._pending
            self._pending = None
        if pending is None:
            return 0
        pending.resolve(None)
        return 1


#: 进程级单例
BROKER = ConfirmBroker()


def deliver_if_confirm(text: str) -> bool:
    """主线程用：把用户输入当作**确认答案**投递。

    只有 ``VALID_ANSWERS`` 里的值才被当作确认 —— 其余输入（哪怕只差一个字符）
    一律当普通对话消息处理，免得把用户的正常发言误当成授权。

    Args:
        text: 用户在输入框里敲的内容

    Returns:
        bool: 是否已作为确认答案投递（False = 不是确认答案 / 当前没有待确认）
    """
    ans = (text or "").strip().lower()
    if ans not in VALID_ANSWERS:
        return False
    return BROKER.deliver(ans)
