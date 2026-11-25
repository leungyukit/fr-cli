"""eval 层 pytest 集成 —— 让 CI 能跑这套离线评测。

跳过方式::

    FR_CLI_SKIP_EVALS=1 pytest tests/evals/

为什么需要跳过开关
------------------
eval 依赖 ``tests/evals/datasets/`` 下的任务集与 fixture。普通单测环境
（比如只装了包、没带仓库测试资产的环境）可能没有这些文件 —— 缺了就跳过，
而不是让整个测试会话红掉。

另外：eval 全程零网络，所以这里会**主动把 socket 封死**再跑一遍评测，
用"跑得通"来证明它确实没有出网。
"""
from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

import pytest

# --- 路径引导：保证无论 pytest 用哪种 import 模式都能找到 harness ---
_EVAL_DIR = Path(__file__).resolve().parent
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from harness import (  # noqa: E402  (路径引导必须在 import 之前)
    DATASET_DIR,
    build_state,
    compute_metrics,
    default_cfg,
    load_tasks,
    run_all,
)

#: 显式跳过开关
SKIP_ENV = "FR_CLI_SKIP_EVALS"

pytestmark = pytest.mark.skipif(
    os.environ.get(SKIP_ENV) == "1",
    reason=f"{SKIP_ENV}=1 —— 已显式跳过 eval 层",
)


# ------------------------------------------------------------------
# 夹具
# ------------------------------------------------------------------
@pytest.fixture(scope="module")
def tasks():
    """加载全部评测任务。"""
    return load_tasks(DATASET_DIR)


@pytest.fixture(scope="module")
def outcomes(tasks, tmp_path_factory):
    """跑一遍完整任务集（模块级，只跑一次）。"""
    workdir = tmp_path_factory.mktemp("evals")
    return run_all(tasks, workdir=workdir, cfg=default_cfg())


@pytest.fixture(scope="module")
def metrics(outcomes):
    """由任务结果算出的指标。"""
    return compute_metrics(outcomes)


@pytest.fixture
def no_network(monkeypatch):
    """把 socket 封死 —— 任何出网尝试都会让用例失败。"""

    def _boom(*args, **kwargs):
        raise AssertionError("eval 层不允许发起网络连接")

    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)
    monkeypatch.setattr(socket, "getaddrinfo", _boom)
    return True


# ------------------------------------------------------------------
# 数据集
# ------------------------------------------------------------------
class TestDataset:
    def test_dataset_has_enough_tasks(self, tasks):
        """任务集至少 8-12 条，覆盖单步 / 多步 / 安全三类。"""
        assert len(tasks) >= 8, f"任务太少: {len(tasks)}"

    def test_task_ids_are_unique(self, tasks):
        ids = [t.id for t in tasks]
        assert len(ids) == len(set(ids)), "任务 id 重复"

    def test_tasks_have_required_fields(self, tasks):
        for task in tasks:
            assert task.id
            assert task.user_input
            assert task.expect_tool
            assert task.max_steps >= 1
            assert task.script, f"{task.id} 缺少 script"

    def test_dataset_covers_three_families(self, tasks):
        """必须同时覆盖单步 / 多步 / 安全拦截三类场景。"""
        assert any(t.is_multi_step for t in tasks), "缺少多步任务"
        assert any(t.expect_blocked is True for t in tasks), "缺少越权拦截任务"
        assert any(t.expect_blocked is False for t in tasks), "缺少对照组任务"

    def test_expected_tools_exist_in_registry(self, tasks):
        """期望的工具必须真的在注册表里 —— 否则评测的是空气。"""
        from fr_cli.command.registry import get_registry

        known = {t["name"] for t in get_registry().get_tools()}
        for task in tasks:
            assert task.expect_tool in known, f"{task.id}: 工具 {task.expect_tool} 未注册"
            for tool in task.expected_sequence:
                assert tool in known, f"{task.id}: 工具 {tool} 未注册"


# ------------------------------------------------------------------
# 四个核心指标
# ------------------------------------------------------------------
class TestCoreMetrics:
    def test_tool_selection_accuracy(self, metrics):
        """工具选择正确率必须 100%。"""
        assert metrics.tool_selection_accuracy == 1.0, (
            f"工具选择正确率 {metrics.tool_selection_accuracy:.2%} < 100%"
        )

    def test_param_accuracy(self, metrics):
        """参数正确率必须 100%。"""
        assert metrics.param_accuracy == 1.0, (
            f"参数正确率 {metrics.param_accuracy:.2%} < 100%"
        )

    def test_multi_step_completion(self, metrics):
        """多步完成率必须 100%。"""
        assert metrics.multi_step_total > 0, "没有多步任务"
        assert metrics.multi_step_completion == 1.0, (
            f"多步完成率 {metrics.multi_step_completion:.2%} < 100%"
        )

    def test_security_interception(self, metrics):
        """越权拦截率必须 100% —— 这是最关键的一条。"""
        assert metrics.security_total > 0, "没有越权拦截任务"
        assert metrics.security_interception == 1.0, (
            f"越权拦截率 {metrics.security_interception:.2%} < 100%"
        )

    def test_no_false_block(self, metrics):
        """对照组：本该放行的工具不能被误拦。"""
        assert metrics.false_block_total > 0, "缺少对照组任务"
        assert metrics.false_block_rate == 0.0, (
            f"误拦率 {metrics.false_block_rate:.2%} > 0"
        )

    def test_regression_baseline_is_clean(self, metrics):
        """排除"已知缺陷"后，端到端必须全绿（不许有回归）。"""
        assert metrics.regression_rate == 1.0, (
            f"回归基线 {metrics.regression_rate:.2%} < 100%"
        )


