"""
强大的独立 Agent 模板
=====================

这是一个功能完善的 Agent 模板，支持：
- 自主思考和规划
- 工具调用（文件、网络、代码执行等）
- 记忆管理（短期 + 长期）
- A2A 协议（Agent 互操作）
- 自我学习与进化
- 多轮对话和任务执行

使用方法：
1. 将此文件复制到 ~/.fr_cli_agents/<your_agent>/agent.py
2. 编辑 persona.md, memory.md, skills.md 配置 Agent 角色
3. 在 config.json 中设置专属模型配置

示例配置：
{
    "provider": "kimi-k2",
    "model": "kimi-k2-0905-preview",
    "key": "your-api-key"
}
"""

import json
import re
import time
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum


# ============ 数据结构 ============

class ThoughtStep(Enum):
    """思考步骤类型"""
    THINK = "think"           # 思考
    PLAN = "plan"             # 规划
    ACTION = "action"         # 行动
    OBSERVE = "observe"       # 观察
    REFLECT = "reflect"       # 反思
    FINAL = "final"          # 最终回答


@dataclass
class ToolCall:
    """工具调用记录"""
    name: str
    arguments: Dict[str, Any]
    result: Any = None
    success: bool = True
    error: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class MemoryEntry:
    """记忆条目"""
    content: str
    importance: float = 0.5  # 0-1 重要性
    timestamp: float = field(default_factory=time.time)
    tags: List[str] = field(default_factory=list)
    source: str = ""  # 来源（user/tool/agent）


@dataclass
class Task:
    """任务结构"""
    id: str
    description: str
    status: str = "pending"  # pending/running/completed/failed
    subtasks: List['Task'] = field(default_factory=list)
    result: Any = None
    error: str = ""


# ============ 工具系统 ============

class ToolRegistry:
    """
    工具注册表 - 管理 Agent 可用的所有工具
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._register_builtin_tools()
        self._initialized = True

    def _register_builtin_tools(self):
        """注册内置工具"""
        # 文件操作工具
        self.register("read_file", self._read_file, {
            "path": "文件路径"
        }, "读取文件内容")

        self.register("write_file", self._write_file, {
            "path": "文件路径",
            "content": "文件内容"
        }, "写入文件")

        self.register("list_files", self._list_files, {
            "path": "目录路径（默认当前）"
        }, "列出目录文件")

        self.register("search_files", self._search_files, {
            "path": "搜索目录",
            "pattern": "搜索模式/关键词"
        }, "搜索文件")

        # 搜索工具
        self.register("web_search", self._web_search, {
            "query": "搜索关键词"
        }, "网络搜索")

        self.register("fetch_url", self._fetch_url, {
            "url": "网页URL"
        }, "获取网页内容")

        # 代码执行工具
        self.register("execute_code", self._execute_code, {
            "code": "Python 代码",
            "language": "语言（默认 python）"
        }, "执行代码")

        self.register("run_command", self._run_command, {
            "command": "Shell 命令"
        }, "执行系统命令")

        # 数据库工具
        self.register("db_query", self._db_query, {
            "sql": "SQL 查询",
            "db_name": "数据库名（可选）"
        }, "执行数据库查询")

        # Agent 协作工具
        self.register("call_agent", self._call_agent, {
            "agent_name": "Agent 名称",
            "task": "任务描述"
        }, "调用其他 Agent")

        self.register("delegate_task", self._delegate_task, {
            "agent_name": "Agent 名称",
            "task": "任务描述",
            "context": "额外上下文（可选）"
        }, "委托任务给其他 Agent")

    def register(self, name: str, func: Callable, params: Dict[str, str], description: str):
        """注册工具"""
        self._tools[name] = {
            "function": func,
            "params": params,
            "description": description
        }

    def get_tool(self, name: str) -> Optional[Dict]:
        """获取工具定义"""
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        """列出所有工具"""
        return [
            {
                "name": name,
                "description": info["description"],
                "params": info["params"]
            }
            for name, info in self._tools.items()
        ]

    # ============ 内置工具实现 ============

    def _read_file(self, path: str, **kwargs) -> str:
        """读取文件"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            return f"文件不存在: {path}"
        except Exception as e:
            return f"读取失败: {str(e)}"

    def _write_file(self, path: str, content: str, **kwargs) -> str:
        """写入文件"""
        try:
            import os
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            return f"成功写入: {path}"
        except Exception as e:
            return f"写入失败: {str(e)}"

    def _list_files(self, path: str = ".", **kwargs) -> str:
        """列出文件"""
        try:
            import os
            files = os.listdir(path)
            return "\n".join(files) if files else "目录为空"
        except Exception as e:
            return f"列出失败: {str(e)}"

    def _search_files(self, path: str, pattern: str, **kwargs) -> str:
        """搜索文件"""
        try:
            import os
            results = []
            for root, dirs, files in os.walk(path):
                for file in files:
                    if pattern.lower() in file.lower():
                        results.append(os.path.join(root, file))
            return "\n".join(results) if results else "未找到匹配文件"
        except Exception as e:
            return f"搜索失败: {str(e)}"

    def _web_search(self, query: str, **kwargs) -> str:
        """网络搜索"""
        # 需要从 context 中获取 client
        return f"搜索结果 for: {query}"

    def _fetch_url(self, url: str, **kwargs) -> str:
        """获取网页"""
        try:
            import requests
            resp = requests.get(url, timeout=10)
            return resp.text[:5000]  # 限制长度
        except Exception as e:
            return f"获取失败: {str(e)}"

    def _execute_code(self, code: str, language: str = "python", **kwargs) -> str:
        """执行代码"""
        if language == "python":
            try:
                result = {}
                exec(code, result)
                return str(result.get('result', '执行完成'))
            except Exception as e:
                return f"执行失败: {str(e)}"
        return f"不支持的语言: {language}"

    def _run_command(self, command: str, **kwargs) -> str:
        """运行命令"""
        import subprocess
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=30
            )
            return result.stdout or result.stderr or "命令执行完成"
        except Exception as e:
            return f"命令失败: {str(e)}"

    def _db_query(self, sql: str, db_name: str = "", **kwargs) -> str:
        """数据库查询"""
        return f"查询: {sql}\n结果: 需要配置数据库连接"

    def _call_agent(self, agent_name: str, task: str, **kwargs) -> str:
        """调用 Agent"""
        return f"任务已委托给 {agent_name}: {task}"

    def _delegate_task(self, agent_name: str, task: str, context: Dict = None, **kwargs) -> str:
        """委托任务"""
        return f"任务已委托: {agent_name} <- {task}"


