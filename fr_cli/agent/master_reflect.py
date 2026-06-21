"""
MasterAgent 反思进化 Mixin

从 master.py 抽离出来，负责：
  - _record_interaction()  记录单次工具调用
  - _get_recent_memory()   获取最近 5 条交互摘要
  - _get_failure_hint()    查询针对工具的历史失败提示
  - _maybe_compress_messages()  长上下文自动压缩
  - _reflect_and_evolve()  每 10 次交互触发自我进化

通过 mixin 模式挂载到 MasterAgent 类。
"""
import json
from datetime import datetime

from fr_cli.memory.compress import maybe_compress

from fr_cli.agent.master_storage import (
    EVOLUTION_FILE,
    MEMORY_FILE,
    STATUS_FILE,
    _classify_error,
    _save_json,
)


class MasterAgentReflectMixin:
    """反思进化 mixin。

    需要 MasterAgent 提供：
      - self.state（含 .client / .model_name / .lang / .context_compress_threshold /
                  .context_compress_keep_recent / .limit）
      - self.memory / self.evolution / self._status_data
    """

    # ---------- 记忆与进化 ----------

    def _record_interaction(self, user_input, tool_name, success, detail, tool_params=None):
        """记录单次交互到内存"""
        self.memory.setdefault("interactions", []).append({
            "time": datetime.now().isoformat(),
            "input": user_input[:100],
            "tool": tool_name,
            "success": success,
            "detail": detail[:200],
            "error_type": None if success else _classify_error(detail),
            "tool_params": tool_params or {},
        })
        # 只保留最近 100 条
        self.memory["interactions"] = self.memory["interactions"][-100:]
        _save_json(MEMORY_FILE, self.memory)

    def _get_recent_memory(self):
        """获取最近 5 条关键记忆摘要"""
        interactions = self.memory.get("interactions", [])
        if not interactions:
            return ""
        recent = interactions[-5:]
        lines = []
        for item in recent:
            status = "✅" if item["success"] else "❌"
            err = f" ({item.get('error_type')})" if not item["success"] and item.get("error_type") else ""
            lines.append(f"{status} [{item['tool']}{err}] {item['input']} → {item['detail'][:80]}")
        return "\n".join(lines)

    def _get_failure_hint(self, tool_name: str) -> str:
        """返回针对指定工具的历史失败提示（最多3条），供当前调用前参考。"""
        hints = self.evolution.get("failure_hints", [])
        matched = [h for h in hints if h.get("tool") == tool_name]
        if not matched:
            return ""
        lines = [f"- {h.get('error_type', '错误')}: {h.get('hint', '')}" for h in matched[:3]]
        return "历史同类失败提示：\n" + "\n".join(lines)

    def _maybe_compress_messages(self, messages: list):
        """当上下文估算 token 超过阈值时，对较早轮次进行摘要压缩。"""
        threshold = getattr(self.state, "context_compress_threshold", 4000)
        keep_recent = getattr(self.state, "context_compress_keep_recent", 5)
        if threshold <= 0 or len(messages) <= keep_recent * 2 + 1:
            return
        # 自适应阈值：不超过模型 token 上限的 60%
        limit = getattr(self.state, "limit", 0) or 0
        effective_threshold = min(threshold, int(limit * 0.6)) if limit > 0 else threshold
        try:
            compressed, did_compress, before, after = maybe_compress(
                messages,
                self.state.client,
                self.state.model_name,
                lang=self.state.lang,
                threshold=effective_threshold,
                keep_recent=keep_recent,
            )
            if did_compress:
                messages[:] = compressed
        except Exception:
            pass

    # ---------- 反思与进化 ----------

    def _reflect_and_evolve(self, task, observations, result):
        """反思并触发自我进化（仅在积累足够数据时执行）"""
        interactions = self.memory.get("interactions", [])
        if len(interactions) < 5:
            return

        # 每 10 次交互触发一次进化
        if len(interactions) % 10 != 0:
            return

        # 统计成功/失败模式（失败按工具+错误类型细分）
        success_patterns = {}
        failure_patterns = {}
        failure_details = []
        for item in interactions[-50:]:
            tool = item["tool"]
            if item["success"]:
                success_patterns[tool] = success_patterns.get(tool, 0) + 1
            else:
                err_type = item.get("error_type") or _classify_error(item.get("detail", ""))
                key = f"{tool}::{err_type}"
                failure_patterns[key] = failure_patterns.get(key, 0) + 1
                failure_details.append({"tool": tool, "error_type": err_type, "detail": item.get("detail", "")})

        # 更新进化数据
        self.evolution["success"] = sorted(success_patterns.items(), key=lambda x: x[1], reverse=True)[:5]
        self.evolution["failure"] = sorted(failure_patterns.items(), key=lambda x: x[1], reverse=True)[:5]

        # 生成进化提示词追加与结构化失败提示
        from fr_cli.agent.master_prompt import SELF_EVOLVE_PROMPT_ZH
        prompt = SELF_EVOLVE_PROMPT_ZH.format(
            success_patterns="\n".join(f"- {k}: {v}次" for k, v in self.evolution["success"]),
            failure_patterns="\n".join(f"- {k}: {v}次" for k, v in self.evolution["failure"]),
        )

        messages = [{"role": "user", "content": prompt}]
        from fr_cli.core.stream import stream_cnt
        raw, _, _, _ = stream_cnt(
            self.state.client, self.state.model_name, messages, self.state.lang,
            custom_prefix="", max_tokens=768, silent=True
        )
        raw = raw.strip()
        if not raw:
            return

        # 解析 LLM 返回的 JSON（兼容无代码块与 Markdown 代码块）
        cleaned = raw
        if cleaned.startswith("```"):
            cleaned = cleaned[cleaned.find("\n") + 1:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:cleaned.rfind("```")]
        cleaned = cleaned.strip()
        try:
            evolve = json.loads(cleaned)
        except Exception:
            # 若 JSON 解析失败，退化为纯文本 prompt_addon
            if len(raw) < 500:
                self.evolution["prompt_addon"] = raw
                _save_json(EVOLUTION_FILE, self.evolution)
            return

        addon = evolve.get("prompt_addon", "").strip()
        if addon and len(addon) < 500:
            self.evolution["prompt_addon"] = addon

        # 合并历史失败提示，保留最近 10 条（去重：同一 tool+error_type 只保留最新）
        existing = {f"{h.get('tool')}::{h.get('error_type')}": h for h in self.evolution.get("failure_hints", [])}
        for h in evolve.get("failure_hints", []):
            if isinstance(h, dict) and h.get("tool") and h.get("error_type"):
                key = f"{h['tool']}::{h['error_type']}"
                existing[key] = h
        self.evolution["failure_hints"] = list(existing.values())[-10:]

        _save_json(EVOLUTION_FILE, self.evolution)

        # 更新进化计数
        self._status_data["evolution_count"] = self._status_data.get("evolution_count", 0) + 1
        _save_json(STATUS_FILE, self._status_data)