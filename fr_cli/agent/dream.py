"""
MasterAgent Dream 梦境模块 —— 凡人元神入定

参考 OpenClaw/HermesAgent 的"梦境整理"机制：
  - 用户空闲时（默认 30 分钟无新交互），主动触发
  - LLM 整理最近 N 条交互记忆 → 提炼关键经验/偏好/技能
  - 归档到长期记忆（~/.fr_cli/master/dream_log.md），供后续检索

触发方式：
  1. 手动：`/dream` 命令
  2. 自动：MasterAgent 检测到空闲超时后调用
  3. 定时：Hermes 后台任务可设置每日凌晨自动 Dream

记忆层级：
  - 日志层：~/.fr_cli/master/memory.json（短期，按时间戳）
  - 长期层：~/.fr_cli/master/dream_log.md（提炼后的人类可读）
  - 长期层 JSON：~/.fr_cli/master/dream_index.json（按主题索引，便于检索）
"""
import json
import re
import threading
from datetime import datetime

from fr_cli.conf import paths as _paths


# Dream 日志文件
DREAM_LOG_FILE = lambda: _paths.MASTER_DIR / "dream_log.md"  # noqa
DREAM_INDEX_FILE = lambda: _paths.MASTER_DIR / "dream_index.json"  # noqa


def _ensure_master_dir():
    _paths.MASTER_DIR.mkdir(parents=True, exist_ok=True)


def _load_dream_index():
    """加载长期记忆索引"""
    _ensure_master_dir()
    idx_path = DREAM_INDEX_FILE()
    if not idx_path.exists():
        return {"themes": {}, "last_dream": None, "total_dreams": 0}
    try:
        return json.loads(idx_path.read_text(encoding="utf-8"))
    except Exception:
        return {"themes": {}, "last_dream": None, "total_dreams": 0}


