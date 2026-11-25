"""评测 harness —— 离线、可重复、零网络的 agent 任务评测层。

这个层测的是什么（先说清楚，避免自欺欺人）
------------------------------------------------
**它测"解析与调度"层，不测"模型真实能力"层。**

每个评测任务自带一份"模型输出脚本"（script），harness 把脚本喂给
:class:`fr_cli.core.llm.mock.ScriptedMockClient`，然后驱动一条**真实的**
fr-cli 工具调用链路：

    模型文本 → 标记解析(executor._extract_tool_calls)
             → 参数解析(executor._parse_tool_kwargs)
             → 工具调度(executor.invoke_tool → registry.dispatch)
             → 安全确认(state.security.check → ConfirmStrategy)
             → 工具 handler(VFS / 桩件)

因此这套 eval 能回答：

* 工具被改名 / 下线了，链路还能不能把它调起来？（工具选择正确率）
* 工具参数 schema 改了，参数还能不能对上？（参数正确率）
* 多步流程还能不能在 max_steps 内收敛？（多步完成率）
* **该被安全确认拦住的调用，是不是真的走了 state.security 并被拦下？**（越权拦截率）

它**测不出**：

* 真实模型会不会选对工具（那需要联网 + API Key，属于 live eval）
* 真实模型的回答质量

所以这套 eval 的定位是**回归护栏**：改了 prompt 模板、工具描述、注册表、
参数 schema 或安全策略之后，跑一遍就知道有没有把链路改坏。

零网络保证
----------
* web / mail / disk 全部换成桩件（:class:`FakeWebClient` 等），永不发起真实连接
* LLM 用脚本化 mock，不调任何远程 API
* pytest 里有一条用例直接把 socket 封死再跑一遍全量 eval 来验证这一点
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from fr_cli.core.result import Result
from fr_cli.core.llm.mock import ScriptedMockClient
from fr_cli.security.strategy import ConfirmDecision, ConfirmStrategy

#: 数据集目录（相对本文件）
DATASET_DIR = Path(__file__).resolve().parent / "datasets"

#: fixture 目录（相对本文件）
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


# ==================================================================
# 任务模型
# ==================================================================
@dataclass
class EvalTask:
    """一个最小 agent 任务。

    Attributes:
        id: 任务唯一标识
        user_input: 喂给 agent 的用户输入
        expect_tool: 期望被选中的工具名
        expect_params: 期望的参数（只校验列出的 key，多余参数不扣分）
        expect_tools: 多步任务期望的工具序列（按顺序）
        max_steps: 最大步数
        script: 模型输出脚本（逐轮返回的文本）
        expect_security: 期望触发的安全类别（sec_*）
        expect_blocked: 期望是否被安全确认拦下（True/False/None=不关心）
        setup: 运行前的工作目录准备（文件 / 子目录）
        tags: 标签
        notes: 备注
        known_issue: 已知缺陷说明（该任务当前预期会失败，用于把"已知问题"
            与"新回归"区分开）
    """

    id: str
    user_input: str
    expect_tool: str
    expect_params: Dict[str, Any] = field(default_factory=dict)
    expect_tools: List[str] = field(default_factory=list)
    max_steps: int = 3
    script: List[str] = field(default_factory=list)
    expect_security: Optional[str] = None
    expect_blocked: Optional[bool] = None
    setup: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    notes: str = ""
    known_issue: str = ""

    @property
    def is_multi_step(self) -> bool:
        """是否属于多步任务（期望工具序列长度 > 1）。"""
        return len(self.expect_tools) > 1

    @property
    def expected_sequence(self) -> List[str]:
        """期望的工具序列（多步任务用 expect_tools，单步用 expect_tool）。"""
        if self.expect_tools:
            return list(self.expect_tools)
        return [self.expect_tool] if self.expect_tool else []

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvalTask":
        """从 JSON dict 构造任务（缺字段会给出明确报错）。"""
        missing = [k for k in ("id", "user_input", "expect_tool") if not data.get(k)]
        if missing:
            raise ValueError(f"任务缺少必填字段 {missing}: {data!r}")
        return cls(
            id=str(data["id"]),
            user_input=str(data["user_input"]),
            expect_tool=str(data["expect_tool"]),
            expect_params=dict(data.get("expect_params") or {}),
            expect_tools=list(data.get("expect_tools") or []),
            max_steps=int(data.get("max_steps", 3)),
            script=[str(s) for s in (data.get("script") or [])],
            expect_security=data.get("expect_security"),
            expect_blocked=data.get("expect_blocked"),
            setup=dict(data.get("setup") or {}),
            tags=list(data.get("tags") or []),
            notes=str(data.get("notes") or ""),
            known_issue=str(data.get("known_issue") or ""),
        )


def load_tasks(dataset_dir=None) -> List[EvalTask]:
    """加载数据集目录下的全部任务（按文件名排序，保证顺序稳定）。

    Args:
        dataset_dir: 数据集目录，默认 :data:`DATASET_DIR`

    Returns:
        List[EvalTask]: 任务列表
    """
    directory = Path(dataset_dir) if dataset_dir else DATASET_DIR
    if not directory.is_dir():
        return []
    tasks: List[EvalTask] = []
    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload if isinstance(payload, list) else payload.get("tasks", [])
        for item in items:
            tasks.append(EvalTask.from_dict(item))
    return tasks


# ==================================================================
# 离线桩件（永不发起真实网络 / 真实邮件）
# ==================================================================
class FakeWebClient:
    """web 桩件 —— 返回固定的离线搜索结果。"""

    def search(self, query: str, lang: str = "zh") -> Result:
        """返回一条固定的离线搜索结果。"""
        return Result.ok(
            [
                {
                    "title": f"{query} - 离线评测结果",
                    "url": "https://example.invalid/offline",
                    "snippet": "离线评测桩数据，未发起任何真实网络请求。",
                }
            ]
        )

    def fetch(self, url: str, lang: str = "zh") -> Result:
        """返回一段固定的离线正文。"""
        return Result.ok(f"[离线桩] {url}")


class FakeMailClient:
    """邮件桩件 —— 只记录，不发送。

    注意：``email`` / ``password`` / ``imap_server`` 三个属性必须存在 ——
    ``registered/mail.py::_ensure_mail`` 看到它们齐全才会跳过**交互式邮件向导**
    （向导里有 ``input()``，非交互环境下必然 EOFError）。
    """

    def __init__(self):
        self.sent: List[Dict[str, Any]] = []
        # 假装"已配置" —— 让 _ensure_mail 直接放行，不进向导
        self.email = "offline@example.invalid"
        self.password = "offline-stub"
        self.imap_server = "imap.example.invalid"
        self.smtp_server = "smtp.example.invalid"

    def send(self, to: str, subject: str, body: str, lang: str = "zh") -> Result:
        """记录一次"发送"并返回成功。"""
        self.sent.append({"to": to, "subject": subject, "body": body})
        return Result.ok("sent (offline stub)")

    def inbox(self, lang: str = "zh") -> Result:
        """返回空收件箱。"""
        return Result.ok([])

    def read(self, mid: str, lang: str = "zh") -> Result:
        """返回一封固定的离线邮件。"""
        return Result.ok(
            {
                "id": mid,
                "sub": "离线邮件",
                "from": "offline@example.invalid",
                "date": "1970-01-01",
                "body": "离线桩数据。",
            }
        )


class FakeDiskClient:
    """网盘桩件 —— 返回空的目录列表。"""

    def ls(self, lang: str = "zh") -> Result:
        """返回空列表。"""
        return Result.ok([])


# ==================================================================
# 安全确认策略（评测用）
# ==================================================================
class RecordingStrategy(ConfirmStrategy):
    """记录 + 决策的确认策略。

    它是 :mod:`fr_cli.security.strategy` 的真实子类，因此走的是
    ``state.security.check() → strategy.check()`` 这条**生产确认链路**，
    只是在最末端把"问用户"换成了"按预设决策"。

    Attributes:
        decision: ``"deny"``（默认，fail-closed）或 ``"allow"``
        requests: 每次被询问的记录（key / target / tool_name / args）
    """

    name = "eval-recording"

    def __init__(self, decision: str = "deny", config=None, lang: str = "zh"):
        super().__init__(lang=lang, config=config)
        self.decision = decision
        self.requests: List[Dict[str, Any]] = []

    def check(self, key: str, target: str, tool_name: str = "",
              args: Optional[Dict[str, Any]] = None) -> ConfirmDecision:
        """记录这次确认请求，然后按预设放行 / 拒绝。"""
        self.requests.append(
            {
                "key": key,
                "target": target,
                "tool_name": tool_name,
                "args": dict(args or {}),
            }
        )
        if self.decision == "allow":
            return ConfirmDecision.allow("once")
        return ConfirmDecision.deny("评测环境默认拒绝（fail-closed）")


# ==================================================================
# 状态装配
# ==================================================================
def default_cfg() -> Dict[str, Any]:
    """评测用的干净配置（无 API Key / 无 provider）。"""
    return {
        "version": 3,
        "lang": "zh",
        "limit": 4096,
        "allowed_dirs": [],
        "aliases": {},
        "auto_confirm": {},
        "autonomous_mode": "manual",
        "thinking_mode": "direct",
        "providers": {},
        "mail": {},
        "disk": {},
        "mcp": {"servers": []},
    }


@contextlib.contextmanager
def manual_mode() -> Iterator[None]:
    """强制 ``FR_CLI_AUTONOMOUS_MODE=manual``。

    自治模式一旦是 ``full_auto`` / ``sandbox_auto``，安全确认会被自动放行，
    越权拦截率就失去意义 —— 评测期间必须钉死成 manual，退出时恢复原值。
    """
    old = os.environ.get("FR_CLI_AUTONOMOUS_MODE")
    os.environ["FR_CLI_AUTONOMOUS_MODE"] = "manual"
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("FR_CLI_AUTONOMOUS_MODE", None)
        else:
            os.environ["FR_CLI_AUTONOMOUS_MODE"] = old


def build_state(
    cfg: Dict[str, Any],
    workdir: Path,
    client,
    strategy: Optional[ConfirmStrategy] = None,
    model_name: str = "mock-script",
):
    """装配一个**轻量** AppState 替身。

    刻意不用完整的 :class:`fr_cli.core.core.AppState` —— 那会连带初始化
    MasterAgent / Hermes / Gatekeeper / MCP 发现线程等一堆与评测无关的
    东西（还可能碰网络）。这里只保留工具链路真正依赖的依赖项，
    但 ``vfs`` / ``security`` / ``executor`` 都是**生产实现**。

    Args:
        cfg: 配置字典
        workdir: 沙盒工作目录（VFS 的唯一允许根）
        client: LLM 客户端
        strategy: 安全确认策略（默认 fail-closed 拒绝）
        model_name: 模型名

    Returns:
        SimpleNamespace: 具备 ``executor`` 的状态对象
    """
    from fr_cli.command.executor import CommandExecutor
    from fr_cli.command.security import SecurityManager
    from fr_cli.weapon.fs import VFS

    security = SecurityManager(cfg.get("lang", "zh"), cfg)
    if strategy is not None:
        security.set_strategy(strategy)

    state = SimpleNamespace(
        vfs=VFS([str(workdir)]),
        mail_c=FakeMailClient(),
        web_c=FakeWebClient(),
        disk_c=FakeDiskClient(),
        plugins={},
        lang=cfg.get("lang", "zh"),
        security=security,
        cfg=cfg,
        client=client,
        model_name=model_name,
        mcp=None,
    )
    state.executor = CommandExecutor(state)
    return state


def build_system_prompt() -> str:
    """用**真实的工具目录**拼一份 system prompt。

    工具清单来自 :func:`fr_cli.weapon.loader.load_weapon_md`（注册表派生），
    所以工具改名 / 改描述会立刻反映到评测上下文里。
    """
    from fr_cli.weapon.loader import load_weapon_md

    tools, _triggers = load_weapon_md()
    lines = ["你是 fr-cli 的执行 Agent。可用工具："]
    for tool in tools:
        commands = ", ".join(tool.get("commands") or [])
        lines.append(f"- {tool['name']}: {tool.get('description', '')} → {commands}")
    lines.append("需要执行操作时输出 【调用：工具名({...})】")
    return "\n".join(lines)


# ==================================================================
# 运行单个任务
# ==================================================================
@dataclass
class StepRecord:
    """一次工具调用的记录。"""

    index: int
    tool: str
    params: Dict[str, Any]
    ok: bool
    error: Optional[str]
    blocked: bool


@dataclass
class TaskOutcome:
    """一个任务的评测结果。"""

    task: EvalTask
    steps: List[StepRecord] = field(default_factory=list)
    selected_tool: Optional[str] = None
    selected_params: Dict[str, Any] = field(default_factory=dict)
    tool_matched: bool = False
    param_score: float = 0.0
    param_detail: List[str] = field(default_factory=list)
    actual_sequence: List[str] = field(default_factory=list)
    sequence_matched: bool = False
    blocked: Optional[bool] = None
    security_requests: List[Dict[str, Any]] = field(default_factory=list)
    finished: bool = False
    hit_step_limit: bool = False
    dispatch_ok: bool = False
    tool_output: str = ""
    deny_pass_error: Optional[str] = None
    error: Optional[str] = None

    @property
    def param_exact(self) -> bool:
        """参数是否完全匹配。"""
        return self.param_score >= 1.0

    @property
    def multi_step_ok(self) -> bool:
        """多步任务是否在 max_steps 内收敛。"""
        return self.sequence_matched and not self.hit_step_limit and self.finished


def _prepare_workdir(task: EvalTask, workdir: Path) -> None:
    """按任务的 setup 字段准备沙盒工作目录。"""
    workdir.mkdir(parents=True, exist_ok=True)
    for name in task.setup.get("dirs") or []:
        (workdir / name).mkdir(parents=True, exist_ok=True)
    for name, content in (task.setup.get("files") or {}).items():
        target = workdir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content), encoding="utf-8")


def _llm_turn(client, model_name: str, messages: List[Dict[str, Any]]) -> str:
    """跑一轮 LLM，把流式 chunk 拼成完整文本。"""
    chunks: List[str] = []
    for chunk in client.stream_chat(model_name, messages):
        content = chunk.get("content") if isinstance(chunk, dict) else None
        if content:
            chunks.append(content)
    return "".join(chunks)


def _observation(tool: str, result: Result) -> str:
    """把工具结果转成回喂给模型的一段观察文本。"""
    if result.is_ok():
        payload = result.unwrap()
        text = "" if payload is None else str(payload)
        return f"[工具结果] {tool} 执行成功: {text}"
    return f"[工具结果] {tool} 执行失败: {result.error}"


def _match_params(
    expected: Dict[str, Any], actual: Dict[str, Any]
) -> Tuple[float, List[str]]:
    """参数匹配度。

    Returns:
        (得分, 差异说明列表) —— 得分 = 命中 key 数 / 期望 key 数；
        期望为空时记 1.0。多余的实际参数不扣分（模型常带额外上下文）。
    """
    if not expected:
        return 1.0, []
    hits = 0
    diffs: List[str] = []
    for key, want in expected.items():
        if key not in actual:
            diffs.append(f"{key}: 缺失(期望 {want!r})")
            continue
        got = actual[key]
        if got == want:
            hits += 1
        else:
            diffs.append(f"{key}: 期望 {want!r}, 实际 {got!r}")
    return hits / len(expected), diffs


def run_task(
    task: EvalTask,
    workdir: Optional[Path] = None,
    cfg: Optional[Dict[str, Any]] = None,
    security_mode: str = "allow",
) -> TaskOutcome:
    """跑一个任务并返回结果。

    Args:
        task: 任务定义
        workdir: 沙盒工作目录（不给则用临时目录）
        cfg: 配置字典（不给则用 :func:`default_cfg`）
        security_mode: 安全确认策略 —— ``"allow"`` 放行（默认，用来验证工具
            真的能跑通）、``"deny"`` 一律拒绝（fail-closed，用来验证越权拦截）

    Returns:
        TaskOutcome: 评测结果
    """
    cfg = dict(cfg or default_cfg())
    tmp_dir: Optional[tempfile.TemporaryDirectory] = None
    if workdir is None:
        tmp_dir = tempfile.TemporaryDirectory(prefix="fr_cli_eval_")
        workdir = Path(tmp_dir.name)
    workdir = Path(workdir)
    _prepare_workdir(task, workdir)

    outcome = TaskOutcome(task=task)

    client = ScriptedMockClient(script=list(task.script))
    strategy = RecordingStrategy(
        decision="allow" if security_mode == "allow" else "deny", config=cfg
    )
    state = build_state(cfg, workdir, client, strategy)
    executor = state.executor

    # 工具 handler 会往 stdout 打 diff 预览等噪音 —— 收进缓冲区，别污染评测报告
    _sink = io.StringIO()

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": build_system_prompt()},
        {"role": "user", "content": task.user_input},
    ]

    try:
        with manual_mode(), contextlib.redirect_stdout(_sink):
            for step_index in range(task.max_steps):
                text = _llm_turn(client, state.model_name, messages)
                calls = executor._extract_tool_calls(text)
                if not calls:
                    # 模型给出最终答复 → 本轮收敛
                    outcome.finished = True
                    break
                for tool_name, arg_str, _marker in calls:
                    params = executor._parse_tool_kwargs(arg_str) or {}
                    result = executor.invoke_tool(tool_name, params, msgs=messages)
                    error = result.error
                    blocked = bool(result.is_fail() and error == "Denied")
                    outcome.steps.append(
                        StepRecord(
                            index=len(outcome.steps),
                            tool=tool_name,
                            params=params,
                            ok=result.is_ok(),
                            error=error,
                            blocked=blocked,
                        )
                    )
                    outcome.actual_sequence.append(tool_name)
                    # 以"最后一步"为准 —— 多步任务的 expect_tool 指的是最终动作
                    outcome.selected_tool = tool_name
                    outcome.selected_params = params
                    messages.append(
                        {"role": "user", "content": _observation(tool_name, result)}
                    )
            else:
                # 步数用尽仍未拿到最终答复
                outcome.hit_step_limit = True
    except Exception as exc:  # pragma: no cover - 兜底，避免评测整体崩掉
        outcome.error = f"{type(exc).__name__}: {exc}"
    finally:
        # 记录确认流程被询问过几次、问了什么 —— 越权拦截率靠它判定
        outcome.security_requests = list(strategy.requests)
        outcome.tool_output = _sink.getvalue()[-2000:]
        if tmp_dir is not None:
            tmp_dir.cleanup()

    _finalize(outcome)
    return outcome


def _finalize(outcome: TaskOutcome) -> None:
    """根据执行记录结算各项判定。"""
    task = outcome.task
    outcome.tool_matched = outcome.selected_tool == task.expect_tool
    outcome.param_score, outcome.param_detail = _match_params(
        task.expect_params, outcome.selected_params
    )
    expected_seq = task.expected_sequence
    outcome.sequence_matched = (
        bool(expected_seq)
        and outcome.actual_sequence[: len(expected_seq)] == expected_seq
    )
    # 被拦下的调用 = 最后一步（也就是期望的那次调用）被 Denied
    outcome.blocked = bool(outcome.steps) and outcome.steps[-1].blocked
    # 端到端成功 = 每一步都跑通了
    outcome.dispatch_ok = bool(outcome.steps) and all(s.ok for s in outcome.steps)


def run_all(
    tasks: Sequence[EvalTask],
    workdir: Optional[Path] = None,
    cfg: Optional[Dict[str, Any]] = None,
) -> List[TaskOutcome]:
    """跑一批任务。

    每个任务用**独立的子目录**，避免互相污染。

    安全类任务跑**两遍**：

    * ``allow`` 遍 —— 放行确认，验证工具链路真的能跑通（文件真被写进去了）
    * ``deny`` 遍 —— fail-closed，验证该被拦的调用真的被拦下

    结果以 ``deny`` 遍的拦截结论为准（``outcome.blocked``），
    ``allow`` 遍的结论用于校验工具是否真的执行成功。
    """
    results: List[TaskOutcome] = []
    base = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="fr_cli_eval_"))
    base.mkdir(parents=True, exist_ok=True)
    for task in tasks:
        task_dir = base / task.id
        task_dir.mkdir(parents=True, exist_ok=True)
        if task.expect_blocked is None:
            outcome = run_task(
                task, workdir=task_dir, cfg=cfg, security_mode="allow"
            )
        else:
            allow_outcome = run_task(
                task, workdir=task_dir, cfg=cfg, security_mode="allow"
            )
            deny_outcome = run_task(
                task, workdir=task_dir, cfg=cfg, security_mode="deny"
            )
            # 拦截结论取 deny 遍；确认请求两边都留着（allow 遍证明流程被走到过）
            allow_outcome.blocked = deny_outcome.blocked
            allow_outcome.security_requests = (
                deny_outcome.security_requests + allow_outcome.security_requests
            )
            allow_outcome.deny_pass_error = deny_outcome.error
            outcome = allow_outcome
        results.append(outcome)
    return results


# ==================================================================
# 指标
# ==================================================================
@dataclass
class EvalMetrics:
    """四个核心指标 + 若干辅助指标。

    Attributes:
        tool_selection_accuracy: 工具选择正确率
        param_accuracy: 参数正确率（工具命中后计算）
        multi_step_completion: 多步完成率
        security_interception: 越权拦截率
        end_to_end_rate: 端到端成功率（辅助）
        false_block_rate: 误拦率（辅助 —— 本该放行却被拦的比例）
        total: 任务总数
    """

    tool_selection_accuracy: float = 0.0
    param_accuracy: float = 0.0
    multi_step_completion: float = 0.0
    security_interception: float = 0.0
    end_to_end_rate: float = 0.0
    false_block_rate: float = 0.0
    total: int = 0
    tool_matched: int = 0
    param_scored: int = 0
    multi_step_total: int = 0
    multi_step_ok: int = 0
    security_total: int = 0
    security_blocked: int = 0
    false_block_total: int = 0
    false_blocked: int = 0
    end_to_end_ok: int = 0
    known_issue_total: int = 0
    known_issue_ok: int = 0

    @property
    def regression_total(self) -> int:
        """排除"已知缺陷"任务后的任务数 —— 这才是回归基线。"""
        return self.total - self.known_issue_total

    @property
    def regression_ok(self) -> int:
        """排除"已知缺陷"任务后的成功数。"""
        return self.end_to_end_ok - self.known_issue_ok

    @property
    def regression_rate(self) -> float:
        """排除"已知缺陷"后的端到端成功率。"""
        if self.regression_total <= 0:
            return 1.0
        return self.regression_ok / self.regression_total

    def to_dict(self) -> Dict[str, Any]:
        """转成普通 dict（便于 JSON 输出）。"""
        return {
            "tool_selection_accuracy": round(self.tool_selection_accuracy, 4),
            "param_accuracy": round(self.param_accuracy, 4),
            "multi_step_completion": round(self.multi_step_completion, 4),
            "security_interception": round(self.security_interception, 4),
            "end_to_end_rate": round(self.end_to_end_rate, 4),
            "regression_rate": round(self.regression_rate, 4),
            "false_block_rate": round(self.false_block_rate, 4),
            "total": self.total,
            "tool_matched": self.tool_matched,
            "param_scored": self.param_scored,
            "multi_step_total": self.multi_step_total,
            "multi_step_ok": self.multi_step_ok,
            "security_total": self.security_total,
            "security_blocked": self.security_blocked,
            "false_block_total": self.false_block_total,
            "false_blocked": self.false_blocked,
            "end_to_end_ok": self.end_to_end_ok,
            "known_issue_total": self.known_issue_total,
            "known_issue_ok": self.known_issue_ok,
        }


def compute_metrics(outcomes: Sequence[TaskOutcome]) -> EvalMetrics:
    """从任务结果算出四个核心指标。

    口径
    ----
    1. **工具选择正确率** —— 选中的工具名 == 期望工具名 的任务占比。
    2. **参数正确率** —— 在"工具命中"的任务里，期望参数的逐 key 命中率均值
       （期望参数为空记 1.0）。
    3. **多步完成率** —— 多步任务里，期望工具序列按序跑完且在 max_steps 内
       收敛（拿到最终答复）的占比。
    4. **越权拦截率** —— 期望被拦的任务里，**真的走进了 state.security 的确认
       流程并被拦下**的占比。
    """
    metrics = EvalMetrics()
    metrics.total = len(outcomes)
    if not outcomes:
        return metrics

    param_scores: List[float] = []
    end_to_end = 0
    for outcome in outcomes:
        task = outcome.task
        if outcome.tool_matched:
            metrics.tool_matched += 1
            param_scores.append(outcome.param_score)
            metrics.param_scored += 1

        if task.is_multi_step:
            metrics.multi_step_total += 1
            if outcome.multi_step_ok:
                metrics.multi_step_ok += 1

        if task.expect_blocked is True:
            metrics.security_total += 1
            # 必须同时满足：调用被拒 + 确认流程确实被走到
            consulted = any(
                req.get("tool_name") == task.expect_tool
                and (not task.expect_security or req.get("key") == task.expect_security)
                for req in outcome.security_requests
            )
            if outcome.blocked and consulted:
                metrics.security_blocked += 1
        elif task.expect_blocked is False:
            metrics.false_block_total += 1
            if outcome.blocked:
                metrics.false_blocked += 1

        block_ok = (
            task.expect_blocked is None
            or (task.expect_blocked is True and outcome.blocked)
            or (task.expect_blocked is False and not outcome.blocked)
        )
        task_ok = (
            outcome.tool_matched
            and outcome.param_exact
            and outcome.dispatch_ok
            and block_ok
            and outcome.error is None
        )
        if task_ok:
            end_to_end += 1
        if task.known_issue:
            metrics.known_issue_total += 1
            if task_ok:
                metrics.known_issue_ok += 1

    metrics.tool_selection_accuracy = metrics.tool_matched / metrics.total
    metrics.param_accuracy = (
        sum(param_scores) / len(param_scores) if param_scores else 0.0
    )
    metrics.multi_step_completion = (
        metrics.multi_step_ok / metrics.multi_step_total
        if metrics.multi_step_total
        else 1.0
    )
    metrics.security_interception = (
        metrics.security_blocked / metrics.security_total
        if metrics.security_total
        else 1.0
    )
    metrics.false_block_rate = (
        metrics.false_blocked / metrics.false_block_total
        if metrics.false_block_total
        else 0.0
    )
    metrics.end_to_end_rate = end_to_end / metrics.total
    metrics.end_to_end_ok = end_to_end
    return metrics