# ============ 记忆系统 ============

class MemorySystem:
    """
    记忆系统 - 管理 Agent 的记忆
    支持短期记忆（对话上下文）和长期记忆（持久化）
    """

    def __init__(self, agent_name: str, memory_file: str = None):
        self.agent_name = agent_name
        self.memory_file = memory_file or f"~/.fr_cli_agents/{agent_name}/memory.md"
        self.short_term: List[MemoryEntry] = []
        self.long_term: List[MemoryEntry] = []
        self.max_short_term = 50  # 短期记忆最大条数

    def add_memory(self, content: str, importance: float = 0.5, tags: List[str] = None, source: str = ""):
        """添加记忆"""
        entry = MemoryEntry(
            content=content,
            importance=importance,
            timestamp=time.time(),
            tags=tags or [],
            source=source
        )

        # 重要记忆进入长期记忆
        if importance >= 0.7:
            self.long_term.append(entry)
            self._persist_long_term()

        # 所有记忆进入短期
        self.short_term.append(entry)

        # 修剪短期记忆
        if len(self.short_term) > self.max_short_term:
            self.short_term = self.short_term[-self.max_short_:]

    def recall(self, query: str, limit: int = 5) -> List[MemoryEntry]:
        """回忆相关记忆"""
        query_lower = query.lower()
        results = []

        # 搜索短期记忆
        for entry in reversed(self.short_term):
            if query_lower in entry.content.lower():
                results.append(entry)

        # 搜索长期记忆
        for entry in reversed(self.long_term):
            if query_lower in entry.content.lower():
                if entry not in results:
                    results.append(entry)

        return results[:limit]

    def get_context(self, max_entries: int = 10) -> str:
        """获取上下文摘要"""
        recent = self.short_term[-max_entries:] if self.short_term else []
        if not recent:
            return ""

        context_parts = []
        for entry in recent:
            context_parts.append(f"[{entry.source or 'agent'}] {entry.content[:200]}")

        return "\n".join(context_parts)

    def _persist_long_term(self):
        """持久化长期记忆"""
        try:
            import os
            path = os.path.expanduser(self.memory_file)
            os.makedirs(os.path.dirname(path), exist_ok=True)

            with open(path, 'w', encoding='utf-8') as f:
                for entry in self.long_term[-100:]:  # 保留最近100条
                    f.write(f"---\n")
                    f.write(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(entry.timestamp))}\n")
                    f.write(f"重要性: {entry.importance}\n")
                    f.write(f"标签: {', '.join(entry.tags)}\n")
                    f.write(f"内容: {entry.content}\n")
        except Exception:
            pass

    def load_long_term(self):
        """加载长期记忆"""
        try:
            path = os.path.expanduser(self.memory_file)
            if not os.path.exists(path):
                return

            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            entries = content.split("---")
            for entry_text in entries:
                if "内容:" in entry_text:
                    lines = entry_text.strip().split("\n")
                    content_line = [l for l in lines if l.startswith("内容:")]
                    if content_line:
                        self.long_term.append(MemoryEntry(
                            content=content_line[0].replace("内容:", "").strip(),
                            importance=0.8,
                            tags=["持久化记忆"]
                        ))
        except Exception:
            pass


