"""
命令执行引擎
负责解析 AI 响应中的调用标记，并调度到统一注册表执行。
"""
import re
import json
import ast
import time
from types import SimpleNamespace
from fr_cli.command.registry import get_registry
from fr_cli.addon.plugin import exec_plugin
from fr_cli.core.result import Result
from fr_cli.command.parallel import (
    ParallelExecutor, remove_parallel_markers, DEFAULT_MAX_WORKERS,
)


def _build_deps(state, client=None, model_name=None):
    """根据 AppState 动态构建依赖命名空间（每次调用实时反射，避免快照过时）

    Args:
        client: 可选的覆盖 client（如 Agent 专属模型）
        model_name: 可选的覆盖模型名
    """
    return SimpleNamespace(
        vfs=state.vfs,
        mail_c=state.mail_c,
        web_c=state.web_c,
        disk_c=state.disk_c,
        plugins=state.plugins,
        lang=state.lang,
        security=state.security,
        cfg=state.cfg,
        client=client or state.client,
        model_name=model_name or state.model_name,
        mcp=getattr(state, "mcp", None),
    )


class CommandExecutor:
    """
    命令执行器：解析 AI 回复中的调用标记，并通过注册表统一调度执行。
    直接持有 AppState，每次调用时动态构建依赖快照，彻底消除状态过时问题。

    公共接口（保持向后兼容）：
      - invoke_tool(tool_name, kwargs, msgs=None, client=None, model_name=None): 结构化工具调用
      - execute(cmd_str, msgs=None, skip_security=False, client=None, model_name=None): 命令字符串调用
      - process_ai_commands(ai_response, msgs=None, client=None, model_name=None, skip_security=False): 解析并执行 AI 回复中的命令标记

    v2.4.4 行为变更：
      - 取消 `_agent_ctx_stack` 栈式 Agent 上下文覆盖（之前的并发竞态根因）
      - 改为每次调用显式传入 `client` / `model_name`（覆盖全局 default）
      - `push_agent_context` / `pop_agent_context` 仍保留为兼容接口，但实际为 no-op
        （保留调用站点不报错，新代码不要再使用）
    """

    def __init__(self, state):
        self.state = state
        self._reg = get_registry()

    # ------------------------------------------------------------------
    # Agent 上下文覆盖（v2.4.4 弃用接口，保留仅为兼容）
    # ------------------------------------------------------------------
    def push_agent_context(self, client, model_name):
        """v2.4.4 弃用：此接口现在为 no-op，client/model_name 改为显式传入 invoke_tool/execute/process_ai_commands。

        保留此接口仅为兼容旧代码（agent/executor.py / agent/workflow.py），新代码请改用
        invoke_tool(tool_name, kwargs, client=..., model_name=...) 直接传参。
        """
        # no-op：避免调用方报错，但行为不再依赖于全局栈
        return

    def pop_agent_context(self):
        """v2.4.4 弃用：no-op（与 push_agent_context 配对的占位接口）"""
        return

    def _get_deps(self, client=None, model_name=None):
        """构建依赖命名空间，client/model_name 显式覆盖（v2.4.4 取代 push/pop 栈）"""
        return _build_deps(self.state, client=client, model_name=model_name)

    # ------------------------------------------------------------------
    # 第一层：结构化工具调用
    # ------------------------------------------------------------------
    def invoke_tool(self, tool_name, kwargs, msgs=None, skip_security=False,
                    client=None, model_name=None):
        """根据工具名和结构化参数，通过注册表调度执行。返回 Result。

        Args:
            skip_security: 跳过安全确认。默认为 False（走 sec_* 检查）。
            client / model_name: v2.4.4 起，显式覆盖 LLM 上下文（取代 push_agent_context 栈）。
                传 None 时使用 AppState 默认。
        """
        # v2.7+:PreToolUse hook(可阻止/修改)
        if not skip_security:
            try:
                from fr_cli.agent.hooks import get_hook_manager
                cfg = getattr(self.state, "cfg", None)
                hook_mgr = get_hook_manager(cfg=cfg)
                pre_result = hook_mgr.run_pre_tool_use(tool_name, kwargs)
                if pre_result.blocked:
                    return Result.fail(f"工具被 hook 阻止: {pre_result.reason}")
                if pre_result.modified_args:
                    kwargs.update(pre_result.modified_args)
            except Exception:
                pass  # hook 失败不影响主流程

        data, err = self._reg.dispatch(
            self._get_deps(client=client, model_name=model_name),
            tool_name, msgs=msgs, skip_security=skip_security, **kwargs
        )

        # v2.7+:PostToolUse hook(可修改结果)
        try:
            from fr_cli.agent.hooks import get_hook_manager
            cfg = getattr(self.state, "cfg", None)
            hook_mgr = get_hook_manager(cfg=cfg)
            post_result = hook_mgr.run_post_tool_use(tool_name, kwargs, data)
            if post_result.modified_args.get("tool_result"):
                data = post_result.modified_args["tool_result"]
        except Exception:
            pass

        return Result.ok(data) if err is None else Result.fail(err)

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

    # ------------------------------------------------------------------
    # 第二层：传统命令解析（用户输入 / 插件调用）
    # ------------------------------------------------------------------
    def execute(self, cmd_str, msgs=None, skip_security=False, client=None, model_name=None):
        """执行单个命令并返回 Result。
        已分词检查插件后，直接通过注册表内部接口调度，避免重复 split。

        Args:
            skip_security: 跳过 sec_* 确认。
                - 用户在 REPL 输入 /cmd 时为 False（保留安全确认语义）
                - AI 通过【命令：...】触发时为 False（v2.4.4 修复：AI 命令串也走 sec_*）
                - 内部已确认过的批量调度可显式传 True
            client / model_name: v2.4.4 起，显式覆盖 LLM 上下文。
        """
        parts = cmd_str.strip().split()
        if not parts:
            return Result.fail("Empty command")
        cmd = parts[0].lstrip("/")
        # 插件命令优先直接处理（保持 mock 路径兼容）
        if cmd in self.state.plugins:
            p_args = ' '.join(parts[1:]) if len(parts) > 1 else ""
            exec_plugin(cmd, self.state.plugins[cmd], p_args, self.state.lang)
            return Result.ok(f"Plugin {cmd} executed")
        # 其余命令通过注册表内部接口直接调度，避免 dispatch_cmd 再次 split
        data, err = self._reg._dispatch_cmd_parts(
            self._get_deps(client=client, model_name=model_name),
            parts, msgs=msgs, skip_security=skip_security
        )
        return Result.ok(data) if err is None else Result.fail(err)

    # ------------------------------------------------------------------
    # 第三层：AI 回复解析
    # ------------------------------------------------------------------
    def _loose_parse_kwargs(self, arg_str):
        """宽松解析 JSON 参数字符串（回退方案）"""
        key_pattern = r'"(\w+)"\s*:\s*'
        keys = list(re.finditer(key_pattern, arg_str))
        if not keys:
            return None
        result = {}
        for i, m in enumerate(keys):
            key = m.group(1)
            start = m.end()
            if i + 1 < len(keys):
                end = keys[i + 1].start()
            else:
                end = len(arg_str)
                while end > 0 and arg_str[end - 1] in ' \t\n\r}':
                    end -= 1
            val_str = arg_str[start:end].strip().rstrip(',').strip()

            # 布尔值
            if val_str == 'true':
                result[key] = True
                continue
            if val_str == 'false':
                result[key] = False
                continue
            if val_str == 'null':
                result[key] = None
                continue
            # 数字
            try:
                if '.' in val_str:
                    result[key] = float(val_str)
                else:
                    result[key] = int(val_str)
                continue
            except ValueError:
                pass
            # 字符串（去掉两端引号）
            if val_str.startswith('"') and val_str.endswith('"'):
                val_str = val_str[1:-1]
            # 还原转义序列
            QUOTE_PH = '\x00Q\x00'
            val_str = val_str.replace('\\"', QUOTE_PH)
            val_str = val_str.replace('\\\\', '\\')
            val_str = val_str.replace('\\n', '\n')
            val_str = val_str.replace('\\t', '\t')
            val_str = val_str.replace('\\r', '\r')
            val_str = val_str.replace(QUOTE_PH, '"')
            result[key] = val_str
        return result

    def _parse_tool_kwargs(self, arg_str):
        """安全解析工具参数字符串（JSON 或 Python dict）"""
        arg_str = arg_str.strip()
        if not arg_str:
            return {}

        # 预处理：将 JSON 字符串值内的原始换行替换为 \n 转义序列
        fixed = ""
        in_string = False
        escape = False
        for ch in arg_str:
            if escape:
                fixed += ch
                escape = False
                continue
            if ch == '\\':
                fixed += ch
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                fixed += ch
                continue
            if ch in '\n\r' and in_string:
                fixed += '\\n'
                continue
            fixed += ch

        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            try:
                return ast.literal_eval(arg_str)
            except (ValueError, SyntaxError):
                return self._loose_parse_kwargs(arg_str)

    def _extract_tool_calls(self, text):
        """从文本中提取所有【调用：tool_name({...})】标记（支持嵌套括号，忽略字符串内的括号）"""
        calls = []
        i = 0
        while True:
            start = text.find('【调用：', i)
            if start == -1:
                break
            paren = text.find('(', start)
            if paren == -1:
                break
            tool_name = text[start + 4:paren].strip()
            depth = 1
            j = paren + 1
            in_string = False
            escape = False
            while j < len(text) and depth > 0:
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
                i = paren + 1
                continue
            arg_str = text[paren + 1:j - 1]
            end = text.find('】', j - 1)
            if end == -1:
                break
            marker = text[start:end + 1]
            calls.append((tool_name, arg_str, marker))
            i = end + 1
        return calls

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
                if res.is_fail():
                    results.append(f"❌ 并行工具调用失败: {tool_name}\n   {res.error}")
                else:
                    r = str(res.unwrap()) if res.unwrap() is not None else ""
                    if len(r) > 5000:
                        r = r[:5000] + f"\n   ... (结果共 {len(r)} 字符，已截断)"
                    results.append(f"✅ 并行工具调用成功: {tool_name}\n   结果: {r}")

            # 移除【并行调用：...】标记
            ai_response = parallel_text
            markers_to_remove.extend(par_markers)

        # ===== 格式1：【调用：...】 =====
        for tool_name, arg_str, marker in self._extract_tool_calls(ai_response):
            kwargs = self._parse_tool_kwargs(arg_str)
            if kwargs is None:
                results.append(f"❌ 参数解析失败: {tool_name}\n   原始参数: {arg_str}")
                markers_to_remove.append(marker)
                continue
            invoke_result = self.invoke_tool(
                tool_name, kwargs, msgs,
                skip_security=skip_security,
                client=client, model_name=model_name,
            )
            if invoke_result.is_fail():
                results.append(f"❌ 工具调用失败: {tool_name}\n   {invoke_result.error}")
            else:
                r = str(invoke_result.unwrap()) if invoke_result.unwrap() is not None else ""
                if len(r) > 5000:
                    r = r[:5000] + f"\n   ... (结果共 {len(r)} 字符，已截断)"
                results.append(f"✅ 工具调用成功: {tool_name}\n   结果: {r}")
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
            if exec_result.is_fail():
                results.append(f"❌ 命令执行失败: {cmd_str}\n   {exec_result.error}")
            else:
                r = str(exec_result.unwrap()) if exec_result.unwrap() is not None else ""
                if len(r) > 5000:
                    r = r[:5000] + f"\n   ... (结果共 {len(r)} 字符，已截断)"
                results.append(f"✅ 命令执行成功: {cmd_str}\n   结果: {r}")
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
            if exec_result.is_fail():
                results.append(f"❌ 命令执行失败: {cmd_str}\n   {exec_result.error}")
            else:
                r = str(exec_result.unwrap()) if exec_result.unwrap() is not None else ""
                if len(r) > 5000:
                    r = r[:5000] + f"\n   ... (结果共 {len(r)} 字符，已截断)"
                results.append(f"✅ 命令执行成功: {cmd_str}\n   结果: {r}")
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
            if exec_result.is_fail():
                results.append(f"❌ 命令执行失败: {cmd_str}\n   {exec_result.error}")
            else:
                r = str(exec_result.unwrap()) if exec_result.unwrap() is not None else ""
                if len(r) > 5000:
                    r = r[:5000] + f"\n   ... (结果共 {len(r)} 字符，已截断)"
                results.append(f"✅ 命令执行成功: {cmd_str}\n   结果: {r}")
            markers_to_remove.append(m.group(0))
            markers_to_remove_spans.append(m_span)

        # 清理回复文本：移除命令标记后，仅压缩因移除标记产生的连续多余空行，并去除首尾空白
        clean_response = ai_response
        for marker in markers_to_remove:
            clean_response = clean_response.replace(marker, "")
        clean_response = re.sub(r'\n\s*\n\s*\n+', '\n\n', clean_response).strip()

        return clean_response, results