# ------------------------------------------------------------------
# 越权拦截的真实性
# ------------------------------------------------------------------
class TestSecurityFlow:
    def test_blocked_call_really_went_through_state_security(self, outcomes):
        """被拦的调用必须真的问过 state.security（而不是别的机制拦的）。"""
        blocked_tasks = [
            o for o in outcomes if o.task.expect_blocked is True
        ]
        assert blocked_tasks, "没有越权拦截任务"
        for outcome in blocked_tasks:
            assert outcome.blocked, f"{outcome.task.id}: 调用没有被拦下"
            assert outcome.security_requests, (
                f"{outcome.task.id}: 没有走过安全确认流程"
            )
            keys = {r["key"] for r in outcome.security_requests}
            assert outcome.task.expect_security in keys, (
                f"{outcome.task.id}: 确认类别不符，期望 "
                f"{outcome.task.expect_security}，实际 {keys}"
            )

    def test_control_task_never_reaches_confirmation(self, outcomes):
        """无安全级别的工具不该触发确认流程。"""
        controls = [o for o in outcomes if o.task.expect_blocked is False]
        assert controls, "缺少对照组任务"
        for outcome in controls:
            assert not outcome.security_requests, (
                f"{outcome.task.id}: 无安全级别却触发了确认 "
                f"{outcome.security_requests}"
            )

    def test_security_manager_is_the_real_one(self, outcomes):
        """确认走的是生产实现 SecurityManager，不是测试替身。"""
        from fr_cli.command.security import SecurityManager

        outcome = outcomes[0]
        state = build_state(default_cfg(), Path("/tmp"), None)
        assert isinstance(state.security, SecurityManager)
        assert outcome.task.id  # 仅避免未使用告警


# ------------------------------------------------------------------
# 离线保证
# ------------------------------------------------------------------
class TestOffline:
    def test_eval_runs_with_sockets_blocked(self, tasks, tmp_path, no_network):
        """把 socket 封死后，eval 依然能跑完 —— 证明全程零网络。"""
        results = run_all(tasks, workdir=tmp_path, cfg=default_cfg())
        assert len(results) == len(tasks)
        m = compute_metrics(results)
        assert m.tool_selection_accuracy == 1.0
        assert m.security_interception == 1.0

    def test_no_api_key_needed(self, tasks, tmp_path, monkeypatch):
        """把 API Key 环境变量清空后照样能跑。"""
        for key in ("ZHIPUAI_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"):
            monkeypatch.delenv(key, raising=False)
        results = run_all(tasks, workdir=tmp_path, cfg=default_cfg())
        assert compute_metrics(results).tool_selection_accuracy == 1.0


# ------------------------------------------------------------------
# 录制 / 回放
# ------------------------------------------------------------------
class TestFixtureReplay:
    def test_sample_fixture_replays_offline(self):
        """仓库里的样例 fixture 能离线回放出同样的响应。"""
        from fr_cli.core.llm.mock import ScriptedMockClient

        fixture = _EVAL_DIR / "fixtures" / "sample_session.json"
        assert fixture.exists(), f"缺少样例 fixture: {fixture}"
        client = ScriptedMockClient.load_fixture(fixture)
        replies = [
            "".join(
                c.get("content", "")
                for c in client.stream_chat("mock", [{"role": "user", "content": "x"}])
            )
            for _ in range(2)
        ]
        assert replies[0].startswith("好的，我来把内容写进 a.txt")
        assert "write_file" in replies[0]
        assert replies[1] == "已经写好了，a.txt 里现在是 hello world。"

    def test_record_then_replay_roundtrip(self, tmp_path):
        """录一次 → 存 fixture → 回放，响应完全一致。"""
        from fr_cli.core.llm.mock import (
            RecordingClient,
            ScriptedMockClient,
        )

        inner = ScriptedMockClient(script=["第一轮", "第二轮"])
        recorder = RecordingClient(inner, name="unit")
        for text in ("问一", "问二"):
            list(recorder.stream_chat("mock", [{"role": "user", "content": text}]))
        path = recorder.save_fixture(tmp_path / "roundtrip.json")
        assert path.exists()

        player = ScriptedMockClient.load_fixture(path)
        got = [
            "".join(
                c.get("content", "")
                for c in player.stream_chat("mock", [{"role": "user", "content": t}])
            )
            for t in ("问一", "问二")
        ]
        assert got == ["第一轮", "第二轮"]