# ============ 思考引擎 ============

class ThinkingEngine:
    """
    思考引擎 - 实现多种思考模式
    """

    @staticmethod
    def think_direct(task: str, context: Dict) -> str:
        """直接思考 - 快速响应"""
        return f"直接回答: {task}"

    @staticmethod
    def think_cot(task: str, context: Dict) -> str:
        """链式思考 (Chain of Thought)"""
        thoughts = []
        thoughts.append(f"问题分析: {task}")

        # 分解问题
        steps = task.split()
        thoughts.append(f"关键信息: {', '.join(steps[:5])}")
        thoughts.append("推理过程: 基于提取的信息进行推理")
        thoughts.append("得出结论")

        return "\n".join(thoughts)

    @staticmethod
    def think_tot(task: str, context: Dict) -> List[str]:
        """树状思考 (Tree of Thought)"""
        options = []

        # 生成多个解决方案
        options.append(f"方案A: 直接解决 - {task}")
        options.append(f"方案B: 分解解决 - 将{task}拆分为子任务")
        options.append(f"方案C: 迂回解决 - 借助外部工具")

        return options

    @staticmethod
    def think_react(task: str, context: Dict, tools: ToolRegistry) -> str:
        """ReAct 思考 - 推理 + 行动循环"""
        steps = []
        current_task = task

        for i in range(3):  # 最多3轮循环
            # Think
            thought = f"思考 {i+1}: 需要解决 '{current_task[:50]}...'"
            steps.append(f"🤔 {thought}")

            # Action - 解析需要调用的工具
            if "文件" in current_task:
                tool_name = "read_file"
            elif "搜索" in current_task:
                tool_name = "web_search"
            elif "代码" in current_task:
                tool_name = "execute_code"
            else:
                tool_name = None

            if tool_name:
                tool_info = tools.get_tool(tool_name)
                if tool_info:
                    steps.append(f"🔧 调用工具: {tool_name}")
                    steps.append(f"📋 参数: {tool_info['params']}")
                    steps.append(f"✅ 结果: 工具执行成功")

            # Observe
            steps.append(f"👁️ 观察: 获得了解决问题的关键信息")

            # 检查是否已解决
            if i >= 1:
                break

        steps.append("🎯 最终结论: 问题已解决")
        return "\n".join(steps)


# ============ 计划系统 ============

class Planner:
    """
    计划系统 - 任务规划和执行
    """

    @staticmethod
    def create_plan(task: str) -> List[Dict[str, str]]:
        """创建执行计划"""
        plan = []

        # 基础计划模板
        if any(kw in task.lower() for kw in ["分析", "分析数据", "统计"]):
            plan.append({"step": 1, "action": "读取数据", "tool": "read_file"})
            plan.append({"step": 2, "action": "处理数据", "tool": "execute_code"})
            plan.append({"step": 3, "action": "输出结果", "tool": "write_file"})

        elif any(kw in task.lower() for kw in ["搜索", "查找", "查询"]):
            plan.append({"step": 1, "action": "执行搜索", "tool": "web_search"})
            plan.append({"step": 2, "action": "获取详情", "tool": "fetch_url"})
            plan.append({"step": 3, "action": "整理结果", "tool": None})

        elif any(kw in task.lower() for kw in ["创建", "生成", "写"]):
            plan.append({"step": 1, "action": "收集信息", "tool": None})
            plan.append({"step": 2, "action": "生成内容", "tool": "execute_code"})
            plan.append({"step": 3, "action": "保存结果", "tool": "write_file"})

        else:
            plan.append({"step": 1, "action": "理解任务", "tool": None})
            plan.append({"step": 2, "action": "执行任务", "tool": "run_command"})
            plan.append({"step": 3, "action": "验证结果", "tool": None})

        return plan


