"""
选品洞察提炼器 —— MasterAgent 选品经验的"炼丹炉"

从选品历史中提炼爆款规律，输出结构化洞察供 prompt 注入。

工作流（分批-聚合模式，应对 100-1000 条规模）：
  1. 加载：source.load(since) → SelectionRecord 列表
  2. 切批：每 batch_size 条切一刀
  3. 批提炼：每批独立调 LLM，提炼"该批的爆款共性" → batch summary 列表
  4. 聚合：把所有 batch summary 二次喂给 LLM，输出全局洞察
  5. 持久化：save(insights) → ~/.fr_cli/master/insights/
  6. 注入：format_for_prompt(insights) → 给 master_prompt_builder 用

输出 schema（最终洞察）：
  {
    "summary": "一句话总结",
    "categories": [{"name", "hit_rate", "evidence", "key_signals"}],
    "price_bands": [{"range", "verdict", "evidence"}],
    "lifecycle_patterns": [{"pattern", "description"}],
    "seasonal_trends": [{"signal", "evidence"}],
    "key_signals": [str]
  }
"""
import json
import re
from typing import Optional

from fr_cli.agent.insight_source import (
    SelectionHistorySource,
    get_default_source,
)
from fr_cli.agent.insight_storage import save as save_insights


# ---------- Prompt 模板 ----------

_BATCH_PROMPT_ZH = """你是电商选品分析师，正在分析一批商品历史数据。

# 数据（共 {count} 条，按峰值日倒序）
{records_block}

# 你的任务
请提炼这一批数据的"爆款共性"：
1. 哪些品类/子类目表现强势？给出 1-3 个代表品类。
2. 哪些价格带最容易出爆款？给出 1-2 个价格区间和判断依据。
3. 生命周期（从上架到爆的周期）有什么规律？平均多少天？短周期爆款 vs 长周期爆款有何差异？
4. 有没有明显的标签/特征组合（应季/送礼/颜值经济/学生党/高客单 等）？
5. 季节性/时间信号：是否集中在某些月份？

# 输出格式（严格 JSON，不要其他文字）
```json
{{
  "summary": "本批爆款共性一句话总结",
  "categories": [{{"name": "品类", "hit_rate": "高/中/低", "evidence": "支撑证据"}}],
  "price_bands": [{{"range": "区间", "verdict": "判定", "evidence": "依据"}}],
  "lifecycle_patterns": [{{"pattern": "模式", "description": "解释"}}],
  "seasonal_trends": [{{"signal": "信号", "evidence": "依据"}}],
  "key_signals": ["本批最值得记住的 1-3 条信号"]
}}
```"""

_BATCH_PROMPT_EN = """You are an e-commerce product analyst reviewing a batch of historical data.

# Data ({count} records, sorted by peak date desc)
{records_block}

# Your task
Extract the "hit-product commonalities" for this batch:
1. Which categories/subcategories performed strongly? List 1-3.
2. Which price bands most easily produce hits? Give 1-2 ranges + reasoning.
3. Lifecycle patterns (days from launch to peak)? Short-cycle vs long-cycle?
4. Notable tag/feature combinations (seasonal/gift/aesthetic/student/high-AOV)?
5. Seasonality/timing signals: any month concentration?

# Output (strict JSON, no other text)
```json
{{
  "summary": "one-line summary of batch hit patterns",
  "categories": [{{"name": "category", "hit_rate": "high/med/low", "evidence": "..."}}],
  "price_bands": [{{"range": "range", "verdict": "verdict", "evidence": "..."}}],
  "lifecycle_patterns": [{{"pattern": "pattern", "description": "..."}}],
  "seasonal_trends": [{{"signal": "signal", "evidence": "..."}}],
  "key_signals": ["1-3 most memorable signals from this batch"]
}}
```"""


_AGG_PROMPT_ZH = """你是资深电商选品策略师，已有多份"批次分析"结论，请你把它们合成一份全局洞察。

# 各批次结论
{batch_summaries}

# 你的任务
跨批次交叉验证，输出一份"全局爆款规律"洞察：

1. **跨批次稳定的品类热点**：在多份批次中都出现强势的品类
2. **跨批次稳定的价格带**：反复出现爆款的价格区间
3. **生命周期规律**：综合所有批次，最常见的"上架到爆"周期
4. **季节性/时间信号**：综合所有批次，月份/季度层面的规律
5. **关键信号**：3-5 条最值得长期记住的爆款规律

# 输出格式（严格 JSON）
```json
{{
  "summary": "全局爆款规律一句话总结(30字内)",
  "categories": [{{"name": "品类", "hit_rate": "高/中/低", "evidence": "跨批次证据", "key_signals": [str]}}],
  "price_bands": [{{"range": "区间", "verdict": "判定", "evidence": "跨批次依据"}}],
  "lifecycle_patterns": [{{"pattern": "模式", "description": "解释"}}],
  "seasonal_trends": [{{"signal": "信号", "evidence": "依据"}}],
  "key_signals": ["3-5 条核心规律，每条 30 字内"]
}}
```"""

