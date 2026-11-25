"""
蜂群引擎（Swarm Engine）—— 多 Agent 协作中枢
支持：并行独立执行、议会汇总、流水线串联

v3.1 变更：timeout 由"死代码"改为真正的整体 deadline
- 旧实现用 ``as_completed(futures)``（不带 timeout）只取已完成任务，
  随后的 ``future.result(timeout=...)`` 立刻返回，超时分支永远不会触发；
- 新实现用 ``concurrent.futures.wait(futures, timeout=...)`` 实现整体 deadline，
  到点立即返回，未完成任务以"带真实任务名的超时条目"返回（部分失败语义）；
- 线程池改为显式 ``shutdown(wait=False)``，避免 ``with`` 退出时 join 挂起线程，
  导致"超时仍然不生效"。
"""
import concurrent.futures
import json
import time
from typing import Any, Dict, List, Optional

from fr_cli.agent.swarm_resolver import SwarmTaskResolver

# 蜂群整体 deadline 默认值（秒）；config.json 的 swarm_timeout 可覆盖
DEFAULT_SWARM_TIMEOUT = 60

# 流水线单步超时的内部标记（与普通错误信息区分）
_TIMEOUT_MARKER = "__swarm_timeout__"


def _to_positive_float(value: Any) -> Optional[float]:
    """把任意值转成正浮点数；非法或非正数返回 None。"""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num if num > 0 else None


def resolve_swarm_timeout(state, override: Any = None) -> float:
    """解析蜂群整体超时（秒）。

    优先级：显式入参 > config.json 的 ``swarm_timeout`` > 默认 60。
    """
    explicit = _to_positive_float(override)
    if explicit is not None:
        return explicit
    cfg = getattr(state, "cfg", None)
    if isinstance(cfg, dict):
        configured = _to_positive_float(cfg.get("swarm_timeout"))
        if configured is not None:
            return configured
    return float(DEFAULT_SWARM_TIMEOUT)