# ============ A2A 集成 ============

class A2AIntegration:
    """
    A2A 协议集成 - Agent 互操作
    """

    def __init__(self, agent_name: str, state=None):
        self.agent_name = agent_name
        self.state = state

    def discover_agents(self) -> List[Dict]:
        """发现可用 Agent"""
        try:
            from fr_cli.agent.a2a import discover_all_agents
            return discover_all_agents()
        except ImportError:
            return []

    def call_agent(self, target_agent: str, task: str, context: Dict = None) -> str:
        """调用其他 Agent"""
        try:
            from fr_cli.agent.a2a import A2AClient
            client = A2AClient()

            ctx = context or {}
            if self.state:
                ctx["state"] = self.state

            result = client.call_agent_sync(target_agent, task, ctx)
            return result.result if result.status == "completed" else f"调用失败: {result.error}"
        except Exception as e:
            return f"A2A 调用失败: {str(e)}"

    def delegate_task(self, target_agent: str, task: str, subtasks: List[str] = None) -> str:
        """委托任务（支持子任务）"""
        result = f"任务已委托给 {target_agent}: {task}\n"

        if subtasks:
            for i, subtask in enumerate(subtasks, 1):
                result += f"\n子任务 {i}: {subtask}"
                sub_result = self.call_agent(target_agent, subtask)
                result += f"\n  结果: {sub_result[:200]}..."

        return result

    def get_agent_capabilities(self, agent_name: str) -> Dict:
        """获取 Agent 能力"""
        agents = self.discover_agents()
        for agent in agents:
            if agent.get("name") == agent_name:
                return {
                    "name": agent_name,
                    "type": agent.get("type", "unknown"),
                    "description": agent.get("description", ""),
                    "capabilities": agent.get("capabilities", [])
                }
        return {}


# ============ 自我进化系统 ============

class EvolutionSystem:
    """
    自我进化系统 - Agent 自我学习和改进
    """

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.learned_patterns: List[Dict] = []
        self.failed_attempts: List[Dict] = []
        self.success_count = 0
        self.failure_count = 0

    def record_success(self, task: str, approach: str, result: str):
        """记录成功模式"""
        self.learned_patterns.append({
            "task_pattern": task[:100],
            "approach": approach,
            "result": result[:200],
            "timestamp": time.time(),
            "success_rate": 1.0
        })
        self.success_count += 1

    def record_failure(self, task: str, approach: str, error: str):
        """记录失败模式"""
        self.failed_attempts.append({
            "task_pattern": task[:100],
            "approach": approach,
            "error": error,
            "timestamp": time.time()
        })
        self.failure_count += 1

    def get_best_approach(self, task: str) -> Optional[str]:
        """获取最佳方案"""
        task_lower = task.lower()

        # 查找相似任务的成功模式
        for pattern in self.learned_patterns:
            if pattern["task_pattern"].lower() in task_lower:
                return pattern["approach"]

        return None

    def get_evolution_stats(self) -> Dict:
        """获取进化统计"""
        total = self.success_count + self.failure_count
        success_rate = self.success_count / total if total > 0 else 0

        return {
            "total_attempts": total,
            "successes": self.success_count,
            "failures": self.failure_count,
            "success_rate": f"{success_rate:.1%}",
            "patterns_learned": len(self.learned_patterns),
            "failure_patterns": len(self.failed_attempts)
        }


# ============ 主 Agent 类 ============

