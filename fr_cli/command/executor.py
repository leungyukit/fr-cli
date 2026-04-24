"""
命令执行引擎
负责解析 AI 响应中的调用标记，并调度到统一注册表执行。
"""
import re
import json
import ast
from types import SimpleNamespace
from fr_cli.command.registry import get_registry
from fr_cli.addon.plugin import exec_plugin


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
      - invoke_tool(tool_name, kwargs, msgs=None): 结构化工具调用
      - execute(cmd_str, msgs=None): 命令字符串调用
      - process_ai_commands(ai_response, msgs=None): 解析并执行 AI 回复中的命令标记
    """

    def __init__(self, state):
        self.state = state
        self._reg = get_registry()
        # Agent 专属模型上下文覆盖（栈结构，支持嵌套 Agent 调用）
        self._agent_ctx_stack = []

    # ------------------------------------------------------------------
    # Agent 上下文覆盖管理
    # ------------------------------------------------------------------
    def push_agent_context(self, client, model_name):
        """临时将工具调用的 LLM 上下文切换为 Agent 专属配置"""
        self._agent_ctx_stack.append((client, model_name))

    def pop_agent_context(self):
        """恢复工具调用的 LLM 上下文为全局默认"""
        if self._agent_ctx_stack:
            self._agent_ctx_stack.pop()

    def _get_deps(self):
        """构建依赖命名空间，优先使用 Agent 专属覆盖"""
        if self._agent_ctx_stack:
            client, model_name = self._agent_ctx_stack[-1]
            return _build_deps(self.state, client, model_name)
        return _build_deps(self.state)

    # ------------------------------------------------------------------
    # 第一层：结构化工具调用
    # ------------------------------------------------------------------
    def invoke_tool(self, tool_name, kwargs, msgs=None):
        """根据工具名和结构化参数，通过注册表调度执行。返回 (result, error)"""
        return self._reg.dispatch(self._get_deps(), tool_name, msgs=msgs, **kwargs)

    # ------------------------------------------------------------------
    # 第二层：传统命令解析（用户输入 / 插件调用）
    # ------------------------------------------------------------------
    def execute(self, cmd_str, msgs=None):
        """执行单个命令并返回结果 (result, error)
        已分词检查插件后，直接通过注册表内部接口调度，避免重复 split。"""
        parts = cmd_str.strip().split()
        if not parts:
            return None, "Empty command"
        cmd = parts[0].lstrip("/")
        # 插件命令优先直接处理（保持 mock 路径兼容）
        if cmd in self.state.plugins:
            p_args = ' '.join(parts[1:]) if len(parts) > 1 else ""
            exec_plugin(cmd, self.state.plugins[cmd], p_args, self.state.lang)
            return f"Plugin {cmd} executed", None
        # 其余命令通过注册表内部接口直接调度，避免 dispatch_cmd 再次 split
        return self._reg._dispatch_cmd_parts(self._get_deps(), parts, msgs=msgs)

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
        return result if result is not None else None

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

    def process_ai_commands(self, ai_response, msgs=None):
        """
        解析AI响应中的调用标记并自动执行
        支持三种格式：
          1. 【调用：tool_name({"参数": "值"})】（结构化调用）
          2. 【命令：/command args】（插件 / 兼容命令）
          3. file_operations/xxx（兼容旧模型输出）
        返回 (clean_response, cmd_results)
        """
        results = []
        markers_to_remove = []

        # ===== 格式1：【调用：...】 =====
        for tool_name, arg_str, marker in self._extract_tool_calls(ai_response):
            kwargs = self._parse_tool_kwargs(arg_str)
            if kwargs is None:
                results.append(f"❌ 参数解析失败: {tool_name}\n   原始参数: {arg_str}")
                markers_to_remove.append(marker)
                continue
            result, error = self.invoke_tool(tool_name, kwargs, msgs)
            if error:
                results.append(f"❌ 工具调用失败: {tool_name}\n   {error}")
            else:
                results.append(f"✅ 工具调用成功: {tool_name}\n   结果: {result}")
            markers_to_remove.append(marker)

        # ===== 格式2：【命令：...】 =====
        pattern_cmd = r'【命令：(.*?)】'
        for m in re.finditer(pattern_cmd, ai_response):
            cmd_str = m.group(1).strip()
            marker = m.group(0)
            result, error = self.execute(cmd_str, msgs)
            if error:
                results.append(f"❌ 命令执行失败: {cmd_str}\n   {error}")
            else:
                results.append(f"✅ 命令执行成功: {cmd_str}\n   结果: {result}")
            markers_to_remove.append(marker)

        # ===== 格式3：file_operations/xxx（兼容） =====
        pattern2_quoted = r'file_operations\s*/(\w+)\s+(\S+)\s+"([\s\S]*?)"'
        pattern2_plain = r'file_operations\s*/(\w+)\s+(.+)$'
        for m in re.finditer(pattern2_quoted, ai_response):
            action = m.group(1)
            path = m.group(2)
            content = m.group(3)
            cmd_str = f"/{action} {path} {content}"
            result, error = self.execute(cmd_str, msgs)
            if error:
                results.append(f"❌ 命令执行失败: {cmd_str}\n   {error}")
            else:
                results.append(f"✅ 命令执行成功: {cmd_str}\n   结果: {result}")
            markers_to_remove.append(m.group(0))
        for m in re.finditer(pattern2_plain, ai_response, re.MULTILINE):
            action = m.group(1)
            args = m.group(2).strip()
            if args.startswith('"') and args.endswith('"'):
                args = args[1:-1]
            already = any(m.group(0) in mk for mk in markers_to_remove)
            if already:
                continue
            cmd_str = f"/{action} {args}"
            result, error = self.execute(cmd_str, msgs)
            if error:
                results.append(f"❌ 命令执行失败: {cmd_str}\n   {error}")
            else:
                results.append(f"✅ 命令执行成功: {cmd_str}\n   结果: {result}")
            markers_to_remove.append(m.group(0))

        # 清理回复文本：移除命令标记后，仅压缩因移除标记产生的连续多余空行，并去除首尾空白
        clean_response = ai_response
        for marker in markers_to_remove:
            clean_response = clean_response.replace(marker, "")
        clean_response = re.sub(r'\n\s*\n\s*\n+', '\n\n', clean_response).strip()

        return clean_response, results
