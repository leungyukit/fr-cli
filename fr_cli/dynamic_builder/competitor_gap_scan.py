"""
竞品监控 能力缺口扫描器

让 fr-cli 主动发现"竞品监控"领域的能力缺口,而不是等用户提需求。

工作流：
  1. 加载能力模型 (fr_cli/dynamic_builder/capabilities/competitor_monitor.yaml)
  2. 拿到当前所有可用工具 (从 ToolRegistry)
  3. 遍历每个子能力,调 CapabilityGapAnalyzer.analyze() 判断覆盖
  4. 汇总缺口 + 持久化报告 + 推到 review queue (可选)

报告 schema:
  {
    "domain": "competitor_monitor",
    "title": "竞品监控",
    "version": 1,
    "scanned": 8,                    # 扫描的能力数
    "gap_count": 3,                  # 缺口数
    "tools_count": 50,               # 当前工具总数
    "timestamp": "ISO",
    "gaps": [
      {
        "name": "competitor_price_monitor",
        "description": "...",
        "priority": "high",
        "key_signals": [...],
        "example_usage": "...",
        "gap": true,
        "confidence": 0.85,
        "suggested_tool_name": "competitor_price_monitor",
        "reasoning": "..."
      }
    ]
  }

存储: ~/.fr_cli/dynamic_builder/gap_reports/competitor_monitor/
  latest.json + history/YYYY-MM-DD_HHMMSS.json
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from fr_cli.conf import paths as _paths


# ---------- 路径(用函数/lambda,便于测试 monkeypatch 隔离) ----------

def _reports_dir():
    return _paths.ROOT / "dynamic_builder" / "gap_reports" / "competitor_monitor"


def _latest_file():
    return _reports_dir() / "latest.json"


def _history_dir():
    return _reports_dir() / "history"


# 默认能力模型路径(fr-cli 内置)
DEFAULT_MODEL_PATH = (
    Path(__file__).parent / "capabilities" / "competitor_monitor.yaml"
)


# ---------- 加载 ----------

def load_model(path: Optional[str] = None) -> dict:
    """加载能力模型 YAML

    Args:
        path: 自定义路径;为 None 时使用内置默认

    Returns:
        dict: 模型内容

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 格式错误
    """
    p = Path(path) if path else DEFAULT_MODEL_PATH
    if not p.exists():
        raise FileNotFoundError(f"能力模型文件不存在: {p}")
    with open(p, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"能力模型格式错误,期望 dict,得到 {type(data)}")
    if "capabilities" not in data or not isinstance(data["capabilities"], list):
        raise ValueError("能力模型缺少 capabilities 列表")
    return data


# ---------- 扫描器 ----------

class CompetitorGapScanner:
    """竞品监控能力缺口扫描器"""

    def __init__(self, model_path: Optional[str] = None, state=None, lang: str = "zh"):
        """
        Args:
            model_path: 能力模型路径(默认内置)
            state: AppState,用于 LLM 二次判断(state.client / state.model_name)
            lang: zh / en
        """
        self.model_path = model_path
        self.state = state
        self.lang = lang
        self._model_cache = None

    @property
    def model(self) -> dict:
        if self._model_cache is None:
            self._model_cache = load_model(self.model_path)
        return self._model_cache

    def _get_tools(self) -> list:
        """拿到当前所有可用工具(去 dataclass 化,只保留 name/description/aliases/triggers)"""
        try:
            from fr_cli.command.registry import get_registry
            reg = get_registry()
        except Exception:
            return []
        out = []
        for t in reg.get_tools():
            out.append({
                "name": t.get("name", ""),
                "description": t.get("description", ""),
                "aliases": list(t.get("aliases", []) or []),
                "triggers": list(t.get("triggers", []) or []),
            })
        return out

    def scan(self, save_report: bool = True) -> dict:
        """执行一次完整扫描

        Args:
            save_report: 是否持久化报告(默认 True)

        Returns:
            报告 dict
        """
        # 延迟 import 避免循环依赖
        from fr_cli.dynamic_builder.gap_analyzer import analyze_gap

        model = self.model
        capabilities = model.get("capabilities", [])
        tools = self._get_tools()

        gaps = []
        for cap in capabilities:
            if not isinstance(cap, dict) or not cap.get("name"):
                continue
            # 拼接需求描述,给 LLM 足够上下文
            requirement = self._build_requirement(cap)
            try:
                analysis = analyze_gap(
                    requirement=requirement,
                    tools=tools,
                    state=self.state,
                    lang=self.lang,
                )
            except Exception as e:
                analysis = {
                    "gap": True,
                    "confidence": 0.0,
                    "suggested_tool_name": cap.get("name", ""),
                    "reasoning": f"分析器异常: {e}",
                }

            gap_entry = {
                "name": cap.get("name", ""),
                "description": cap.get("description", ""),
                "priority": cap.get("priority", "medium"),
                "key_signals": list(cap.get("key_signals", []) or []),
                "example_usage": cap.get("example_usage", ""),
                "gap": analysis.get("gap", True),
                "confidence": float(analysis.get("confidence", 0.0)),
                "suggested_tool_name": analysis.get("suggested_tool_name", "")
                                       or cap.get("name", ""),
                "reasoning": analysis.get("reasoning", ""),
            }
            # 只保留有缺口的项(便于输出精简)
            if gap_entry["gap"]:
                gaps.append(gap_entry)

        # 按优先级排序(high > medium > low)
        priority_order = {"high": 0, "medium": 1, "low": 2}
        gaps.sort(key=lambda g: (priority_order.get(g["priority"], 9),
                                  -g["confidence"]))

        report = {
            "domain": model.get("domain", "unknown"),
            "title": model.get("title", ""),
            "version": model.get("version", 1),
            "scanned": len(capabilities),
            "gap_count": len(gaps),
            "tools_count": len(tools),
            "timestamp": datetime.now().isoformat(),
            "gaps": gaps,
        }

        if save_report:
            try:
                self._save_report(report)
            except Exception:
                # 存储失败不影响返回
                pass

        return report

    def _build_requirement(self, cap: dict) -> str:
        """把能力定义拼成给 gap_analyzer 的需求描述"""
        parts = [f"能力名称:{cap.get('name', '')}"]
        if cap.get("description"):
            parts.append(f"描述:{cap['description']}")
        signals = cap.get("key_signals") or []
        if signals:
            parts.append(f"相关关键词:{' / '.join(signals)}")
        if cap.get("example_usage"):
            parts.append(f"典型场景:{cap['example_usage']}")
        return "\n".join(parts)

    def _save_report(self, report: dict):
        """持久化报告到 ~/.fr_cli/dynamic_builder/gap_reports/competitor_monitor/"""
        d = _reports_dir()
        d.mkdir(parents=True, exist_ok=True)
        hd = _history_dir()
        hd.mkdir(parents=True, exist_ok=True)

        latest = _latest_file()
        latest.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        (hd / f"{stamp}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


# ---------- 便捷函数 ----------

def load_latest_report() -> Optional[dict]:
    """加载最新一次扫描报告;不存在返回 None"""
    p = _latest_file()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def format_report_text(report: dict) -> str:
    """把报告格式化为可读文本(供命令打印)"""
    if not report:
        return "(无报告)"
    lines = []
    title = report.get("title") or report.get("domain") or "能力扫描"
    lines.append(f"📊 {title} 能力扫描")
    if report.get("timestamp"):
        lines.append(f"   扫描时间: {report['timestamp'][:19]}")
    lines.append(
        f"   已扫: {report.get('scanned', 0)} | "
        f"缺口: {report.get('gap_count', 0)} | "
        f"现有工具: {report.get('tools_count', 0)}"
    )
    lines.append("")

    gaps = report.get("gaps") or []
    if not gaps:
        lines.append("✅ 当前工具已覆盖该领域所有能力,无需补全。")
        return "\n".join(lines)

    # 兜底排序:高优先级在前,同优先级按置信度降序
    priority_order = {"high": 0, "medium": 1, "low": 2}
    gaps = sorted(
        gaps,
        key=lambda g: (priority_order.get(g.get("priority", "medium"), 9),
                       -float(g.get("confidence", 0.0))),
    )

    lines.append(f"⚠️  发现 {len(gaps)} 项能力缺口:\n")
    for i, g in enumerate(gaps, 1):
        priority_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
            g.get("priority", "medium"), "⚪"
        )
        lines.append(
            f"  {i}. {priority_emoji} {g.get('name', '?')} "
            f"[{g.get('priority', 'medium')}] "
            f"(置信度 {g.get('confidence', 0):.2f})"
        )
        if g.get("description"):
            lines.append(f"     {g['description']}")
        if g.get("reasoning"):
            lines.append(f"     理由: {g['reasoning'][:120]}")
        if g.get("key_signals"):
            sigs = " / ".join(g["key_signals"][:5])
            lines.append(f"     关键词: {sigs}")
        lines.append("")

    return "\n".join(lines)


__all__ = [
    "CompetitorGapScanner",
    "load_model",
    "load_latest_report",
    "format_report_text",
    "DEFAULT_MODEL_PATH",
]