class SwarmEngine:
    """蜂群引擎：协调多个 Agent 同时或协作工作"""

    MAX_WORKERS = 10

    def __init__(self, state):
        self.state = state

    def run(self, mode, names, user_input, max_workers=5, timeout=None, **kwargs):
        """
        蜂群统一入口。

        Args:
            mode: "parallel" | "council" | "pipeline"
            names: Agent 名称列表
            user_input: 任务描述/初始输入
            max_workers: 最大并发数
            timeout: 整体 deadline 秒数；None 表示取 config.json 的
                ``swarm_timeout``（默认 60）

        Returns:
            (result_dict, None) 或 (None, error)
        """
        mode = str(mode).lower()
        if not names:
            return None, "蜂群至少需要 1 个 Agent"
        timeout = resolve_swarm_timeout(self.state, timeout)
        if mode == "parallel":
            return self.run_parallel(names, user_input, max_workers=max_workers, timeout=timeout)
        if mode == "council":
            return self.run_council(names, user_input, max_workers=max_workers, timeout=timeout)
        if mode == "pipeline":
            return self.run_pipeline(names, user_input, timeout=timeout)
        return None, f"不支持的蜂群模式: {mode}（支持 parallel/council/pipeline）"

    def run_parallel(self, names, user_input, max_workers=5, timeout=None):
        """
        并行独立执行：每个 Agent 同时处理同一任务。

        Args:
            names: 任务名列表
            user_input: 任务描述
            max_workers: 最大并发数
            timeout: 整体 deadline 秒数；None 表示取 config.json 的 ``swarm_timeout``

        Returns:
            {"mode": "parallel", "results": [{"agent": str, "kind": str, "target": str,
                                              "result": any, "error": str|None}]}
        """
        timeout = resolve_swarm_timeout(self.state, timeout)
        results = self._execute_parallel(names, user_input, max_workers=max_workers, timeout=timeout)
        return {"mode": "parallel", "results": results}, None

    def run_council(self, names, user_input, max_workers=5, timeout=None):
        """
        议会模式：并行收集各 Agent 意见，再交由 LLM 综合汇总。

        Returns:
            {"mode": "council", "individual": [...], "summary": str}
        """
        timeout = resolve_swarm_timeout(self.state, timeout)
        individual = self._execute_parallel(names, user_input, max_workers=max_workers, timeout=timeout)
        summary = self._summarize_with_llm(user_input, individual)
        return {
            "mode": "council",
            "individual": individual,
            "summary": summary,
        }, None

    def run_pipeline(self, names, initial_input, timeout=None):
        """
        流水线模式：多个任务串联执行，前一个的输出作为后一个的输入。
        任务可以是 Agent、工具、命令、MCP 或插件。

        Args:
            names: 任务名列表
            initial_input: 初始输入
            timeout: 整体 deadline 秒数；None 表示取 config.json 的 ``swarm_timeout``

        Returns:
            {"mode": "pipeline", "results": [{"agent": str, "kind": str, "target": str,
                                              "result": any, "error": str|None}]}
        """
        timeout = resolve_swarm_timeout(self.state, timeout)
        deadline = time.monotonic() + timeout if timeout and timeout > 0 else None
        pipeline_result = initial_input
        logs: List[Dict[str, Any]] = []
        resolver = SwarmTaskResolver(self.state)

        for idx, name in enumerate(names, start=1):
            kind, target, _ = resolver.resolve(name)
            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            if remaining is not None and remaining <= 0:
                # 整体 deadline 已耗尽：按"部分失败"语义记录超时条目后停止
                logs.append(self._timeout_entry(resolver, name, timeout))
                break
            print(f"[流水线] {idx}/{len(names)}: 运行 {kind} [{target}]")
            result, err = self._call_with_deadline(
                resolver, name, str(pipeline_result) if pipeline_result else "", remaining
            )
            if err == _TIMEOUT_MARKER:
                logs.append(self._timeout_entry(resolver, name, timeout))
                break
            if err:
                return None, f"Pipeline step {idx} ('{name}'): {err}"
            logs.append({"agent": name, "kind": kind, "target": target, "result": result, "error": None})
            pipeline_result = result

        return {"mode": "pipeline", "results": logs}, None

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    @staticmethod
    def _call_with_deadline(resolver, name, payload, timeout):
        """在给定 deadline 内执行单个流水线任务。

        Returns:
            (result, error)；超时时 error 为内部标记 ``_TIMEOUT_MARKER``。
        """
        if timeout is None or timeout <= 0:
            return resolver.call(name, payload)
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(resolver.call, name, payload)
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                return None, _TIMEOUT_MARKER
        finally:
            # 不等待挂起线程（Python 无法强杀线程，诚实边界）
            executor.shutdown(wait=False)

    @staticmethod
    def _timeout_entry(resolver, name, timeout):
        """构造超时条目：带真实任务名 + kind/target（解析失败时降级为 unknown）。"""
        agent_name = name if isinstance(name, str) and name else str(name)
        kind, target = "unknown", agent_name
        try:
            kind, target, _ = resolver.resolve(agent_name)
        except Exception:
            pass
        return {
            "agent": agent_name,
            "kind": kind,
            "target": target,
            "result": None,
            "error": f"任务执行超时（{timeout:g}秒）",
        }

    def _execute_parallel(self, names, user_input, max_workers=5, timeout=60):
        """内部：并发执行所有任务（Agent / 工具 / 命令 / MCP / 插件），支持真正的整体 deadline。

        超时语义：到达 deadline 立即返回，未完成任务以"带真实任务名的超时条目"返回，
        整体 err 仍为 None（部分失败），不让单个任务超时拖垮整个蜂群。

        诚实边界：Python 无法强杀线程，超时任务的线程会继续跑完，
        但不再阻塞调用方返回。
        """
        workers = min(int(max_workers), self.MAX_WORKERS)
        workers = max(1, workers)

        results: List[Dict[str, Any]] = []
        resolver = SwarmTaskResolver(self.state)

        def _call_one(name):
            if not isinstance(name, str) or not name:
                return {"agent": str(name), "kind": "unknown", "target": str(name),
                        "result": None, "error": "任务名称无效"}
            try:
                kind, target, _ = resolver.resolve(name)
                result, err = resolver.call(name, user_input)
                return {"agent": name, "kind": kind, "target": target, "result": result, "error": err}
            except Exception as e:
                return {"agent": name, "kind": "unknown", "target": name, "result": None, "error": str(e)}

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
        try:
            futures = {executor.submit(_call_one, name): name for name in names}
            done, not_done = concurrent.futures.wait(futures, timeout=timeout)
            for future in done:
                try:
                    results.append(future.result())
                except Exception as e:  # 理论上 _call_one 已兜底，这里再兜一层
                    failed_name = futures[future]
                    results.append({
                        "agent": failed_name,
                        "kind": "unknown",
                        "target": failed_name,
                        "result": None,
                        "error": str(e),
                    })
            for future in not_done:
                results.append(self._timeout_entry(resolver, futures[future], timeout))
        finally:
            # 关键：不能等待挂起线程，否则"真超时"仍然不生效
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except TypeError:  # Python 3.8 不支持 cancel_futures
                executor.shutdown(wait=False)

        # 保持原始顺序（重名任务以首次出现的位置为准，避免互相覆盖）
        order_map: Dict[str, int] = {}
        for idx, name in enumerate(names):
            order_map.setdefault(str(name), idx)
        results.sort(key=lambda x: order_map.get(str(x.get("agent")), 9999))
        return results

    def _summarize_with_llm(self, user_input, individual):
        """调用全局 LLM 汇总各任务输出"""
        client = getattr(self.state, "client", None)
        model = getattr(self.state, "model_name", None)
        if not client or not model:
            return "[模型未配置，无法生成汇总]"

        valid_results = [r for r in individual if r.get("error") is None and r.get("result") is not None]
        if not valid_results:
            return "[所有任务均执行失败，无法汇总]"

        parts = []
        for r in valid_results:
            result_text = r["result"]
            if isinstance(result_text, dict):
                try:
                    result_text = json.dumps(result_text, ensure_ascii=False, indent=2)
                except Exception:
                    result_text = str(result_text)
            else:
                result_text = str(result_text)
            kind = r.get("kind", "agent")
            parts.append(f"### [{kind}] {r['agent']}\n{result_text}")

        prompt = (
            "你是一位高效的协调者。以下是多个任务针对同一任务目标给出的各自独立结果。\n\n"
            f"任务：{user_input}\n\n"
            "各任务输出如下：\n\n"
            f"{'\n\n'.join(parts)}\n\n"
            "请综合以上所有结果，去重、补全、解决冲突，给出一份结构清晰、完整准确的最终结论。"
            "不要提及“Agent”、“工具”或“汇总”等内部概念，直接给出用户可用的最终答案。"
        )

        # v2.8.9：此前直接调 client.chat.completions.create —— 那是 OpenAI SDK
        # **内部**对象（openai_compat.py 里是 self._client.chat.completions），
        # 不是 fr_cli 客户端的公开属性。结果：所有 OpenAI 兼容厂商
        # （DeepSeek/Kimi/Qwen/StepFun/MiniMax/讯飞/MiMo）的议会汇总**一直失败**，
        # 只会吐一句 "[汇总失败: ... has no attribute 'chat']"。
        # 现统一走公开接口 stream_chat（core/llm/completion.py::complete_text）。
        from fr_cli.core.llm.completion import complete_text

        text, err = complete_text(
            client, model,
            [{"role": "user", "content": prompt}],
            lang=getattr(self.state, "lang", "zh"),
            provider=getattr(self.state, "provider", None),
        )
        if err:
            return f"[汇总失败: {err}]"
        return text


def run_swarm(mode, names, state, user_input, max_workers=5, **kwargs):
    """
    蜂群执行便捷函数。

    Returns:
        (result_dict, None) 或 (None, error)
    """
    engine = SwarmEngine(state)
    return engine.run(mode, names, user_input, max_workers=max_workers, **kwargs)
