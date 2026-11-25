"""
Agent Team —— 多 Agent 协作小组
================================

把一个用户请求**自动拆解**成多个子任务，由多个成员**并行**完成，
再由聚合器汇总成一份最终答案。

    ① 规划 Planner     LLM 读用户请求 + 成员清单 → 输出 N 个子任务（JSON）
    ② 执行 Runner      子任务并行执行（ThreadPoolExecutor + 整体 deadline）
    ③ 聚合 Aggregator  LLM 综合各成员产出 → 最终答案

成员（member）
--------------
* ``main`` —— **通用成员**：用全局 LLM 直接完成子任务。**零配置可用**，
  没有自建 Agent 也能开团队。但它是**纯文本**调用，**不调用工具**
  （不读写文件、不执行命令）—— 要干活的子任务得指派给具备工具的 Agent。
* 具体 Agent 名 —— 本地分身 / 远程 Agent / 内置 Agent（local / remote /
  spider / db / RAG / stock），由 ``fr_cli.agent.client.call_agent`` 统一分发。

开关
----
``/agent_team on`` / ``/agent_team off`` —— 写进 config.json 的
``agent_team_enabled``。开启后，普通对话（斜杠命令除外）自动走团队流程；
计划模式与 MasterAgent 主控会被团队流程接管（团队优先）。

与既有蜂群（swarm）的区别
-------------------------
``swarm_run`` 是**用户手动点名** Agent 去跑同一个任务（parallel / council /
pipeline）；Agent Team 是**自动拆解**用户请求 → 自动指派成员 → 自动聚合。
两者共用同一套"按名字调用 Agent"的底座（``agent/client.py``）。

诚实边界
--------
* 拆解与聚合各额外消耗 1 次 LLM 调用；只有 1 个子任务时跳过聚合。
* Python 无法强杀线程：超时的子任务线程会继续跑完，但不再阻塞返回。
* 总 deadline 复用 ``swarm_timeout``（默认 60 秒），成员并发上限 ``MAX_WORKERS``。
* 规划失败时**如实降级**为"单成员（main）直接做整件事"，不会编造结果。
"""
from __future__ import annotations

import concurrent.futures
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from fr_cli.core.result import Result

#: 通用成员名 —— 用全局 LLM 直接完成子任务
MAIN_MEMBER = "main"

#: 规划器最多拆几个子任务
MAX_SUBTASKS = 6

#: 团队并发上限
MAX_WORKERS = 6

#: 单个成员产出截断长度（防止超长文本把聚合 prompt 撑爆）
MAX_MEMBER_OUTPUT = 4000

#: 团队整体超时默认值（秒）；config.json 的 swarm_timeout 可覆盖
DEFAULT_TEAM_TIMEOUT = 120


# ============================================================
# 配置开关
# ============================================================


def is_team_enabled(state) -> bool:
    """团队模式是否开启（读 config.json 的 ``agent_team_enabled``）。"""
    cfg = getattr(state, "cfg", None)
    if not isinstance(cfg, dict):
        return False
    return bool(cfg.get("agent_team_enabled", False))


def set_team_enabled(state, enabled: bool) -> bool:
    """开启 / 关闭团队模式并持久化。

    Returns:
        True 表示已写入并保存；False 表示 state 没有可写的 cfg。
    """
    cfg = getattr(state, "cfg", None)
    if not isinstance(cfg, dict):
        return False
    cfg["agent_team_enabled"] = bool(enabled)
    save = getattr(state, "save_cfg", None)
    if callable(save):
        save()
    return True


def resolve_team_timeout(state, override: Any = None) -> float:
    """解析团队整体超时（秒）。

    优先级：显式入参 > config.json 的 ``swarm_timeout`` > ``DEFAULT_TEAM_TIMEOUT``。
    """
    try:
        if override is not None:
            num = float(override)
            if num > 0:
                return num
    except (TypeError, ValueError):
        pass
    cfg = getattr(state, "cfg", None)
    if isinstance(cfg, dict):
        try:
            num = float(cfg.get("swarm_timeout"))
            if num > 0:
                return num
        except (TypeError, ValueError):
            pass
    return float(DEFAULT_TEAM_TIMEOUT)


# ============================================================
# 成员发现
# ============================================================