_AGG_PROMPT_EN = """You are a senior e-commerce product strategist with multiple batch analyses; synthesize them into a global insight.

# Batch conclusions
{batch_summaries}

# Task
Cross-validate across batches and output a global hit-product insight.

# Output (strict JSON)
```json
{{
  "summary": "one-line global summary (<=30 chars)",
  "categories": [{{"name": "cat", "hit_rate": "high/med/low", "evidence": "cross-batch", "key_signals": [str]}}],
  "price_bands": [{{"range": "range", "verdict": "verdict", "evidence": "cross-batch"}}],
  "lifecycle_patterns": [{{"pattern": "pattern", "description": "..."}}],
  "seasonal_trends": [{{"signal": "signal", "evidence": "..."}}],
  "key_signals": ["3-5 core rules, each <=30 chars"]
}}
```"""


# ---------- 工具函数 ----------

def _format_records_block(records) -> str:
    """把 SelectionRecord 列表格式化成 LLM 友好的纯文本块"""
    lines = []
    for i, r in enumerate(records, 1):
        tags = ",".join(r.tags) if r.tags else "-"
        lines.append(
            f"{i}. {r.name} | 品类:{r.category} | 价格:¥{r.price} | "
            f"30天销量:{r.sales_30d} | 周期:{r.lifecycle_days}天 | "
            f"峰值:{r.peak_date} | 标签:{tags}"
        )
    return "\n".join(lines)


def _parse_json_response(raw: str) -> Optional[dict]:
    """从 LLM 响应中提取 JSON(容忍 markdown code block)"""
    if not raw:
        return None
    cleaned = raw.strip()
    if "```" in cleaned:
        m = re.search(r"```(?:json)?\s*\n?(.*?)```", cleaned, re.DOTALL)
        if m:
            cleaned = m.group(1).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        # 尝试截取第一个 { 到最后一个 }
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except Exception:
                return None
        return None


def _empty_insights() -> dict:
    """返回空白洞察骨架(供解析失败时回退)"""
    return {
        "summary": "",
        "categories": [],
        "price_bands": [],
        "lifecycle_patterns": [],
        "seasonal_trends": [],
        "key_signals": [],
    }


# ---------- 提炼器 ----------