def _save_dream_index(idx):
    _ensure_master_dir()
    DREAM_INDEX_FILE().write_text(
        json.dumps(idx, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _append_dream_log(markdown_section):
    """追加 Markdown 章节到 dream_log.md"""
    _ensure_master_dir()
    log_path = DREAM_LOG_FILE()
    if not log_path.exists():
        log_path.write_text(
            "# 凡人元神 · 梦境档案\n\n"
            "> 自动整理 MasterAgent 的长期记忆。每节梦境对应一次整理。\n\n",
            encoding="utf-8",
        )
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(markdown_section)


def _read_recent_interactions(limit=20):
    """从 memory.json 读取最近 N 条交互"""
    memory_path = _paths.MASTER_DIR / "memory.json"
    if not memory_path.exists():
        return []
    try:
        memory = json.loads(memory_path.read_text(encoding="utf-8"))
        return memory.get("interactions", [])[-limit:]
    except Exception:
        return []


def _summarize_interactions_for_prompt(interactions):
    """把交互记录格式化成 LLM 友好的摘要"""
    if not interactions:
        return "（无近期交互记录）"
    lines = []
    for item in interactions:
        time = item.get("time", "?")[:16]
        status = "✅" if item.get("success") else "❌"
        err = f" ({item.get('error_type')})" if not item.get("success") and item.get("error_type") else ""
        tool = item.get("tool", "?")
        inp = (item.get("input") or "")[:60]
        detail = (item.get("detail") or "")[:60]
        lines.append(f"{status} [{time}] {tool}{err} | 输入: {inp} | 结果: {detail}")
    return "\n".join(lines)


DREAM_PROMPT_ZH = """你是凡人元神的「梦中书」，负责在 MasterAgent 空闲时整理记忆。

# 近期交互（按时间顺序）
{interactions}

# 你的任务
1. **提炼经验**：找出反复出现的主题（用户偏好、常用工具、失败模式）
2. **识别偏好**：从输入中提取用户表达过的偏好/习惯/禁区
3. **归纳技能**：哪些工具组合用得好，可以作为最佳实践
4. **改进建议**：哪些失败应该避免，下次怎么改进

# 输出格式（严格 JSON）
```json
{{
  "themes": [
    {{"name": "主题名", "description": "一句话说明", "frequency": "高频/中频/低频"}},
    ...
  ],
  "preferences": ["用户偏好1", "用户偏好2"],
  "best_practices": ["最佳实践1", "最佳实践2"],
  "improvements": ["改进建议1", "改进建议2"],
  "summary": "本次梦境一句话总结（30字内）"
}}
```

只输出 JSON，不要其他文字。"""


class DreamEngine:
    """梦境整理引擎"""

    def __init__(self, client=None, model_name=None, lang="zh"):
        self.client = client
        self.model_name = model_name
        self.lang = lang
        self._lock = threading.Lock()
        self._last_interaction_at = None
        self._idle_thread = None

    def start_idle_watcher(self, idle_minutes=30, on_dream=None):
        """启动空闲监听线程：超过 idle_minutes 无交互时触发 Dream

        Args:
            idle_minutes: 空闲分钟数（默认 30）
            on_dream: Dream 完成后的回调（可选），参数为 dream_result dict
        """
        if self._idle_thread and self._idle_thread.is_alive():
            return  # 已在运行

        def _watcher():
            self._last_interaction_at = datetime.now()
            while True:
                import time
                time.sleep(60)  # 每分钟检查一次
                if self._last_interaction_at is None:
                    continue
                elapsed = (datetime.now() - self._last_interaction_at).total_seconds() / 60
                if elapsed >= idle_minutes:
                    try:
                        result = self.dream_now()
                        if on_dream:
                            on_dream(result)
                    except Exception:
                        pass
                    # Dream 后重置计时
                    self._last_interaction_at = datetime.now()

        self._idle_thread = threading.Thread(target=_watcher, daemon=True)
        self._idle_thread.start()

    def notify_interaction(self):
        """MasterAgent 在每次交互后调用，重置空闲计时"""
        self._last_interaction_at = datetime.now()

    def dream_now(self, lookback=20):
        """立即执行一次 Dream 整理（手动 / 自动都走这里）

        Returns:
            dict: 梦境结果，结构与 DREAM_PROMPT 中的 JSON 一致
        """
        with self._lock:
            interactions = _read_recent_interactions(limit=lookback)
            if len(interactions) < 3:
                return {"skipped": True, "reason": "interactions 太少，无需整理"}

            # 1. 调用 LLM 整理
            prompt = DREAM_PROMPT_ZH.format(
                interactions=_summarize_interactions_for_prompt(interactions)
            )
            messages = [{"role": "user", "content": prompt}]
            try:
                from fr_cli.core.stream import stream_cnt
                raw, _, _, _ = stream_cnt(
                    self.client, self.model_name, messages, self.lang,
                    custom_prefix="", max_tokens=1024, silent=True,
                )
            except Exception as e:
                return {"skipped": True, "reason": f"LLM 调用失败: {e}"}

            raw = raw.strip()
            if not raw:
                return {"skipped": True, "reason": "LLM 无响应"}

            # 2. 解析 JSON（容忍 Markdown 代码块）
            cleaned = raw
            if "```" in cleaned:
                m = re.search(r"```(?:json)?\s*\n?(.*?)```", cleaned, re.DOTALL)
                if m:
                    cleaned = m.group(1).strip()
            try:
                dream_data = json.loads(cleaned)
            except Exception:
                return {"skipped": True, "reason": "JSON 解析失败"}

            # 3. 写入长期记忆索引
            idx = _load_dream_index()
            now = datetime.now().isoformat()
            for theme in dream_data.get("themes", []):
                if not isinstance(theme, dict):
                    continue
                name = theme.get("name", "").strip()
                if not name:
                    continue
                t = idx["themes"].setdefault(name, {"count": 0, "last_seen": None, "descriptions": []})
                t["count"] += 1
                t["last_seen"] = now
                desc = theme.get("description", "")
                if desc and desc not in t["descriptions"]:
                    t["descriptions"].append(desc)
                    t["descriptions"] = t["descriptions"][-5:]  # 最多保留 5 条
            idx["last_dream"] = now
            idx["total_dreams"] = idx.get("total_dreams", 0) + 1
            _save_dream_index(idx)

            # 4. 写入 Markdown 档案
            md = self._render_dream_markdown(dream_data, interactions, now)
            _append_dream_log(md)

            return {"skipped": False, "data": dream_data, "saved_at": now}

    def _render_dream_markdown(self, dream_data, interactions, timestamp):
        """把梦境结果格式化成 Markdown 章节"""
        lines = [f"\n## 🌙 梦境 #{datetime.fromisoformat(timestamp).strftime('%Y-%m-%d %H:%M')}"]
        lines.append(f"\n> 来源：{len(interactions)} 条近期交互\n")

        summary = dream_data.get("summary", "").strip()
        if summary:
            lines.append(f"\n**摘要**: {summary}\n")

        themes = dream_data.get("themes", [])
        if themes:
            lines.append("\n### 主题提炼\n")
            for t in themes:
                if isinstance(t, dict):
                    freq = t.get("frequency", "")
                    name = t.get("name", "")
                    desc = t.get("description", "")
                    lines.append(f"- **{name}** ({freq}): {desc}")

        prefs = dream_data.get("preferences", [])
        if prefs:
            lines.append("\n### 用户偏好\n")
            for p in prefs:
                lines.append(f"- {p}")

        bp = dream_data.get("best_practices", [])
        if bp:
            lines.append("\n### 最佳实践\n")
            for b in bp:
                lines.append(f"- {b}")

        imp = dream_data.get("improvements", [])
        if imp:
            lines.append("\n### 改进建议\n")
            for i in imp:
                lines.append(f"- {i}")

        lines.append("\n---\n")
        return "\n".join(lines)


# 简易查询接口
def search_dream_memory(query, limit=5):
    """在长期梦境索引中搜索相关主题

    Returns:
        list[dict]: 匹配的主题摘要列表
    """
    idx = _load_dream_index()
    q = query.lower()
    results = []
    for name, t in idx.get("themes", {}).items():
        if q in name.lower() or any(q in d.lower() for d in t.get("descriptions", [])):
            results.append({
                "name": name,
                "count": t.get("count", 0),
                "last_seen": t.get("last_seen"),
                "descriptions": t.get("descriptions", []),
            })
    # 按 count 降序
    results.sort(key=lambda x: x["count"], reverse=True)
    return results[:limit]


def get_dream_summary():
    """获取最近 Dream 整理的简要信息"""
    idx = _load_dream_index()
    return {
        "total_dreams": idx.get("total_dreams", 0),
        "last_dream": idx.get("last_dream"),
        "top_themes": sorted(
            [
                {"name": k, "count": v.get("count", 0)}
                for k, v in idx.get("themes", {}).items()
            ],
            key=lambda x: x["count"],
            reverse=True,
        )[:5],
    }
