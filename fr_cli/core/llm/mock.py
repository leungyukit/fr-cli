"""Mock LLM 客户端 —— 零配置试用 / API 不可用时的降级方案 + 脚本化测试替身

三层能力
--------
1. :class:`MockLLMClient` —— 回声式 mock（v2.8.6 起的既有行为，**行为完全不变**）
2. :class:`ScriptedMockClient` —— 脚本化 mock：按调用序列 / 按输入内容匹配返回预置响应
3. :class:`RecordingClient` —— 录制包装器：包住任意 client，把交互录成 fixture

关于 1 与 2 的关系
------------------
:class:`ScriptedMockClient` 直接继承 :class:`BaseLLMClient`，**不是**
:class:`MockLLMClient` 的子类 —— 它是"测试替身"，不是"降级回声"：

* ``core/stream.py`` 用 ``isinstance(client, MockLLMClient)`` 判断是不是降级模式，
  脚本化客户端**不**满足这个判断（它不会走缺 key 提示那条分支）；
* 需要"看起来就是 mock"时用 ``MockLLMClient(script=[...])`` ——
  传了脚本参数就切脚本化，不传就是老行为。

为什么需要 2 / 3
----------------
回声式 mock 只能"按输入返回固定内容"，无法编排多步 agent 流程
（第 1 轮调工具 → 第 2 轮根据工具结果再调 → 第 3 轮给结论）。
脚本化 mock 让 eval 层可以**离线、可重复、零网络**地跑完整 agent 循环，
并把一次真实交互录成 fixture 后反复回放。

约束
----
* 零网络、零 API Key、零新依赖（只用标准库）
* ``MockLLMClient`` 的公开行为保持不变 —— 既有测试一个都不能坏
* ``MockClient`` 是 ``MockLLMClient`` 的别名（历史上有人这么叫它）
"""
from __future__ import annotations

import json
import re
import time as _time
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple, Union

from fr_cli.core.llm.base import BaseLLMClient

#: fixture 文件版本号（结构不兼容变更时 +1）
FIXTURE_VERSION = 1

#: fixture 文件类型标记（回放时用来校验文件确实是本模块产出的）
FIXTURE_KIND = "fr_cli.llm.fixture"

#: 脚本化客户端在脚本与规则都没命中时的兜底响应
DEFAULT_SCRIPTED_RESPONSE = "【Mock 脚本】没有匹配的脚本响应。"

#: 规则匹配器允许的类型：字符串（子串）/ 编译后的正则 / 可调用对象
Matcher = Union[str, "re.Pattern[str]", Callable[[List[Dict[str, Any]]], bool]]


# ------------------------------------------------------------------
# fixture 读写（录制 / 回放共用同一份格式）
# ------------------------------------------------------------------
def save_fixture(path, calls: Sequence[Dict[str, Any]], name: str = "session") -> Path:
    """把录制到的调用写成 fixture 文件。

    Args:
        path: 目标文件路径（父目录不存在会自动创建）
        calls: 调用记录列表，每项形如
               ``{"model": str, "messages": list, "response": str}``
        name: 会话名（仅作备注）

    Returns:
        写入后的文件路径（Path）
    """
    payload = {
        "version": FIXTURE_VERSION,
        "kind": FIXTURE_KIND,
        "name": name,
        "calls": [dict(c) for c in calls],
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return target


def load_fixture(path) -> Dict[str, Any]:
    """读取 fixture 文件并做基本校验。

    Raises:
        ValueError: 文件不是合法的 fixture（缺 kind / calls）
    """
    raw = Path(path).read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"fixture 格式错误（应为对象）: {path}")
    if data.get("kind") != FIXTURE_KIND:
        raise ValueError(f"不是 LLM fixture（kind={data.get('kind')!r}）: {path}")
    if not isinstance(data.get("calls"), list):
        raise ValueError(f"fixture 缺少 calls 列表: {path}")
    return data


def _first_user_content(messages: Sequence[Dict[str, Any]]) -> str:
    """取第一条 user 消息的正文（agent 流程里最稳定的"任务输入"）。"""
    for m in messages:
        if m.get("role") == "user":
            return str(m.get("content", ""))
    return ""


def _last_user_content(messages: Sequence[Dict[str, Any]]) -> str:
    """取最后一条 user 消息的正文。"""
    for m in reversed(list(messages)):
        if m.get("role") == "user":
            return str(m.get("content", ""))
    return ""


def _all_user_content(messages: Sequence[Dict[str, Any]]) -> str:
    """把所有 user 消息正文拼起来（多轮 agent 流程的兜底匹配目标）。"""
    return "\n".join(
        str(m.get("content", "")) for m in messages if m.get("role") == "user"
    )


