"""
并行工具调用 —— 独立工具并发执行

使用场景:
- AI 一次性输出多个【调用：...】标记,且这些调用之间没有依赖
- 例如同时搜索 3 个关键词、读 5 个文件、调用 3 个 API
- 并发执行比串行快 3-10 倍

设计:
- 检测可并行的工具调用(通过标记前缀或显式声明)
- 用 ThreadPoolExecutor 并发执行
- 收集结果后按原顺序返回
- 失败隔离:一个工具失败不影响其他
- 共享跳过安全确认:要么都确认,要么都不确认

格式:
- 标准【调用：...】串行执行(默认,安全)
- 【并行调用：tool1({...}),tool2({...})】—— 显式并发
- 或在 system prompt 中让 AI 知道多个独立调用可以并发
"""
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, List, Tuple, Optional

from fr_cli.core.result import Result


# 并发上限(避免同时跑太多)
DEFAULT_MAX_WORKERS = 5
ABSOLUTE_MAX_WORKERS = 10


def _clamp_workers(n: int) -> int:
    return max(1, min(n, ABSOLUTE_MAX_WORKERS))


def extract_parallel_calls(text: str) -> List[Tuple[str, str]]:
    """从文本提取【并行调用：...】标记

    格式:【并行调用：tool1({...}),tool2({...}),...】

    Returns:
        [(tool_name, arg_str), ...] 列表
    """
    # 找所有【并行调用：...】块
    calls = []
    i = 0
    while True:
        start = text.find('【并行调用：', i)
        if start == -1:
            break

        # 找匹配的 】 块
        bracket_depth = 0
        paren_depth = 0
        in_string = False
        escape = False
        j = start + len('【并行调用：')
        end = -1
        while j < len(text):
            ch = text[j]
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == '"':
                in_string = not in_string
            elif not in_string:
                if ch == '【':
                    bracket_depth += 1
                elif ch == '】':
                    if bracket_depth == 0:
                        end = j
                        break
                    bracket_depth -= 1
                elif ch == '(':
                    paren_depth += 1
                elif ch == ')':
                    paren_depth -= 1
            j += 1
        if end == -1:
            break

        block = text[start + len('【并行调用：'):end]
        # block 现在是 "tool1({...}),tool2({...}),..." 形式
        # 用括号深度拆分逗号
        items = _split_calls(block)
        calls.extend(items)
        i = end + 1
    return calls


def _split_calls(text: str) -> List[Tuple[str, str]]:
    """拆分 'tool1({...}),tool2({...})' 为 [(tool, args), ...]"""
    items = []
    i = 0
    n = len(text)
    while i < n:
        # 跳过空白
        while i < n and text[i] in ' \t\n,':
            i += 1
        if i >= n:
            break

        # 找 tool 名(到第一个 ( )
        paren = text.find('(', i)
        if paren == -1:
            break
        tool_name = text[i:paren].strip()
        if not tool_name:
            i = paren + 1
            continue

        # 找匹配的 )
        depth = 1
        j = paren + 1
        in_string = False
        escape = False
        while j < n and depth > 0:
            ch = text[j]
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == '"':
                in_string = not in_string
            elif not in_string:
                if ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
            j += 1
        if depth != 0:
            break
        arg_str = text[paren + 1:j - 1]
        items.append((tool_name, arg_str))
        i = j
    return items


def _isolate_msgs(msgs):
    """给每个并发线程一份**独立**的消息上下文副本。

    v2.8.7(P2-5)：并行工具此前共享同一个 ``msgs`` list ——
    任何声明了 ``needs_msgs`` 且往上下文里写东西的工具，
    都会与其他线程互相踩（append 顺序错乱、内容被覆盖）。

    这里做**两层**拷贝：列表本身 + 每条消息 dict 各拷一份 ——
    只拷列表的话，工具改 ``msgs[i]["content"]`` 仍会串到别的线程。
    非 dict 的消息项按原样保留（不可拷贝时兜底回列表浅拷贝）。
    """
    if not msgs:
        return msgs
    try:
        return [dict(m) if isinstance(m, dict) else m for m in msgs]
    except Exception:
        try:
            return list(msgs)
        except Exception:
            return msgs


