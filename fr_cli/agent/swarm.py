"""
蜂群引擎（Swarm Engine）—— 多 Agent 协作中枢
支持：并行独立执行、议会汇总、流水线串联
"""
import concurrent.futures
import json
from fr_cli.agent.swarm_resolver import SwarmTaskResolver


class SwarmEngine:
    """蜂群引擎：协调多个 Agent 同时或协作工作"""

    MAX_WORKERS = 10

    def __init__(self, state):
        self.state = state

    def run(self, mode, names, user_input, max_workers=5, timeout=60, **kwargs):
        """
        蜂群统一入口。

        Args:
            mode: "parallel" | "council" | "pipeline"
            names: Agent 名称列表
            user_input: 任务描述/初始输入
            max_workers: 最大并发数
            timeout: 单任务超时秒数（默认 60）

        Returns:
            (result_dict, None) 或 (None, error)
        """
        mode = str(mode).lower()
        if not names:
            return None, "蜂群至少需要 1 个 Agent"
        if mode == "parallel":
            return self.run_parallel(names, user_input, max_workers=max_workers, timeout=timeout)
        if mode == "council":
            return self.run_council(names, user_input, max_workers=max_workers, timeout=timeout)
        if mode == "pipeline":
            return self.run_pipeline(names, user_input)
        return None, f"不支持的蜂群模式: {mode}（支持 parallel/council/pipeline）"

    def run_parallel(self, names, user_input, max_workers=5, timeout=60):
        """
        并行独立执行：每个 Agent 同时处理同一任务。

        Returns:
            {"mode": "parallel", "results": [{"agent": str, "result": any, "error": str|None}]}
        """
        results = self._execute_parallel(names, user_input, max_workers=max_workers, timeout=timeout)
        return {"mode": "parallel", "results": results}, None

    def run_council(self, names, user_input, max_workers=5, timeout=60):
        """
        议会模式：并行收集各 Agent 意见，再交由 LLM 综合汇总。

        Returns:
            {"mode": "council", "individual": [...], "summary": str}
        """
        individual = self._execute_parallel(names, user_input, max_workers=max_workers, timeout=timeout)
        summary = self._summarize_with_llm(user_input, individual)
        return {
            "mode": "council",
            "individual": individual,
            "summary": summary,
        }, None

    def run_pipeline(self, names, initial_input):
        """
        流水线模式：多个任务串联执行，前一个的输出作为后一个的输入。
        任务可以是 Agent、工具、命令、MCP 或插件。

        Returns:
            {"mode": "pipeline", "results": [{"agent": str, "kind": str, "target": str, "result": any}]}
        """
        pipeline_result = initial_input
        logs = []
        resolver = SwarmTaskResolver(self.state)

        for idx, name in enumerate(names, start=1):
            kind, target, _ = resolver.resolve(name)
            print(f"[流水线] {idx}/{len(names)}: 运行 {kind} [{target}]")
            result, err = resolver.call(name, str(pipeline_result) if pipeline_result else "")
            if err:
                return None, f"Pipeline step {idx} ('{name}'): {err}"
            logs.append({"agent": name, "kind": kind, "target": target, "result": result})
            pipeline_result = result

        return {"mode": "pipeline", "results": logs}, None

    def _execute_parallel(self, names, user_input, max_workers=5, timeout=60):
        """内部：并发执行所有任务（Agent / 工具 / 命令 / MCP / 插件），支持超时"""
        workers = min(int(max_workers), self.MAX_WORKERS)
        workers = max(1, workers)

        results = []
        resolver = SwarmTaskResolver(self.state)

        def _call_one(name):
            if not isinstance(name, str) or not name:
                return {"agent": str(name), "result": None, "error": "任务名称无效"}
            try:
                kind, target, _ = resolver.resolve(name)
                result, err = resolver.call(name, user_input)
                return {"agent": name, "kind": kind, "target": target, "result": result, "error": err}
            except Exception as e:
                return {"agent": name, "kind": "unknown", "target": name, "result": None, "error": str(e)}

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(_call_one, name) for name in names]
            for future in concurrent.futures.as_completed(futures):
                try:
                    results.append(future.result(timeout=timeout))
                except concurrent.futures.TimeoutError:
                    results.append({"agent": "unknown", "result": None, "error": f"任务执行超时（{timeout}秒）"})

        # 保持原始顺序
        order_map = {name: idx for idx, name in enumerate(names)}
        results.sort(key=lambda x: order_map.get(x["agent"], 9999))
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

        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
            )
            return resp.choices[0].message.content
        except Exception as e:
            return f"[汇总失败: {e}]"


def run_swarm(mode, names, state, user_input, max_workers=5, **kwargs):
    """
    蜂群执行便捷函数。

    Returns:
        (result_dict, None) 或 (None, error)
    """
    engine = SwarmEngine(state)
    return engine.run(mode, names, user_input, max_workers=max_workers, **kwargs)