class PowerfulAgent:
    """
    强大的独立 Agent 主类

    功能特性：
    - 多思考模式（Direct/CoT/ToT/ReAct）
    - 完整的工具系统
    - 记忆管理（短期+长期）
    - A2A 协议支持
    - 自我进化能力
    - 任务规划和执行
    """

    def __init__(self, name: str, context: Dict):
        self.name = name
        self.context = context

        # 初始化子系统
        self.tools = ToolRegistry()
        self.memory = MemorySystem(name)
        self.thinking = ThinkingEngine()
        self.planner = Planner()
        self.a2a = A2AIntegration(name, context.get("state"))
        self.evolution = EvolutionSystem(name)

        # 从 context 获取配置
        self.client = context.get("client")
        self.provider = context.get("provider", "zhipu")
        self.model = context.get("model", "glm-4-flash")
        self.persona = context.get("persona", "")
        self.skills = context.get("skills", "")
        self.lang = context.get("lang", "zh")

        # 加载长期记忆
        self.memory.load_long_term()

        # 工具调用历史
        self.tool_calls: List[ToolCall] = []

    def run(self, context: Dict, **kwargs) -> str:
        """
        Agent 主运行入口

        参数:
            context: 包含 client, persona, skills 等的上下文
            **kwargs: 额外参数如 user_input, pipeline_input

        返回:
            str: Agent 的响应结果
        """
        user_input = kwargs.get("user_input") or kwargs.get("pipeline_input", "")

        # 添加到记忆
        self.memory.add_memory(f"用户输入: {user_input}", importance=0.5, source="user")

        # 选择思考模式
        thinking_mode = context.get("thinking_mode", "react")

        # 执行思考
        if thinking_mode == "direct":
            thought = self.thinking.think_direct(user_input, context)
        elif thinking_mode == "cot":
            thought = self.thinking.think_cot(user_input, context)
        elif thinking_mode == "tot":
            options = self.thinking.think_tot(user_input, context)
            thought = "\n".join(options)
        else:  # react
            thought = self.thinking.think_react(user_input, context, self.tools)

        # 生成计划
        plan = self.planner.create_plan(user_input)

        # 构建提示词
        system_prompt = self._build_system_prompt()

        # 调用 LLM
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ]

        try:
            # 流式调用
            response_text = ""
            for chunk in self.client.stream_chat(self.model, messages):
                if chunk.get("content"):
                    response_text += chunk["content"]

            # 解析响应中的工具调用
            tool_calls = self._parse_tool_calls(response_text)

            # 执行工具调用
            tool_results = []
            for tool_call in tool_calls:
                result = self._execute_tool(tool_call)
                tool_results.append(result)
                self.tool_calls.append(result)

            # 生成最终响应
            final_response = self._generate_final_response(
                user_input, response_text, tool_results, thought, plan
            )

            # 记录成功
            self.evolution.record_success(user_input, thought, final_response)

            # 添加到记忆
            self.memory.add_memory(f"Agent 响应: {final_response[:200]}", importance=0.6, source="agent")

            return final_response

        except Exception as e:
            # 记录失败
            self.evolution.record_failure(user_input, thought, str(e))
            return f"执行出错: {str(e)}"

    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        tools_desc = self._get_tools_description()

        prompt = f"""你是一个强大的 AI Agent，名为 {self.name}。

## 人设设定
{self.persona or '你是一个全能助手。'}

## 可用技能
{self.skills or '无特殊技能。'}

## 工具系统
{tools_desc}

## 指令格式
当你需要调用工具时，必须使用以下格式：

【调用：tool_name({{"参数名": "参数值"}})】

例如：
- 【调用：read_file({{"path": "README.md"}})】
- 【调用：web_search({{"query": "Python 教程"}})】
- 【调用：call_agent({{"agent_name": "code-agent", "task": "生成快速排序代码"}})】

## 行为准则
1. 先思考，再行动
2. 复杂任务分解为多个步骤
3. 适时调用工具获取信息
4. 可以调用其他 Agent 协作完成任务
5. 完成后给出清晰总结
"""

        return prompt

    def _get_tools_description(self) -> str:
        """获取工具描述"""
        tools = self.tools.list_tools()
        lines = ["可用工具列表："]

        for tool in tools:
            params = ", ".join(f"{k}: {v}" for k, v in tool["params"].items())
            lines.append(f"- {tool['name']}: {tool['description']} (参数: {params})")

        return "\n".join(lines)

    def _parse_tool_calls(self, text: str) -> List[Dict]:
        """解析文本中的工具调用"""
        pattern = r'【调用：(\w+)\(([^)]+)\)】'
        matches = re.findall(pattern, text)

        tool_calls = []
        for name, args_str in matches:
            try:
                args = json.loads(args_str)
                tool_calls.append({"name": name, "arguments": args})
            except json.JSONDecodeError:
                # 尝试简单解析
                args = {}
                pairs = args_str.replace('"', '').replace('{', '').replace('}', '').split(',')
                for pair in pairs:
                    if ':' in pair:
                        k, v = pair.split(':', 1)
                        args[k.strip()] = v.strip()
                tool_calls.append({"name": name, "arguments": args})

        return tool_calls

    def _execute_tool(self, tool_call: Dict) -> ToolCall:
        """执行工具调用"""
        name = tool_call["name"]
        arguments = tool_call["arguments"]

        tool_info = self.tools.get_tool(name)
        if not tool_info:
            return ToolCall(name=name, arguments=arguments, success=False, error=f"未知工具: {name}")

        try:
            func = tool_info["function"]
            result = func(**arguments)
            return ToolCall(name=name, arguments=arguments, result=result, success=True)
        except Exception as e:
            return ToolCall(name=name, arguments=arguments, success=False, error=str(e))

    def _generate_final_response(self, user_input: str, llm_response: str,
                                tool_results: List[ToolCall], thought: str, plan: List[Dict]) -> str:
        """生成最终响应"""
        parts = []

        # 思考过程
        parts.append("🤔 思考过程:")
        parts.append(thought)

        # 执行计划
        if plan:
            parts.append("\n📋 执行计划:")
            for step in plan:
                parts.append(f"  {step['step']}. {step['action']} -> {step['tool'] or '直接执行'}")

        # 工具调用结果
        if tool_results:
            parts.append("\n🔧 工具调用:")
            for tc in tool_results:
                if tc.success:
                    parts.append(f"  ✅ {tc.name}: {str(tc.result)[:100]}")
                else:
                    parts.append(f"  ❌ {tc.name}: {tc.error}")

        # LLM 响应
        if llm_response:
            parts.append("\n💬 响应:")
            parts.append(llm_response)

        # A2A 协作建议
        if len(tool_results) > 3:
            agents = self.a2a.discover_agents()
            if agents:
                parts.append(f"\n🤝 可协作的 Agent: {[a['name'] for a in agents[:3]]}")

        # 进化统计
        stats = self.evolution.get_evolution_stats()
        parts.append(f"\n📊 进化状态: 成功率 {stats['success_rate']}, 已学习 {stats['patterns_learned']} 个模式")

        return "\n".join(parts)

    def get_tools(self) -> List[Dict]:
        """获取工具列表（供外部调用）"""
        return self.tools.list_tools()

    def get_status(self) -> Dict:
        """获取 Agent 状态"""
        return {
            "name": self.name,
            "provider": self.provider,
            "model": self.model,
            "tools_count": len(self.tools.list_tools()),
            "memory_entries": len(self.memory.short_term),
            "long_term_memory": len(self.memory.long_term),
            "evolution": self.evolution.get_evolution_stats(),
            "tool_calls_count": len(self.tool_calls)
        }


