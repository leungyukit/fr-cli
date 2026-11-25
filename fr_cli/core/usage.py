"""
Token 与费用统计持久化 —— 记录每次 LLM 调用的用量，支持按天汇总。

存储位置：~/.fr_cli/usage.json
权限：0o600

v3.0+:可订阅 v3 EventBus,自动从 llm.responded 事件中提取 usage 并记录。
"""
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from fr_cli.conf.paths import USAGE_FILE
from fr_cli.core.store import JsonStore


def format_token_usage(input_tokens: int = 0, output_tokens: int = 0,
                       total_tokens: int = 0, limit: int = 0,
                       with_pct: bool = False) -> str:
    """统一的 token 显示口径 —— **所有显示 token 的地方都必须走这里**。

    v2.8.7(P2-3)：此前 token 在**三处**显示，各写各的：

    - 状态栏：``100/200/300``（裸数字，无箭头、无占比）
    - 回答末尾：``↓100 ↑200 Σ300 (12%)``
    - 状态栏另一分支：``tokens_used/limit`` —— 而 ``tokens_used``
      **全仓无人写入**，那个分支恒不触发（与当年的 ``tool_name`` 同一类死代码）

    三个数三个格式，用户没法判断"到底是多少"。现在统一成同一个函数：
    同样的三个数、同样的箭头语义、同样的占比分母（``limit``）。

    Args:
        input_tokens: 输入 token
        output_tokens: 输出 token
        total_tokens: 合计 token（为 0 时用 input+output 兜底）
        limit: token 上限（用于算占比）；0 表示不显示占比
        with_pct: 是否附带占比

    Returns:
        如 ``↓100 ↑200 Σ300`` 或 ``↓100 ↑200 Σ300 (12%)``
    """
    total = total_tokens or (int(input_tokens or 0) + int(output_tokens or 0))
    text = f"↓{int(input_tokens or 0)} ↑{int(output_tokens or 0)} Σ{int(total)}"
    if with_pct and limit:
        text += f" ({total / limit * 100:.0f}%)"
    return text


class UsageTracker:
    """LLM 调用用量追踪器 —— 线程安全、自动持久化

    v2.8.7 行为变更：
    - 真正线程安全。此前 docstring 自称线程安全，但全文件无 ``import threading``，
      ``record()`` 里 append 与 ``_save()`` 之间没有临界区 —— 并发调用会丢记录。
    - 落盘改为**批量延迟写**：原先每次 record 都全量重写整个 JSON
      （上限 10 万条），写放大严重。现在默认最多 5 秒落盘一次，
      ``flush()`` 可强制落盘，进程退出前也会 flush。
    """

    #: 批量落盘的最小间隔（秒）
    FLUSH_INTERVAL = 5.0
    #: 记录数不超过该值时立即落盘（保持既有行为：跨实例立即可读）
    IMMEDIATE_FLUSH_MAX = 1000

    def __init__(self, path=None, cfg=None):
        self.path = Path(path) if path else USAGE_FILE
        self.cfg = cfg or {}
        self._store = JsonStore(self.path, default=list)
        self._lock = threading.RLock()
        self._records = self._store.read()
        if not isinstance(self._records, list):
            self._records = []
        self._bus_listener: Optional[Callable] = None  # 防止 GC
        self._bus = None
        self._dirty = False
        self._last_save = time.time()

    def _save(self):
        """落盘（调用方需持有锁，或仅在构造期无并发时调用）。"""
        with self._lock:
            self._store.write(self._records)
            self._dirty = False
            self._last_save = time.time()

    def flush(self):
        """强制把内存中的记录落盘。"""
        if self._dirty:
            self._save()

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
        with self._lock:
            self._records.append(record)
            # 限制内存中保留数量，避免文件无限增长（保留最近 10 万条）
            if len(self._records) > 100_000:
                self._records = self._records[-100_000:]
            self._dirty = True
            # 落盘策略：小数据量立即落盘（保持既有行为 —— 新建 tracker 立即能读到记录）；
            # 记录数变多后按 FLUSH_INTERVAL 批量落盘，避免每次调用都全量重写整个文件。
            if (len(self._records) <= self.IMMEDIATE_FLUSH_MAX
                    or time.time() - self._last_save >= self.FLUSH_INTERVAL):
                self._save()

    def summary(self, days=30):
        """汇总最近 N 天的用量"""
        cutoff = time.time() - days * 86400
        with self._lock:
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
        with self._lock:
            self._records = []
            self._dirty = True
            self._save()

    # ---------------- v3 EventBus 集成 ----------------

    def install_listener(self, bus=None, event_type: str = "llm.responded"):
        """订阅 v3 EventBus,自动从 llm.responded 事件记录用量

        Args:
            bus: v3 EventBus 实例,默认全局单例
            event_type: 监听的事件类型,默认 llm.responded

        Returns:
            True 成功安装, False 失败(已安装 / 缺依赖 / 事件格式不对)

        Note:
            - 每个 tracker 实例只安装一次,重复调用直接返回 True
            - 自动从 event.data 中提取 provider / model / usage(prompt_tokens / completion_tokens / total_tokens)
            - 不影响现有的 record() 显式调用(可叠加)
        """
        if self._bus_listener is not None:
            return True  # 已经安装

        try:
            from fr_cli.v3.core.events import EventBus
        except Exception:
            return False

        if bus is None:
            bus = EventBus.instance()
        self._bus = bus

        def _on_llm_responded(event):
            """监听器:从 llm.responded 事件提取 usage 并 record"""
            try:
                data = event.data or {}
                usage = data.get("usage") or {}
                if not usage:
                    return  # 没 usage 数据,跳过

                # provider / model 从 data 或 usage 中取
                provider = (data.get("provider")
                            or usage.get("provider")
                            or getattr(self, "_current_provider", None)
                            or "unknown")
                model = (data.get("model")
                         or usage.get("model")
                         or getattr(self, "_current_model", None)
                         or "unknown")

                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                total_tokens = usage.get("total_tokens")

                self.record(
                    provider=provider,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                )
            except Exception:
                # 监听器异常不影响主流程
                pass

        try:
            self._bus_listener = bus.on(event_type, _on_llm_responded, priority=0)
            return True
        except Exception:
            return False

    def uninstall_listener(self):
        """解除 v3 EventBus 监听"""
        if self._bus_listener is None or self._bus is None:
            return False
        try:
            self._bus.off("llm.responded", self._bus_listener)
            self._bus_listener = None
            return True
        except Exception:
            return False
