"""
能力缺口分析器

判断用户需求是否已被现有工具覆盖；若未被覆盖，则给出构建新工具的建议。
"""
import json
import re
from typing import Dict, List, Any

from fr_cli.core.stream import stream_cnt


def _tokenize(text: str) -> set:
    """简单分词：保留中文字符与英文单词"""
    text = text.lower()
    tokens = set(re.findall(r"[\u4e00-\u9fa5]", text))
    tokens.update(re.findall(r"[a-z0-9_]+", text))
    return tokens


def _keyword_match_score(requirement: str, tool: Dict[str, Any]) -> float:
    """计算需求与工具描述的关键词重叠得分。"""
    req_tokens = _tokenize(requirement)
    if not req_tokens:
        return 0.0

    tool_text = " ".join([
        tool.get("name", ""),
        tool.get("description", ""),
        " ".join(tool.get("aliases", [])),
        " ".join(tool.get("triggers", [])),
    ])
    tool_tokens = _tokenize(tool_text)
    overlap = req_tokens & tool_tokens
    return len(overlap) / len(req_tokens)


GAP_ANALYZER_PROMPT_ZH = """你是 fr-cli 的能力缺口分析专家。请判断以下需求是否已被当前工具覆盖。

用户需求：{requirement}

当前可用工具（仅名称与描述）：
{tools_summary}

请输出严格 JSON（不要 Markdown 代码块）：
{{
  "gap": true 或 false,
  "confidence": 0-1 之间的数字,
  "suggested_tool_name": "若存在缺口，建议构建的工具名（合法 Python 标识符）",
  "reasoning": "判断理由（不超过100字）"
}}

注意：若现有工具组合即可满足需求，gap 应为 false。"""


def _tools_summary(tools: List[Dict[str, Any]], limit: int = 60) -> str:
    lines = []
    for t in tools[:limit]:
        lines.append(f"- {t.get('name')}: {t.get('description', '')}")
    return "\n".join(lines)


class CapabilityGapAnalyzer:
    """分析用户需求与现有工具集之间的差距。"""

    def __init__(self, keyword_threshold: float = 0.3):
        self.keyword_threshold = keyword_threshold

    def analyze(
        self,
        requirement: str,
        tools: List[Dict[str, Any]],
        state=None,
        lang: str = "zh",
    ) -> Dict[str, Any]:
        """
        返回缺口分析结果字典：
        {
            "gap": bool,
            "confidence": float,
            "suggested_tool_name": str,
            "reasoning": str,
        }
        """
        requirement = (requirement or "").strip()
        if not requirement:
            return {"gap": False, "confidence": 1.0, "reasoning": "需求为空"}

        # 初筛：关键词命中即认为已覆盖
        best_score = 0.0
        best_tool = None
        for tool in tools:
            score = _keyword_match_score(requirement, tool)
            if score > best_score:
                best_score = score
                best_tool = tool
        if best_score >= self.keyword_threshold:
            return {
                "gap": False,
                "confidence": best_score,
                "suggested_tool_name": "",
                "reasoning": f"关键词命中现有工具 [{best_tool.get('name')}]，可直接使用。",
            }

        # 未命中：使用 LLM 做二次判断
        if state is None or not getattr(state, "model_name", None):
            return {
                "gap": True,
                "confidence": 0.5,
                "suggested_tool_name": "",
                "reasoning": "无 LLM 上下文(state 或 model_name 缺失),按保守策略标记为缺口。"
                              "如需精确判断,请配置 API Key 后重跑。",
            }

        prompt = GAP_ANALYZER_PROMPT_ZH.format(
            requirement=requirement,
            tools_summary=_tools_summary(tools),
        )
        messages = [{"role": "user", "content": prompt}]
        try:
            raw, _, _, _ = stream_cnt(
                state.client, state.model_name, messages, lang,
                custom_prefix="", max_tokens=512, silent=True,
            )
        except Exception as e:
            return {
                "gap": True,
                "confidence": 0.5,
                "suggested_tool_name": "",
                "reasoning": f"LLM 分析失败: {e}",
            }

        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned[cleaned.find("\n") + 1:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:cleaned.rfind("```")]
        cleaned = cleaned.strip()
        try:
            result = json.loads(cleaned)
            if not isinstance(result, dict):
                raise ValueError("not a dict")
            return {
                "gap": bool(result.get("gap", True)),
                "confidence": float(result.get("confidence", 0.5)),
                "suggested_tool_name": result.get("suggested_tool_name", ""),
                "reasoning": result.get("reasoning", ""),
            }
        except Exception:
            # 解析失败时保守认为存在缺口
            # 常见情况:API Key 未配置 / Key 错误 / 余额不足 —— 给可操作提示
            raw_preview = (raw or "")[:100]
            auth_hint_keywords = ("api 密钥", "api key", "apikey", "auth",
                                  "unauthorized", "401", "认证失败", "invalid key")
            if any(kw in (raw or "").lower() for kw in auth_hint_keywords):
                reasoning = (
                    f"LLM 调用失败(疑似 API Key 未配置或无效): {raw_preview}"
                    " — 请用 /key <your-key> 配置有效密钥后重跑。"
                )
            else:
                reasoning = f"LLM 输出解析失败，原始输出: {raw_preview}"
            return {
                "gap": True,
                "confidence": 0.5,
                "suggested_tool_name": "",
                "reasoning": reasoning,
            }


def analyze_gap(requirement: str, tools: List[Dict[str, Any]], state=None, lang: str = "zh") -> Dict[str, Any]:
    """便捷函数：分析单一需求的能力缺口。"""
    analyzer = CapabilityGapAnalyzer()
    return analyzer.analyze(requirement, tools, state=state, lang=lang)