#: 内置 Agent 的一句话说明（给规划器看）
_BUILTIN_DESC = {
    "local": "内置 —— 本地文件与命令",
    "remote": "内置 —— 远程主机操作",
    "spider": "内置 —— 智能网页爬虫",
    "db": "内置 —— 数据库查询",
    "RAG": "内置 —— 本地知识库检索",
    "stock": "内置 —— 股票行情",
}


def discover_members(state) -> List[Dict[str, str]]:
    """列出可指派的团队成员。

    Returns:
        ``[{"name": str, "kind": "main|local|remote|builtin", "desc": str}, ...]``
    """
    members: List[Dict[str, str]] = [{
        "name": MAIN_MEMBER,
        "kind": "main",
        "desc": "通用成员 —— 用全局大模型完成子任务（纯文本，不调用工具）",
    }]

    # 本地分身
    try:
        from fr_cli.agent.manager import list_agents

        for a in list_agents():
            flags = [k for k in ("persona", "memory", "skills")
                     if a.get(f"has_{k}")]
            desc = f"本地分身（{'/'.join(flags) if flags else '无设定'}）"
            members.append({"name": a["name"], "kind": "local", "desc": desc})
    except Exception:
        pass

    # 远程 Agent
    try:
        from fr_cli.agent.remote import list_remote_agents

        for name, c in (list_remote_agents() or {}).items():
            if not isinstance(c, dict):
                continue
            desc = c.get("description") or (
                f"远程 Agent @ {c.get('host')}:{c.get('port')}"
            )
            members.append({"name": name, "kind": "remote", "desc": desc})
    except Exception:
        pass

    # 内置 Agent
    try:
        from fr_cli.agent.dispatch import BUILTIN_AGENTS

        for name in BUILTIN_AGENTS:
            members.append({
                "name": name,
                "kind": "builtin",
                "desc": _BUILTIN_DESC.get(name, "内置 Agent"),
            })
    except Exception:
        pass

    return members


# ============================================================
# 规划器
# ============================================================


@dataclass
class Subtask:
    """一个可并行执行的子任务"""

    title: str
    member: str
    instruction: str


def extract_json_obj(text: str) -> Optional[dict]:
    """从模型输出里挖出 JSON 对象（容忍 ```json 围栏、前后废话）。

    Returns:
        解析出的 dict；失败返回 None。
    """
    if not text:
        return None
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json|JSON)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    # 直接尝试
    try:
        obj = json.loads(cleaned)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass

    # 退化：取第一个 { 到最后一个 } 之间的片段
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(cleaned[start:end + 1])
            return obj if isinstance(obj, dict) else None
        except Exception:
            pass
    return None