def _match_targets(messages: Sequence[Dict[str, Any]]) -> List[str]:
    """规则匹配的候选文本（按优先级）。

    依次尝试：最后一条 user → 第一条 user → 全部 user 拼接。
    这样"同一段输入反复问"（命中第一条）与"多步流程追问"（命中最后一条）
    都能用同一个规则表覆盖。
    """
    targets = [
        _last_user_content(messages),
        _first_user_content(messages),
        _all_user_content(messages),
    ]
    # 去重且保持顺序
    seen = set()
    unique = []
    for t in targets:
        if t and t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


class ScriptedMockClient(BaseLLMClient):
    """脚本化 Mock LLM —— 按调用序列 / 按输入内容匹配返回预置响应。

    两种模式（可共存，**规则优先于序列**）：

    * **序列模式** ``script=["A", "B"]``
      第 n 次调用返回 ``script[n-1]``（``call_index`` 从 0 开始计数，
      每次 ``stream_chat`` 都 +1，与是否命中规则无关）。
    * **匹配模式** ``rules=[("关键词", "响应")]``
      按输入内容匹配：字符串 → 子串匹配；``re.Pattern`` → ``search``；
      可调用对象 → 传入整份 messages，返回真值即命中。
      多个规则按声明顺序，**首个命中者生效**。

    两者都没命中时返回 ``default_response``。

    每次调用都会被记录到 :attr:`calls`，可用 :meth:`save_fixture` 落盘成
    fixture 供后续回放。

    Args:
        script: 预置响应序列
        rules: 匹配规则列表，元素为 ``(pattern, response)`` 或
               ``{"pattern": ..., "response": ...}``
        default_response: 兜底响应（默认 :data:`DEFAULT_SCRIPTED_RESPONSE`）
        api_key: 兼容基类签名（mock 不校验）。默认给一个**够长**的占位串 ——
            ``core/stream.py`` 会用 ``len(api_key) < 10`` 判断"是不是没配 key"，
            短占位符会触发多余的缺 key 提示。
        model: 模型名（仅作展示）
        usage: 固定 usage 载荷（不传则按字符数估算）
    """

    #: Mock 不模拟原生工具调用
    SUPPORTS_TOOLS = False

    def __init__(
        self,
        script: Optional[Sequence[str]] = None,
        rules: Optional[Sequence[Any]] = None,
        default_response: Optional[str] = None,
        api_key: str = "mock-script-key",
        model: str = "mock-script",
        usage: Optional[Dict[str, int]] = None,
        **kwargs,
    ):
        super().__init__(api_key, **kwargs)
        self.model = model
        self.is_mock = True
        self.script: List[str] = [str(s) for s in (script or [])]
        self.rules: List[Tuple[Matcher, str]] = []
        self.default_response = (
            default_response if default_response is not None else DEFAULT_SCRIPTED_RESPONSE
        )
        self.usage = usage
        #: 已发生的调用序号（0 起）—— 序列模式按它取 script
        self.call_index = 0
        #: 调用记录（供 save_fixture 使用）
        self.calls: List[Dict[str, Any]] = []
        for rule in rules or []:
            self._add_rule(rule)

    # ---------------- 规则 / 脚本维护 ----------------
    def _add_rule(self, rule: Any) -> "ScriptedMockClient":
        """追加一条匹配规则。

        接受 ``(pattern, response)`` 元组或 ``{"pattern":..., "response":...}``。
        """
        if isinstance(rule, dict):
            pattern = rule.get("pattern")
            response = rule.get("response", "")
        else:
            pattern, response = rule[0], rule[1]
        self.rules.append((pattern, str(response)))
        return self

    def on(self, pattern: Matcher, response: str) -> "ScriptedMockClient":
        """追加一条匹配规则（链式调用）。"""
        return self._add_rule((pattern, response))

    def push(self, response: str) -> "ScriptedMockClient":
        """向序列末尾追加一个响应（链式调用）。"""
        self.script.append(str(response))
        return self

    def reset(self) -> None:
        """重置调用序号与调用记录（脚本 / 规则保留）。"""
        self.call_index = 0
        self.calls = []

    # ---------------- 响应解析 ----------------
    def _match_rule(self, messages: Sequence[Dict[str, Any]]) -> Optional[str]:
        """按输入内容匹配规则，返回命中的响应；未命中返回 None。"""
        if not self.rules:
            return None
        targets = _match_targets(messages)
        for pattern, response in self.rules:
            if callable(pattern) and not isinstance(pattern, (str, re.Pattern)):
                try:
                    if pattern(list(messages)):
                        return response
                except Exception:
                    continue
            elif isinstance(pattern, re.Pattern):
                if any(pattern.search(t) for t in targets):
                    return response
            elif isinstance(pattern, str):
                if pattern and any(pattern in t for t in targets):
                    return response
        return None

    def _resolve(self, messages: Sequence[Dict[str, Any]]) -> str:
        """决定本次调用返回什么（规则 → 序列 → 兜底）。"""
        matched = self._match_rule(messages)
        if matched is not None:
            return matched
        index = self.call_index
        if 0 <= index < len(self.script):
            return self.script[index]
        return self.default_response

    def _usage_payload(
        self, messages: Sequence[Dict[str, Any]], response: str
    ) -> Dict[str, int]:
        """生成 usage 载荷（固定值优先，否则按字符数估算）。"""
        if self.usage:
            return dict(self.usage)
        prompt_chars = sum(len(str(m.get("content", ""))) for m in messages)
        return {
            "prompt_tokens": prompt_chars // 4,
            "completion_tokens": len(response) // 4,
            "total_tokens": (prompt_chars + len(response)) // 4,
        }

    # ---------------- LLM 接口 ----------------
    def stream_chat(
        self,
        model: str,
        messages: list,
        max_tokens: int = 4096,
        timeout: int = None,
        tools: Optional[list] = None,
        tool_choice: Optional[str] = None,
    ) -> Iterator[dict]:
        """返回预置响应（零网络）。"""
        # 先按当前序号取响应，再推进序号 —— 顺序反了会导致永远取到第 2 项
        response = self._resolve(messages)
        self.call_index += 1
        self.calls.append(
            {
                "model": model,
                "messages": [dict(m) for m in messages],
                "response": response,
            }
        )
        yield {"content": response, "usage": None}
        yield {"content": "", "usage": self._usage_payload(messages, response)}

    # ---------------- 录制 / 回放 ----------------
    def save_fixture(self, path, name: str = "scripted-session") -> Path:
        """把已发生的调用写成 fixture 文件。"""
        return save_fixture(path, self.calls, name=name)

    @classmethod
    def load_fixture(
        cls,
        path,
        mode: str = "sequence",
        **kwargs,
    ) -> "ScriptedMockClient":
        """从 fixture 文件构造回放客户端（零网络）。

        Args:
            path: fixture 文件路径
            mode: ``"sequence"`` 按录制顺序回放（默认）；
                  ``"match"`` 按录制时的首条 user 消息内容匹配
        """
        data = load_fixture(path)
        calls = data.get("calls") or []
        client = cls(**kwargs)
        if mode == "match":
            for call in calls:
                text = _first_user_content(call.get("messages") or [])
                if text:
                    client.on(text, str(call.get("response", "")))
        else:
            client.script = [str(c.get("response", "")) for c in calls]
        return client

    @property
    def last_response(self) -> str:
        """最近一次返回的响应文本（无记录时为空串）。"""
        return self.calls[-1]["response"] if self.calls else ""