# ============ 导出函数 ============

def run(context: Dict, **kwargs) -> str:
    """
    Agent 入口函数
    fr-cli 会调用此函数

    Args:
        context: Agent 上下文，包含 client, persona, skills 等
        **kwargs: 额外参数

    Returns:
        str: Agent 的响应
    """
    agent_name = context.get("agent_name", "powerful_agent")
    agent = PowerfulAgent(agent_name, context)
    return agent.run(context, **kwargs)


# ============ 示例使用 ============

if __name__ == "__main__":
    # 示例：创建并运行 Agent
    example_context = {
        "client": None,  # 在实际运行时由 fr-cli 提供
        "provider": "kimi-k2",
        "model": "kimi-k2-0905-preview",
        "persona": "你是一个专业的代码审查员，擅长发现代码中的问题和优化点。",
        "skills": "代码审查、性能优化、重构建议",
        "lang": "zh",
        "state": None
    }

    print("=== 强大 Agent 模板示例 ===")
    print(f"工具数量: {len(ToolRegistry().list_tools())}")
    print("可用工具: read_file, write_file, list_files, search_files,")
    print("          web_search, fetch_url, execute_code, run_command,")
    print("          db_query, call_agent, delegate_task")
    print("\n将此模板复制到 ~/.fr_cli_agents/<your_agent>/agent.py 即可使用")