class TeamPlanner:
    """规划器 —— 把用户请求拆成可并行执行的子任务。"""

    def __init__(self, state):
        self.state = state
        #: 最近一次拆解的 token 用量（供团队执行器加总）
        self.last_usage: Dict[str, Any] = {}

    # ---- 公开入口 ----

    def plan(self, user_input: str) -> List[Subtask]:
        """拆解用户请求。

        规划失败时**如实降级**为"单成员（main）直接做整件事"，
        绝不返回空列表（空列表会让上层无从下手）。
        """
        fallback = [Subtask("主任务", MAIN_MEMBER, user_input)]

        members = discover_members(self.state)
        prompt = self._build_prompt(user_input, members)

        from fr_cli.core.llm.completion import complete_text_ex

        text, err, usage = complete_text_ex(
            getattr(self.state, "client", None),
            getattr(self.state, "model_name", None),
            [{"role": "user", "content": prompt}],
            lang=getattr(self.state, "lang", "zh"),
            provider=getattr(self.state, "provider", None),
        )
        self.last_usage = usage or {}
        if err:
            return fallback

        subtasks = self._parse(text, members)
        return subtasks or fallback

    # ---- 内部实现 ----

    def _build_prompt(self, user_input: str, members: List[Dict[str, str]]) -> str:
        """构造拆解 prompt。"""
        roster = "\n".join(f"- {m['name']}：{m['desc']}" for m in members)
        recent = self._recent_context()
        history_block = (
            f"\n## 最近对话（用于理解“那第二点呢？”这类追问）\n{recent}\n"
            if recent else ""
        )
        return (
            "你是多 Agent 团队的调度员。用户的请求需要被拆解成若干个可以**并行**执行的子任务。\n\n"
            f"## 可用成员\n{roster}\n\n"
            f"## 用户请求\n{user_input}\n"
            f"{history_block}\n"
            "## 输出要求\n"
            "只输出一个 JSON 对象，不要任何解释文字、不要 Markdown 围栏。格式：\n"
            '{"subtasks": [{"title": "子任务标题", "member": "成员名", "instruction": "交给该成员的完整指令"}]}\n\n'
            "规则：\n"
            "1. member 必须是上面清单里的名字；拿不准就填 main。\n"
            "2. 拆 2~5 个子任务；如果这个请求本来就该一个人干，就只给 1 个。\n"
            "3. 子任务之间互不依赖，可以同时跑。\n"
            "4. instruction 必须自包含 —— 成员看不到用户的原始请求，也看不到历史对话。\n"
            "5. 不要臆造成员名；也不要给 main 派需要读写文件或执行命令的活"
            "（main 只能做纯文本分析）。"
        )

    def _recent_context(self, limit: int = 4) -> str:
        """最近几轮对话 —— 规划器要靠它理解"接着上面说"这类追问。"""
        try:
            messages = (
                self.state.get_messages() if hasattr(self.state, "get_messages")
                else list(getattr(self.state, "messages", []))
            )
        except Exception:
            return ""
        turns: List[str] = []
        try:
            candidates = messages[-limit * 2:]
        except Exception:
            return ""
        for m in candidates:
            role = m.get("role")
            if role not in ("user", "assistant"):
                continue
            content = str(m.get("content", "")).strip()
            if content:
                turns.append(f"{'用户' if role == 'user' else 'AI'}：{content[:300]}")
        return "\n".join(turns)

    def _parse(self, text: str, members: List[Dict[str, str]]) -> List[Subtask]:
        """解析模型输出的子任务列表。"""
        data = extract_json_obj(text)
        if not isinstance(data, dict):
            return []

        raw = data.get("subtasks") or data.get("tasks") or []
        if not isinstance(raw, list):
            return []

        valid = {m["name"] for m in members}
        out: List[Subtask] = []
        for item in raw[:MAX_SUBTASKS]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip() or "子任务"
            member = str(item.get("member") or item.get("agent") or "").strip()
            # 指派了不存在的成员 → 退回通用成员（不编造、也不让整轮失败）
            if member not in valid:
                member = MAIN_MEMBER
            instruction = str(item.get("instruction") or item.get("task") or "").strip()
            if not instruction:
                instruction = title
            out.append(Subtask(title=title, member=member, instruction=instruction))
        return out


# ============================================================
# 团队执行器
# ============================================================