class RecordingClient(BaseLLMClient):
    """录制包装器 —— 包住任意 client，把每次交互录下来，可落盘成 fixture。

    用于"把一次真实交互录成 fixture，回放时零网络"：

    .. code-block:: python

        recorder = RecordingClient(real_client, name="demo")
        ...  # 跑一次真实对话
        recorder.save_fixture("tests/evals/fixtures/demo.json")

        # 之后离线回放
        player = ScriptedMockClient.load_fixture("tests/evals/fixtures/demo.json")
    """

    def __init__(self, inner, name: str = "session", **kwargs):
        api_key = kwargs.pop("api_key", None) or getattr(inner, "api_key", "") or "mock"
        super().__init__(api_key, **kwargs)
        self.inner = inner
        self.name = name
        self.model = getattr(inner, "model", "recorded")
        self.is_mock = False
        # 是否支持原生 function calling 跟随内层 client
        self.SUPPORTS_TOOLS = bool(getattr(inner, "SUPPORTS_TOOLS", False))
        #: 录制到的调用
        self.calls: List[Dict[str, Any]] = []

    def stream_chat(
        self,
        model: str,
        messages: list,
        max_tokens: int = 4096,
        timeout: int = None,
        tools: Optional[list] = None,
        tool_choice: Optional[str] = None,
    ) -> Iterator[dict]:
        """透传给内层 client，同时把本轮交互录下来。"""
        chunks: List[str] = []
        try:
            stream = self.inner.stream_chat(
                model,
                messages,
                max_tokens=max_tokens,
                timeout=timeout,
                tools=tools,
                tool_choice=tool_choice,
            )
        except TypeError:
            # 兼容旧签名（不接受 tools / tool_choice）
            stream = self.inner.stream_chat(model, messages, max_tokens=max_tokens)
        for chunk in stream:
            content = chunk.get("content") if isinstance(chunk, dict) else None
            if content:
                chunks.append(content)
            yield chunk
        self.calls.append(
            {
                "model": model,
                "messages": [dict(m) for m in messages],
                "response": "".join(chunks),
            }
        )

    def save_fixture(self, path) -> Path:
        """把录制到的调用写成 fixture 文件。"""
        return save_fixture(path, self.calls, name=self.name)