class InsightExtractor:
    """选品洞察提炼器——分批聚合，应对 100-1000 条规模"""

    def __init__(self, client=None, model_name: Optional[str] = None,
                 lang: str = "zh", source: Optional[SelectionHistorySource] = None,
                 batch_size: int = 30):
        """
        Args:
            client: LLM 客户端(zhipuai / openai 兼容)
            model_name: 使用的模型名
            lang: zh / en
            source: 数据源(默认走 get_default_source)
            batch_size: 每批提炼的记录数
        """
        self.client = client
        self.model_name = model_name
        self.lang = lang
        self.source = source or get_default_source()
        self.batch_size = batch_size

    def extract(self, since: Optional[str] = None,
                on_progress=None) -> dict:
        """执行一次完整提炼流程

        Args:
            since: 起始日期(同 source.load)
            on_progress: 进度回调,签名 on_progress(stage, current, total, info)
                - stage: "load" | "summarize" | "aggregate" | "save"
                - current/total: 当前/总进度(可能为 0)
                - info: 额外信息(如 "第 1/3 批提炼中")

        Returns:
            dict: 洞察结果(同时持久化到磁盘)
        """
        if on_progress:
            on_progress("load", 0, 1, "加载数据源")
        records = self.source.load(since=since)
        if on_progress:
            on_progress("load", 1, 1, f"加载 {len(records)} 条")
        if not records:
            return {
                "skipped": True,
                "reason": "no_records",
                "insights": _empty_insights(),
            }

        # 切批
        batches = self._split_batches(records)
        if not batches:
            return {
                "skipped": True,
                "reason": "batch_split_empty",
                "insights": _empty_insights(),
            }

        # 批提炼(无 client 时只生成 stub,便于离线测试)
        batch_summaries = []
        for i, batch in enumerate(batches, 1):
            if on_progress:
                on_progress("summarize", i, len(batches),
                            f"第 {i}/{len(batches)} 批提炼中")
            summary = self._summarize_batch(batch, batch_index=i, total=len(batches))
            if summary:
                batch_summaries.append(summary)

        if not batch_summaries:
            return {
                "skipped": True,
                "reason": "all_batches_failed",
                "insights": _empty_insights(),
            }

        # 聚合
        if on_progress and len(batch_summaries) > 1:
            on_progress("aggregate", 0, 1, "跨批聚合中")
        if len(batch_summaries) == 1:
            final = batch_summaries[0]
        else:
            final = self._aggregate_summaries(batch_summaries)

        # 持久化
        if on_progress:
            on_progress("save", 0, 1, "保存到磁盘")
        try:
            save_insights(
                final,
                source_name=getattr(self.source, "name", "unknown"),
                record_count=len(records),
                since=since,
            )
        except Exception:
            # 存储失败不影响返回
            pass

        return {
            "skipped": False,
            "source_name": getattr(self.source, "name", "unknown"),
            "record_count": len(records),
            "batch_count": len(batches),
            "insights": final,
        }

    def format_for_prompt(self, insights: dict, max_chars: int = 2000) -> str:
        """把洞察格式化为可注入 system prompt 的 Markdown 段落

        Args:
            insights: 洞察 dict(可来自 load_latest()["insights"])
            max_chars: 最大字符数(防止 prompt 撑爆)

        Returns:
            Markdown 字符串;若 insights 为空则返回空字符串
        """
        if not insights or not isinstance(insights, dict):
            return ""
        lines = ["[选品经验]"]
        summary = (insights.get("summary") or "").strip()
        if summary:
            lines.append(f"**核心规律**: {summary}")

        categories = insights.get("categories") or []
        if categories:
            lines.append("\n**强势品类**:")
            for c in categories[:5]:
                if not isinstance(c, dict):
                    continue
                name = c.get("name", "?")
                hr = c.get("hit_rate", "")
                ev = c.get("evidence", "")
                ks = c.get("key_signals") or []
                line = f"- {name}({hr})"
                if ev:
                    line += f" — {ev}"
                if ks:
                    line += f" | 信号: {', '.join(str(x) for x in ks[:3])}"
                lines.append(line)

        price_bands = insights.get("price_bands") or []
        if price_bands:
            lines.append("\n**价格带规律**:")
            for p in price_bands[:4]:
                if not isinstance(p, dict):
                    continue
                lines.append(f"- {p.get('range', '?')}: {p.get('verdict', '')} ({p.get('evidence', '')})")

        lc = insights.get("lifecycle_patterns") or []
        if lc:
            lines.append("\n**生命周期**:")
            for x in lc[:3]:
                if not isinstance(x, dict):
                    continue
                lines.append(f"- {x.get('pattern', '?')}: {x.get('description', '')}")

        st = insights.get("seasonal_trends") or []
        if st:
            lines.append("\n**季节/时间信号**:")
            for x in st[:3]:
                if not isinstance(x, dict):
                    continue
                lines.append(f"- {x.get('signal', '?')}: {x.get('evidence', '')}")

        ks = insights.get("key_signals") or []
        if ks:
            lines.append("\n**关键信号**:")
            for s in ks[:5]:
                lines.append(f"- {s}")

        text = "\n".join(lines)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n...(已截断)"
        return text

    # ---------- 内部方法 ----------

    def _split_batches(self, records) -> list:
        if self.batch_size <= 0:
            return [records]
        return [records[i:i + self.batch_size] for i in range(0, len(records), self.batch_size)]

    def _call_llm(self, prompt: str) -> Optional[str]:
        """调用 LLM(封装 stream_cnt)"""
        if not self.client or not self.model_name:
            return None
        try:
            from fr_cli.core.stream import stream_cnt
            messages = [{"role": "user", "content": prompt}]
            raw, _, _, _ = stream_cnt(
                self.client, self.model_name, messages, self.lang,
                custom_prefix="", max_tokens=2048, silent=True,
            )
            return raw
        except Exception:
            return None

    def _summarize_batch(self, batch, batch_index: int, total: int) -> Optional[dict]:
        """提炼单批"""
        block = _format_records_block(batch)
        template = _BATCH_PROMPT_ZH if self.lang == "zh" else _BATCH_PROMPT_EN
        prompt = template.format(count=len(batch), records_block=block)
        raw = self._call_llm(prompt)
        if not raw:
            return None
        return _parse_json_response(raw)

    def _aggregate_summaries(self, summaries: list) -> dict:
        """聚合多批提炼结果"""
        # 把每个 summary 渲染成文本块
        blocks = []
        for i, s in enumerate(summaries, 1):
            blocks.append(f"--- 批次 {i} ---\n{json.dumps(s, ensure_ascii=False, indent=2)}")
        template = _AGG_PROMPT_ZH if self.lang == "zh" else _AGG_PROMPT_EN
        prompt = template.format(batch_summaries="\n\n".join(blocks))
        raw = self._call_llm(prompt)
        if not raw:
            # 聚合失败时回退到"取第一个 summary"
            return summaries[0] if summaries else _empty_insights()
        parsed = _parse_json_response(raw)
        return parsed or _empty_insights()


__all__ = ["InsightExtractor"]