class AgentTeam:
    """团队执行器 —— 规划 → 并行执行 → 聚合。"""

    def __init__(self, state):
        self.state = state
        #: 本轮所有模型调用的 token 用量加总（拆解 + 成员 + 聚合）
        self._usage: Dict[str, Any] = {}

    # ---- 公开入口 ----

    def run(
        self,
        user_input: str,
        timeout: Any = None,
        max_workers: int = MAX_WORKERS,
        planner: Optional[TeamPlanner] = None,
    ) -> Result:
        """跑一轮团队协作。

        Returns:
            ``Result.ok({"plan": [...], "results": [...], "answer": str, "usage": {...}})``；
            整体异常时 ``Result.fail(error)``。
        """
        self._usage = {}
        try:
            timeout = resolve_team_timeout(self.state, timeout)
            planner = planner or TeamPlanner(self.state)
            subtasks = planner.plan(user_input)
            self._merge_usage(getattr(planner, "last_usage", None))
            results = self._execute(subtasks, max_workers=max_workers, timeout=timeout)
            answer = self._aggregate(user_input, results)
        except Exception as e:
            return Result.fail(f"团队协作失败: {e}", error_type=type(e).__name__)

        return Result.ok({
            "plan": [
                {"title": s.title, "member": s.member, "instruction": s.instruction}
                for s in subtasks
            ],
            "results": results,
            "answer": answer,
            "usage": dict(self._usage),
        })

    # ---- 内部实现 ----

    def _merge_usage(self, usage: Optional[Dict[str, Any]]) -> None:
        """把一次模型调用的 token 用量累加进本轮总量。"""
        if not usage:
            return
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            try:
                self._usage[key] = self._usage.get(key, 0) + int(usage.get(key, 0) or 0)
            except (TypeError, ValueError):
                pass

    def _execute(
        self,
        subtasks: List[Subtask],
        max_workers: int,
        timeout: float,
    ) -> List[Dict[str, Any]]:
        """并行执行所有子任务，支持真正的整体 deadline。

        超时语义：到点立即返回，未完成任务以"带真实子任务名的超时条目"返回
        （部分失败），不让单个子任务拖垮整个团队。

        诚实边界：Python 无法强杀线程，超时任务的线程会继续跑完，
        但不再阻塞调用方返回。
        """
        if not subtasks:
            return []
        workers = max(1, min(int(max_workers or 1), MAX_WORKERS))

        results: List[Dict[str, Any]] = []
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
        try:
            futures = {
                executor.submit(self._run_subtask, st): st for st in subtasks
            }
            done, not_done = concurrent.futures.wait(futures, timeout=timeout)
            for future in done:
                st = futures[future]
                try:
                    results.append(future.result())
                except Exception as e:
                    results.append({
                        "title": st.title,
                        "member": st.member,
                        "ok": False,
                        "output": "",
                        "error": str(e),
                    })
            for future in not_done:
                st = futures[future]
                results.append({
                    "title": st.title,
                    "member": st.member,
                    "ok": False,
                    "output": "",
                    "error": f"子任务超时（{timeout:g}秒）",
                })
        finally:
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except TypeError:  # Python 3.8 不支持 cancel_futures
                executor.shutdown(wait=False)

        # 保持原始顺序（重名子任务以首次出现的位置为准）
        order: Dict[str, int] = {}
        for idx, st in enumerate(subtasks):
            order.setdefault(st.title, idx)
        results.sort(key=lambda r: order.get(str(r.get("title")), 9999))

        # 汇总各成员的 token 用量
        for r in results:
            self._merge_usage(r.get("usage"))
        return results

    def _run_subtask(self, subtask: Subtask) -> Dict[str, Any]:
        """执行单个子任务（成员可能是 main 或具体 Agent）。"""
        usage: Dict[str, Any] = {}
        try:
            if subtask.member == MAIN_MEMBER:
                out, err, usage = self._run_main(subtask.instruction)
            else:
                out, err = self._run_agent(subtask.member, subtask.instruction)
        except Exception as e:
            out, err = "", str(e)

        return {
            "title": subtask.title,
            "member": subtask.member,
            "ok": err is None,
            "output": (out or "")[:MAX_MEMBER_OUTPUT],
            "error": err,
            "usage": usage or {},
        }

    def _run_main(self, instruction: str) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
        """通用成员 —— 用全局 LLM 完成子任务（纯文本，不调用工具）。"""
        prompt = (
            "你是团队中的一个成员，独立完成下面这个子任务。\n"
            "只输出这个子任务的产出本身，不要客套、不要提及「团队」「成员」「子任务」"
            "等内部概念。\n\n"
            f"## 子任务\n{instruction}"
        )
        from fr_cli.core.llm.completion import complete_text_ex

        return complete_text_ex(
            getattr(self.state, "client", None),
            getattr(self.state, "model_name", None),
            [{"role": "user", "content": prompt}],
            lang=getattr(self.state, "lang", "zh"),
            provider=getattr(self.state, "provider", None),
        )

    def _run_agent(self, member: str, instruction: str) -> Tuple[Optional[str], Optional[str]]:
        """具体 Agent 成员 —— 统一走 agent/client.py（本地 / 远程 / 内置）。"""
        from fr_cli.agent.client import call_agent

        res = call_agent(member, self.state, user_input=instruction)
        if res is None:
            return None, f"成员 [{member}] 未返回结果"
        if hasattr(res, "is_fail") and res.is_fail():
            return None, res.error
        return res.unwrap(), None

    def _aggregate(self, user_input: str, results: List[Dict[str, Any]]) -> str:
        """聚合各成员产出为最终答案。"""
        ok_results = [
            r for r in results if r.get("ok") and str(r.get("output") or "").strip()
        ]

        if not ok_results:
            # 全军覆没 → 如实报出每个成员的真实错误，不编造结果
            errs = "; ".join(
                f"{r.get('member')}: {r.get('error') or '无产出'}" for r in results
            )
            return f"[团队执行失败] {errs or '没有成员产出结果'}"

        # 单成员单子任务 → 不必再花一次 LLM 调用做聚合
        if len(ok_results) == 1 and len(results) == 1:
            return ok_results[0]["output"]

        parts = [
            f"### [{r['member']}] {r['title']}\n{r['output']}"
            for r in ok_results
        ]
        prompt = (
            "你是一位高效的协调者。以下是多个成员针对同一任务目标给出的各自独立结果。\n\n"
            f"任务：{user_input}\n\n"
            "各成员输出如下：\n\n"
            f"{'\n\n'.join(parts)}\n\n"
            "请综合以上所有结果，去重、补全、解决冲突，给出一份结构清晰、完整准确的最终结论。"
            "不要提及「Agent」「成员」「团队」或「汇总」等内部概念，直接给出用户可用的最终答案。"
        )

        from fr_cli.core.llm.completion import complete_text_ex

        text, err, usage = complete_text_ex(
            getattr(self.state, "client", None),
            getattr(self.state, "model_name", None),
            [{"role": "user", "content": prompt}],
            lang=getattr(self.state, "lang", "zh"),
            provider=getattr(self.state, "provider", None),
        )
        self._merge_usage(usage)
        if err:
            # 聚合器挂了 → 退回原始产出的拼接（不假装聚合成功）
            return "\n\n".join(parts)
        return text


