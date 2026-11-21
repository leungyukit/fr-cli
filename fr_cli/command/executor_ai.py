"""
CommandExecutor AI 响应解析 mixin —— peek / process_ai_commands

从 fr_cli.command.executor 拆出(原文件 509 行)。
第三层:解析 AI 回复中的调用标记并执行,支持 4 种格式:
  0.【并行调用：...】      (v2.8+ 并发执行)
  1.【调用：tool({...})】   (结构化调用)
  2.【命令：/cmd args】     (插件 / 兼容命令)
  3.file_operations/xxx    (兼容旧模型输出)

同时提供 peek_ai_commands(dry-run 预览,防提示词注入)。
_fmt_tool_result 是原来散落 5 处的结果格式化逻辑(含 5000 字符截断)。
"""
from __future__ import annotations

import re
import time

from fr_cli.command.parallel import (
    ParallelExecutor, remove_parallel_markers, DEFAULT_MAX_WORKERS,
)
from fr_cli.core.result import Result

# 工具结果最大注入上下文的字符数(超出截断)
_RESULT_MAX_CHARS = 5000


def _fmt_tool_result(label: str, name: str, res: Result) -> str:
    """统一格式化单个工具/命令执行结果(带超长截断)

    Args:
        label: 类别名,如 "工具调用" / "命令执行" / "并行工具调用"
        name: 工具名或命令串
        res: Result 实例
    """
    if res.is_fail():
        return f"[x] {label}失败: {name}\n   {res.error}"
    r = str(res.unwrap()) if res.unwrap() is not None else ""
    if len(r) > _RESULT_MAX_CHARS:
        # 注意:len(r) 在赋值完成前仍是原始长度,截断提示里的字符数是准确的
        r = r[:_RESULT_MAX_CHARS] + f"\n   ... (结果共 {len(r)} 字符，已截断)"
    return f"[OK] {label}成功: {name}\n   结果: {r}"