class MockLLMClient(BaseLLMClient):
    """Mock LLM:不调任何远程 API,本地回声式响应

    适用场景:
    1. 用户首次启动还没配 API Key(init_config 检测到无 key 时切换)
    2. 远程 API 调用失败(网络/限流/key 错)的临时降级
    3. 演示 / 测试场景

    v2.8.7(P2-1) 行为变更：**默认行为完全不变**（仍是回声式）；
    额外支持可选的脚本化参数 ``script`` / ``rules`` / ``default_response`` ——
    传入任意一个即切换为脚本化模式（等价于 :class:`ScriptedMockClient`）。
    """

    #: Mock 不模拟原生工具调用
    SUPPORTS_TOOLS = False

    def __init__(self, api_key: str = "mock", **kwargs):
        # 脚本化参数（可选，默认 None → 保持回声式行为）
        script = kwargs.pop("script", None)
        rules = kwargs.pop("rules", None)
        default_response = kwargs.pop("default_response", None)
        model = kwargs.pop("model", "mock-echo")
        super().__init__(api_key, **kwargs)
        self.model = model
        self.is_mock = True
        self._scripted: Optional[ScriptedMockClient] = None
        if script is not None or rules is not None or default_response is not None:
            self._scripted = ScriptedMockClient(
                script=script,
                rules=rules,
                default_response=default_response,
                api_key=api_key,
                model=model,
            )

    def stream_chat(self, model: str, messages: list,
                    max_tokens: int = 4096, timeout: int = None,
                    tools: Optional[list] = None,
                    tool_choice: Optional[str] = None) -> Iterator[dict]:
        """回声响应:把最后一条 user message 包装一下吐出来"""
        # 传入脚本化参数时走脚本化分支
        # 注意:本方法是生成器函数,必须 yield from —— 直接 return 生成器对象
        # 会让调用方拿到 0 个 chunk。
        if self._scripted is not None:
            yield from self._scripted.stream_chat(
                model, messages, max_tokens=max_tokens, timeout=timeout,
                tools=tools, tool_choice=tool_choice,
            )
            return

        # 提取最后一条 user 消息
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = m.get("content", "")
                break

        # 简单响应模板
        if not last_user:
            response = ("【Mock 模式】我是本地 mock 客户端,没收到你的输入。"
                        "配置 API Key 后可启用真实 LLM(/key <your-key>)。")
        elif last_user.startswith("/"):
            response = (f"【Mock 模式】你输入了命令 {last_user[:60]}。"
                        "当前在 mock 模式,命令执行仍可工作(不依赖 LLM),"
                        "只是 AI 回答部分是模拟的。")
        else:
            short = last_user[:200]
            response = (
                f"【Mock 模式】当前未配置 API Key 或 LLM 不可用。\n"
                f"你刚才说的是:{short}\n\n"
                f"**配置真实 LLM 的方式:**\n"
                f"- `/key sk-xxx` 设置当前提供商的 key\n"
                f"- `/providers use <厂商>` 切换到其他提供商\n"
                f"- `/providers setup` 交互式配置\n\n"
                f"**Mock 模式仍能用的功能:**\n"
                f"- `/help` / `/cat` / `/ls` / `/web` 等命令\n"
                f"- `/shell` 执行系统命令\n"
                f"- `@local` / `@RAG` 等不依赖 LLM 的 Agent\n"
            )

        # 模拟流式输出:按词切分
        for word in response.split(" "):
            yield {"content": word + " ", "usage": None}
            _time.sleep(0.02)  # 让用户看到流式效果

        # 最后给个 usage
        yield {
            "content": "",
            "usage": {
                "prompt_tokens": sum(len(m.get("content", "")) for m in messages) // 4,
                "completion_tokens": len(response) // 4,
                "total_tokens": (sum(len(m.get("content", "")) for m in messages) + len(response)) // 4,
            },
        }


#: 历史别名 —— 有人习惯直接叫它 MockClient
MockClient = MockLLMClient

__all__ = [
    "MockLLMClient",
    "MockClient",
    "ScriptedMockClient",
    "RecordingClient",
    "save_fixture",
    "load_fixture",
    "FIXTURE_VERSION",
    "FIXTURE_KIND",
    "DEFAULT_SCRIPTED_RESPONSE",
]
