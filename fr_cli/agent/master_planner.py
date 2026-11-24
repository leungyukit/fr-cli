"""
MasterAgent 强制规划步 mixin —— ReAct 循环的前置规划阶段

背景(用户实测反馈): ReAct 循环的"拆解"完全靠模型自觉 —— 模型这轮回复不带
tool 代码块, 循环立刻 break 把原始文本当最终答案, 静默退化成一问一答。
session.json 实证: 17 个任务里 11 个零工具调用。本 mixin 把"先规划"变成
机制: 任务型输入先让 LLM 产出 N 步结构化计划, 渲染展示后播种进 ReAct 循环
再逐步执行。

设计要点:
1. 门控是本地启发式(零 LLM 成本): 短问候/纯咨询直接答, 不给"你好"也画
   一张计划、白搭一次调用; 明确任务动词或长输入才走规划。
2. 规划调用 silent=True: 模型思维链不刷屏, 计划由 render_plan 统一渲染。
3. 解析走 core.plan.parse_plan_json 容错提取(容忍 CoT 前后文/代码块)。
4. 规划失败只打印一行提示后回退原直连 ReAct, 不阻断对话(无回归)。
"""
from fr_cli.ui.ui import DIM, RESET, YELLOW, print_styled


class MasterAgentPlannerMixin:
    """强制规划步 mixin。

    需要 MasterAgent 提供:
      - self.state(含 .client / .model_name / .lang)
      - self._build_tools_desc()(由 MasterAgentPromptMixin 提供)
      - self.session(当前任务字典, 规划结果记入其中)
    """

    # 纯咨询特征(疑问/解释请求): 命中时直接回答, 不画计划
    _CONSULT_MARKERS = (
        "如何", "怎么", "怎样", "什么是", "是什么", "为啥", "为什么",
        "吗", "呢", "能不能", "可不可以", "是否", "思路", "建议", "区别",
        "？", "?",
    )
    # 明确任务动词: 命中即强制走规划步
    _TASK_MARKERS = (
        "帮我", "请帮", "麻烦", "查找", "搜索", "查一下", "查下", "抓取",
        "爬取", "爬虫", "下载", "生成", "创建", "新建", "写入", "保存到",
        "整理", "汇总", "统计", "分析", "调研", "监控", "发布", "发送",
        "转换", "翻译", "制定", "搜一", "做一份", "写一份", "列一",
    )

    def _needs_planning(self, user_input: str) -> bool:
        """本地启发式(零 LLM 成本): 输入是否任务型, 值得先出计划。

        判定顺序(从便宜到贵):
        1. 太短(<10 字): 问候/单字命令, 直接回答;
        2. 纯咨询(疑问词/解释请求): 直接回答 —— 咨询要的是答案不是计划;
        3. 明确任务动词: 强制规划;
        4. 长文本(>=40 字)默认按任务处理(描述类需求通常较长)。

        刻意偏保守: 宁可少规划(维持原有问答体验), 不可给"你好"画计划;
        用户想强制规划时说"帮我..."即可。
        """
        text = (user_input or "").strip()
        if len(text) < 10:
            return False
        if any(m in text for m in self._CONSULT_MARKERS):
            return False
        if any(m in text for m in self._TASK_MARKERS):
            return True
        return len(text) >= 40

    def _plan_for_task(self, user_input: str, lang: str = "zh"):
        """强制规划步: 让 LLM 先输出 N 步结构化计划。

        Returns:
            规范化后的 plan dict(含 goal/steps/summary), 或 None(失败,
            调用方回退到原直连 ReAct, 不阻断对话)。
        """
        from fr_cli.core.stream import stream_cnt
        from fr_cli.core.plan.generator import parse_plan_json
        from fr_cli.core.plan.prompts import PLAN_PROMPT_EN, PLAN_PROMPT_ZH

        hint = "正在制定执行计划..." if lang == "zh" else "Planning the task..."
        # REPL 的 AI 对话跑在 patch_stdout 代理期, 裸打 DIM 只会得到
        # ?[2m...?[0m 乱码; 走 print_styled 剥色(与 plan_mode 同一出口)。
        print_styled(f"{DIM}{hint}{RESET}")

        template = PLAN_PROMPT_ZH if lang == "zh" else PLAN_PROMPT_EN
        prompt = template.format(tools=self._build_tools_desc(), user_input=user_input)
        messages = [{"role": "user", "content": prompt}]

        # silent=True: 规划过程的思维链/JSON 原文不刷屏, 展示走 render_plan
        txt, usage, _, interrupted = stream_cnt(
            self.state.client,
            self.state.model_name,
            messages,
            lang,
            custom_prefix="",
            max_tokens=2048,
            silent=True,
        )
        if interrupted or not txt:
            return None

        plan = parse_plan_json(txt)
        if not plan:
            msg = ("[!] 规划解析失败，进入直接执行模式" if lang == "zh"
                   else "[!] Plan parsing failed, falling back to direct mode")
            print_styled(f"{YELLOW}{msg}{RESET}")
            return None
        return plan