class CommandAIMixin:
    """AI 回复解析与执行"""

    def peek_ai_commands(self, ai_response):
        """Dry-run：解析 AI 响应中所有调用标记，返回人类可读的描述列表（不执行）。

        用于在执行前让用户先看到 AI 想做什么（尤其适用于 ! shell | prompt 这类
        半可信上下文的递归 LLM 调用），避免提示词注入触发破坏性操作。

        Returns:
            list[str]: 每个元素形如 "tool_name 关键参数摘要"，为空列表表示无命令。
        """
        descriptions = []

        # 格式 1：【调用：...】
        for tool_name, arg_str, _marker in self._extract_tool_calls(ai_response):
            kwargs = self._parse_tool_kwargs(arg_str)
            if kwargs is None:
                descriptions.append(f"{tool_name} (参数解析失败)")
                continue
            # 高亮关键参数
            key_params = []
            for k in ("path", "url", "query", "to", "name", "prompt", "command", "subject"):
                if k in kwargs and kwargs[k]:
                    val = str(kwargs[k])
                    if len(val) > 50:
                        val = val[:47] + "..."
                    key_params.append(f"{k}={val}")
            extra = "  ".join(key_params) if key_params else str(arg_str)[:50]
            descriptions.append(f"{tool_name}({extra})")

        # 格式 2：【命令：...】
        for m in re.finditer(r'【命令：(.*?)】', ai_response):
            descriptions.append(f"/{m.group(1).strip()[:80]}")

        # 格式 3：file_operations/xxx
        for m in re.finditer(r'file_operations\s*/(\w+)\s+(\S+)', ai_response):
            descriptions.append(f"/{m.group(1)} {m.group(2)[:60]}")

        return descriptions

    def process_ai_commands(self, ai_response, msgs=None, skip_security=False,
                            client=None, model_name=None):
        """
        解析AI响应中的调用标记并自动执行
        支持三种格式：
          1. 【调用：tool_name({"参数": "值"})】（结构化调用）
          2. 【命令：/command args】（插件 / 兼容命令）
          3. file_operations/xxx（兼容旧模型输出）
        返回 (clean_response, cmd_results)

        Args:
            skip_security: 跳过安全确认。默认 False（会走 sec_* 检查）。
                调用方在已经做过人工确认后传 True。
            client / model_name: v2.4.4 起，显式覆盖 LLM 上下文（Agent 专属模型）
                —— 取代旧版 push_agent_context/pop_agent_context 栈。
        """
        results = []
        markers_to_remove = []
        # 记录已覆盖的 span，用于格式 3 中 plain 模式去重 quoted 模式已匹配的文本
        markers_to_remove_spans = []

        # ===== 格式0：【并行调用：...】(v2.8+ 并发执行) =====
        parallel_text, parallel_calls = remove_parallel_markers(ai_response)
        if parallel_calls:
            # 并行模式要求 skip_security=True(并发场景通常已人工确认过)
            parallel_skip = skip_security
            par_exec = ParallelExecutor(self, max_workers=DEFAULT_MAX_WORKERS)
            t0 = time.time()
            par_results, par_markers = par_exec.execute_batch(
                [(t, a, m) for t, a, m in parallel_calls],
                msgs=msgs, skip_security=parallel_skip,
                client=client, model_name=model_name,
            )
            _ = time.time() - t0  # 耗时统计,保留备用

            for (tool_name, _, _), res in zip(parallel_calls, par_results):
                results.append(_fmt_tool_result("并行工具调用", tool_name, res))

            # 移除【并行调用：...】标记
            ai_response = parallel_text
            markers_to_remove.extend(par_markers)

        # ===== 格式1：【调用：...】 =====
        for tool_name, arg_str, marker in self._extract_tool_calls(ai_response):
            kwargs = self._parse_tool_kwargs(arg_str)
            if kwargs is None:
                results.append(f"[x] 参数解析失败: {tool_name}\n   原始参数: {arg_str}")
                markers_to_remove.append(marker)
                continue
            invoke_result = self.invoke_tool(
                tool_name, kwargs, msgs,
                skip_security=skip_security,
                client=client, model_name=model_name,
            )
            results.append(_fmt_tool_result("工具调用", tool_name, invoke_result))
            markers_to_remove.append(marker)

        # ===== 格式2：【命令：...】 =====
        pattern_cmd = r'【命令：(.*?)】'
        for m in re.finditer(pattern_cmd, ai_response):
            cmd_str = m.group(1).strip()
            marker = m.group(0)
            # v2.4.4 行为变更：AI 命令串也走 sec_* 确认（之前 skip_security=True 留下
            # prompt injection 绕过面）。与【调用：...】对齐。调用方可继续传
            # skip_security=True 跳过（如已通过 peek_ai_commands 提前让用户确认）。
            exec_result = self.execute(
                cmd_str, msgs, skip_security=skip_security,
                client=client, model_name=model_name,
            )
            results.append(_fmt_tool_result("命令执行", cmd_str, exec_result))
            markers_to_remove.append(marker)

        # ===== 格式3：file_operations/xxx（兼容） =====
        pattern2_quoted = r'file_operations\s*/(\w+)\s+(\S+)\s+"([\s\S]*?)"'
        pattern2_plain = r'file_operations\s*/(\w+)\s+(.+)$'
        for m in re.finditer(pattern2_quoted, ai_response):
            action = m.group(1)
            path = m.group(2)
            content = m.group(3)
            cmd_str = f"/{action} {path} {content}"
            exec_result = self.execute(
                cmd_str, msgs, skip_security=skip_security,
                client=client, model_name=model_name,
            )
            results.append(_fmt_tool_result("命令执行", cmd_str, exec_result))
            markers_to_remove.append(m.group(0))
            markers_to_remove_spans.append(m.span())
        for m in re.finditer(pattern2_plain, ai_response, re.MULTILINE):
            action = m.group(1)
            args = m.group(2).strip()
            if args.startswith('"') and args.endswith('"'):
                args = args[1:-1]
            # 用 span 判定是否已被前面的 quoted 模式覆盖，避免重复执行
            m_span = m.span()
            already = any(
                (mk_span[0] <= m_span[0] and mk_span[1] >= m_span[1])
                for mk_span in markers_to_remove_spans
            )
            if already:
                continue
            cmd_str = f"/{action} {args}"
            exec_result = self.execute(
                cmd_str, msgs, skip_security=skip_security,
                client=client, model_name=model_name,
            )
            results.append(_fmt_tool_result("命令执行", cmd_str, exec_result))
            markers_to_remove.append(m.group(0))
            markers_to_remove_spans.append(m_span)

        # 清理回复文本：移除命令标记后，仅压缩因移除标记产生的连续多余空行，并去除首尾空白
        clean_response = ai_response
        for marker in markers_to_remove:
            clean_response = clean_response.replace(marker, "")
        clean_response = re.sub(r'\n\s*\n\s*\n+', '\n\n', clean_response).strip()

        return clean_response, results
