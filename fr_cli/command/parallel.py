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
from typing import List, Tuple, Optional

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


def extract_independent_calls(text: str, executor) -> List[Tuple[str, str, str]]:
    """提取可以并发的多个【调用：...】(启发式:AI 在 prompt 里说明"独立调用可并发")

    简化版:目前不启发式检测,只信任 AI 显式标注的【并行调用：...】

    Returns:
        [(tool_name, arg_str, marker), ...]
    """
    # 暂未启用启发式,保留接口
    return []


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
                    tool_name, kwargs, msgs,
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
                    results[idx] = Result.fail(f"执行异常: {e}")

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


def format_parallel_results(results: List[Result], calls: List[Tuple[str, str, str]],
                            total_time: float = 0.0) -> str:
    """格式化并发结果"""
    if not results:
        return ""

    lines = [f"⚡ 并发执行 {len(results)} 个工具 (耗时 {total_time:.2f}s):"]
    for i, ((tool_name, _, _), result) in enumerate(zip(calls, results), 1):
        if result.is_fail():
            lines.append(f"  ❌ [{i}/{len(results)}] {tool_name}: {result.error}")
        else:
            data = result.unwrap()
            preview = str(data) if data is not None else ""
            if len(preview) > 200:
                preview = preview[:197] + "..."
            preview = preview.replace("\n", " ")
            lines.append(f"  ✅ [{i}/{len(results)}] {tool_name}: {preview}")
    return "\n".join(lines)
