"""
Token 与费用统计持久化 —— 记录每次 LLM 调用的用量，支持按天汇总。

存储位置：~/.fr_cli/usage.json
权限：0o600
"""
import time
from pathlib import Path

from fr_cli.conf.paths import USAGE_FILE
from fr_cli.core.store import JsonStore


class UsageTracker:
    """LLM 调用用量追踪器 —— 线程安全、自动持久化"""

    def __init__(self, path=None, cfg=None):
        self.path = Path(path) if path else USAGE_FILE
        self.cfg = cfg or {}
        self._store = JsonStore(self.path, default=list)
        self._records = self._store.read()
        if not isinstance(self._records, list):
            self._records = []

    def _save(self):
        self._store.write(self._records)

    def _estimate_cost(self, provider, model, prompt_tokens, completion_tokens):
        """根据用户配置的价格表估算费用（未配置返回 0.0）。"""
        prices = self.cfg.get("usage_prices", {})
        provider_prices = prices.get(provider or "")
        if not provider_prices:
            return 0.0
        # 支持按 provider 统一或按 model 单独配置
        model_prices = provider_prices.get(model or "") if isinstance(provider_prices, dict) else None
        if model_prices is None and isinstance(provider_prices, dict) and "prompt" in provider_prices:
            model_prices = provider_prices
        if not isinstance(model_prices, dict):
            return 0.0
        prompt_price = float(model_prices.get("prompt", 0))
        completion_price = float(model_prices.get("completion", 0))
        # 价格单位为：每千 tokens 元
        return (prompt_tokens * prompt_price + completion_tokens * completion_price) / 1000.0

    def record(self, provider, model, prompt_tokens, completion_tokens, total_tokens=None, cost=None):
        """记录一次 LLM 调用用量"""
        prompt_tokens = int(prompt_tokens or 0)
        completion_tokens = int(completion_tokens or 0)
        if total_tokens is None:
            total_tokens = prompt_tokens + completion_tokens
        else:
            total_tokens = int(total_tokens)
        if cost is None:
            cost = self._estimate_cost(provider, model, prompt_tokens, completion_tokens)

        record = {
            "timestamp": time.time(),
            "provider": provider or "unknown",
            "model": model or "unknown",
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost": float(cost),
        }
        self._records.append(record)
        # 限制内存中保留数量，避免文件无限增长（保留最近 10 万条）
        if len(self._records) > 100_000:
            self._records = self._records[-100_000:]
        self._save()

    def summary(self, days=30):
        """汇总最近 N 天的用量"""
        cutoff = time.time() - days * 86400
        recent = [r for r in self._records if r.get("timestamp", 0) >= cutoff]
        return {
            "days": days,
            "calls": len(recent),
            "prompt_tokens": sum(r.get("prompt_tokens", 0) for r in recent),
            "completion_tokens": sum(r.get("completion_tokens", 0) for r in recent),
            "total_tokens": sum(r.get("total_tokens", 0) for r in recent),
            "estimated_cost": sum(r.get("cost", 0.0) for r in recent),
        }

    def reset(self):
        """清空所有记录"""
        self._records = []
        self._save()