# ============================================================
# 对话入口（由 core/chat/pipeline.py 调用）
# ============================================================


def handle_team_chat(state, u: str):
    """团队模式下的普通对话入口。

    Returns:
        **stats 字典**（与 ``core/chat/pipeline.py::_direct_chat`` 同形状）——
        调用方（``repl/queue.py`` / ``repl/actions.py``）会把它展开成
        ``prompt.update_last_stats(**stats)``，所以这里**必须**返回字典，
        返回字符串会让交互式 REPL 直接抛 TypeError。
        答案本身通过 ``state.last_reply`` 取。
    """
    from fr_cli.core.headless import is_headless
    from fr_cli.ui.output import bullet, header, info

    headless = is_headless(state)
    if not headless:
        info("团队协作中 —— 正在拆解任务…")

    started = time.monotonic()
    team = AgentTeam(state)
    result = team.run(u)

    usage: Dict[str, Any] = {}

    if result.is_fail():
        answer = f"[团队协作失败] {result.error}"
        if not headless:
            from fr_cli.ui.output import failure
            failure("团队协作失败", reason=result.error)
    else:
        payload = result.unwrap() or {}
        plan = payload.get("plan") or []
        results = payload.get("results") or []
        answer = payload.get("answer") or ""
        usage = payload.get("usage") or {}

        if not headless:
            header("任务拆解")
            bullet([f"{p.get('member')} — {p.get('title')}" for p in plan])
            failed = [r for r in results if not r.get("ok")]
            if failed:
                from fr_cli.ui.output import warning
                warning(
                    f"{len(failed)} 个成员未完成",
                    reason="; ".join(
                        f"{r.get('member')}: {r.get('error')}" for r in failed
                    ),
                )

    # 收尾：与普通对话链路一致 —— 写回历史、记忆摘要、按日期存档会话
    stats = {
        "response_time": time.monotonic() - started,
        "input_tokens": usage.get("prompt_tokens", 0) if usage else 0,
        "output_tokens": usage.get("completion_tokens", 0) if usage else 0,
        "total_tokens": usage.get("total_tokens", 0) if usage else 0,
    }
    try:
        from fr_cli.core.chat.pipeline_post import _post_process

        messages = (
            state.get_messages() if hasattr(state, "get_messages")
            else list(getattr(state, "messages", []))
        )
        messages.append({"role": "user", "content": u})
        messages.append({"role": "assistant", "content": answer})
        stats = _post_process(
            state, messages, answer, usage, stats["response_time"],
            u, getattr(state, "lang", "zh"),
        ) or stats
    except Exception:
        # 收尾失败不影响主流程 —— 答案已经拿到了
        try:
            state.messages = messages
        except Exception:
            pass

    state.last_reply = answer

    if not headless:
        print()
        print(answer)
        print()

    return stats