class ParallelExecutor:
    """并发执行多个工具调用"""

    def __init__(self, executor, max_workers: int = DEFAULT_MAX_WORKERS):
        """
        Args:
            executor: CommandExecutor 实例
            max_workers: 最大并发数
        """
        self.executor = executor
        self.max_workers = _clamp_workers(max_workers)

    def execute_parsed(self, calls: List[Tuple[str, Any]], msgs=None,
                       skip_security: bool = False,
                       client=None, model_name=None) -> List[Result]:
        """并发执行一批**已解析**的工具调用（参数是 dict）。

        与 :meth:`execute_batch` 的区别：后者收 JSON 字符串并自己解析参数；
        **原生 function calling** 路径拿到的已经是 dict，不必再序列化一遍。

        返回的 Result 列表**按入参顺序**排列 —— 调用方要把它和 tool_calls
        一一对应回填（``role="tool"`` 消息必须与请求顺序一致）。

        Args:
            calls: ``[(tool_name, kwargs_dict), ...]``
            msgs: LLM 消息上下文（每个线程一份独立副本）
            skip_security: 跳过安全确认
            client/model_name: LLM 覆盖
        """
        if not calls:
            return []

        results: List[Optional[Result]] = [None] * len(calls)

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            future_to_idx = {}
            for idx, (tool_name, kwargs) in enumerate(calls):
                if not isinstance(kwargs, dict):
                    results[idx] = Result.fail(f"参数解析失败: {tool_name}")
                    continue
                future = pool.submit(
                    self.executor.invoke_tool,
                    tool_name, dict(kwargs), _isolate_msgs(msgs),
                    skip_security=skip_security,
                    client=client, model_name=model_name,
                )
                future_to_idx[future] = idx

            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result(timeout=120)
                except Exception as e:
                    # v2.8.7(P2-6)：保留异常类型
                    results[idx] = Result.fail(f"执行异常: {e}", error_type=type(e).__name__)

        return [r if r is not None else Result.fail("未执行") for r in results]

    def execute_batch(self, calls: List[Tuple[str, str, str]], msgs=None,
                      skip_security: bool = False,
                      client=None, model_name=None) -> Tuple[List[Result], List[str]]:
        """并发执行一批工具调用

        Args:
            calls: [(tool_name, arg_str, marker), ...]
            msgs: LLM 消息上下文
            skip_security: 跳过安全确认
            client/model_name: LLM 覆盖

        Returns:
            (results, markers) — 按输入顺序的 Result 列表 + 对应的 marker
        """
        if not calls:
            return [], []

        # 先解析所有 kwargs(JSON 解析可能在主线程做,避免并发问题)
        parsed = []
        for tool_name, arg_str, marker in calls:
            kwargs = self.executor._parse_tool_kwargs(arg_str)
            parsed.append((tool_name, kwargs, marker))

        # 并发执行
        results: List[Optional[Result]] = [None] * len(parsed)
        markers: List[str] = [p[2] for p in parsed]

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            future_to_idx = {}
            for idx, (tool_name, kwargs, _) in enumerate(parsed):
                if kwargs is None:
                    results[idx] = Result.fail(f"参数解析失败: {tool_name}\n原始: {calls[idx][1]}")
                    continue
                future = pool.submit(
                    self.executor.invoke_tool,
                    tool_name, kwargs, _isolate_msgs(msgs),
                    skip_security=skip_security,
                    client=client, model_name=model_name,
                )
                future_to_idx[future] = idx

            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    result = future.result(timeout=120)
                    results[idx] = result
                except Exception as e:
                    # v2.8.7(P2-6)：保留异常类型
                    results[idx] = Result.fail(f"执行异常: {e}", error_type=type(e).__name__)

        # 填充可能的 None(应该不会发生)
        final_results = [r if r is not None else Result.fail("未执行") for r in results]
        return final_results, markers


def remove_parallel_markers(text: str) -> Tuple[str, List[Tuple[str, str, str]]]:
    """从文本中提取并移除【并行调用：...】标记

    Returns:
        (cleaned_text, all_calls)
    """
    calls = extract_parallel_calls(text)
    if not calls:
        return text, []

    # 移除整个【并行调用：...】块
    cleaned = re.sub(r'【并行调用：.*?】', '', text, flags=re.DOTALL)
    return cleaned, [(t, a, f"【并行调用：...{a[:30]}...】") for t, a in calls]


