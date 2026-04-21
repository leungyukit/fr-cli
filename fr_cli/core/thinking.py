"""
思维引擎 —— 造化推演
支持 CoT（思维链）、ToT（思维树）、ReAct（推理+行动）三种思维模式。
在最终回答前，让大模型按照人类思维范式进行问题拆解和自我反馈验证。
"""

COT_PROMPT_ZH = """你是一个深度思考专家。用户提出了以下问题，请严格按照以下步骤进行完整的思维推演：

步骤1 — 问题拆解：将用户问题分解为若干个独立的子问题，明确每个子问题的核心诉求。
步骤2 — 信息评估：列出已知信息、缺失信息、以及可能需要验证的假设。
步骤3 — 路径探索：针对每个子问题，提出至少两种解决思路，并简要说明各自的优劣。
步骤4 — 方案筛选：综合评估后，选择最优解决路径，并说明选择理由。
步骤5 — 自我验证：以批判者视角审视你的推理链，检查是否存在逻辑漏洞、过度推断或遗漏的边界情况。
步骤6 — 风险兜底：如果最优方案失败，备选方案是什么？

要求：
- 每个步骤必须独立成段，标题明确
- 推理要具体、可执行，不要空洞的概括
- 最后用一个简短的"结论摘要"总结核心思路

用户问题：{question}

请开始深度思考："""

COT_PROMPT_EN = """You are a deep-thinking expert. The user has asked the following question. Please conduct a complete chain-of-thought reasoning strictly following these steps:

Step 1 — Problem Decomposition: Break the user's question into independent sub-problems, clarifying the core need of each.
Step 2 — Information Assessment: List known facts, missing information, and assumptions that need verification.
Step 3 — Path Exploration: For each sub-problem, propose at least two solution approaches with brief pros/cons.
Step 4 — Solution Selection: Choose the optimal path with justification.
Step 5 — Self-Verification: Review your reasoning chain critically for logical gaps, over-inference, or overlooked edge cases.
Step 6 — Risk Mitigation: If the optimal solution fails, what is the fallback plan?

Requirements:
- Each step must be a separate paragraph with a clear heading
- Reasoning must be concrete and actionable, not vague summaries
- End with a brief "Conclusion Summary"

User Question: {question}

Begin deep thinking:"""

TOT_PROMPT_ZH = """你是一个战略思维专家。请使用思维树（Tree of Thought）方法对用户问题进行系统性分析。

思维树构建规则：
1. 【根节点】提炼问题的核心目标（用一句话概括）
2. 【第一层分支】生成至少3个不同的解决策略（标注为 策略A、策略B、策略C）
3. 【第二层分支】对每个策略进行至少两层深入展开（子策略/具体步骤）
4. 【节点评估】对每个叶子节点从以下维度评分（1-5分）：
   - 可行性（技术/资源是否允许）
   - 准确性（是否能真正解决问题）
   - 效率（时间/成本开销）
5. 【路径选择】选择总分最高的完整路径作为最优方案
6. 【反向验证】假设最优路径因某个节点失败而中断，从该节点的父节点出发，选择次优分支作为备选
7. 【收敛总结】用一句话总结最终推荐的行动方案

要求：
- 以树状层级格式输出（使用缩进或 ├── 符号）
- 评分必须给出具体理由，不能只有数字
- 最后明确标注"推荐方案"和"备选方案"

用户问题：{question}

请构建思维树："""

TOT_PROMPT_EN = """You are a strategic thinking expert. Please conduct a systematic analysis of the user's question using the Tree of Thought methodology.

Tree Construction Rules:
1. [Root Node] Distill the core objective in one sentence
2. [Level-1 Branches] Generate at least 3 distinct strategies (labeled Strategy A, B, C)
3. [Level-2 Branches] Expand each strategy at least two levels deep (sub-strategies / concrete steps)
4. [Node Evaluation] Score each leaf node on (1-5):
   - Feasibility (technical/resource constraints)
   - Accuracy (does it truly solve the problem)
   - Efficiency (time/cost overhead)
5. [Path Selection] Choose the highest-scoring complete path as optimal
6. [Backtracking] If the optimal path fails at any node, select the next-best branch from the parent node as fallback
7. [Convergence] Summarize the final recommended action in one sentence

Requirements:
- Output in tree hierarchy format (use indentation or ├── symbols)
- Scores must include rationale, not just numbers
- Clearly label "Recommended Plan" and "Fallback Plan"

User Question: {question}

Construct the thought tree:"""

REACT_SYSTEM_ENHANCEMENT_ZH = """

---
【ReAct 推演模式已激活】
在回答用户问题时，请严格遵循 ReAct（Reasoning + Acting）范式：

1. Thought（观察与思考）：
   - 先观察用户问题的核心诉求
   - 明确当前已掌握的信息和缺失的信息
   - 思考下一步应该采取什么行动来获取信息或解决问题
   - 每轮思考后进行自我检查："我的推理是否存在漏洞？"

2. Action（行动）：
   - 如果需要调用工具，使用标准格式：【调用：tool_name({"参数": "值"})】
   - 如果信息足够，直接给出答案
   - 如果信息不足，明确说明需要什么额外信息

3. Observation（观察结果）：
   - 工具执行结果会自动反馈给你
   - 基于新信息更新你的思考

4. Final Answer（最终答案）：
   - 只有当所有子问题都解决、所有验证都通过后，才给出最终答案
   - 最终答案前必须包含一行："✅ 验证通过，以下是最终结论："

重要：
- 不要在 Thought 中编造不存在的信息
- 每个 Action 后等待 Observation 再继续
- 如果某个路径失败，必须回溯并尝试替代方案
"""

REACT_SYSTEM_ENHANCEMENT_EN = """

---
[ReAct Mode Activated]
When answering the user's question, strictly follow the ReAct (Reasoning + Acting) paradigm:

1. Thought (Observation & Reasoning):
   - Observe the core intent of the user's question
   - Identify what information is known and what is missing
   - Decide the next action to acquire information or solve the problem
   - After each round of reasoning, self-check: "Does my reasoning have any flaws?"

2. Action:
   - If a tool is needed, use the standard format: 【调用：tool_name({"param": "value"})】
   - If information is sufficient, provide the answer directly
   - If information is insufficient, clearly state what additional info is needed

3. Observation:
   - Tool execution results will be fed back to you automatically
   - Update your reasoning based on new information

4. Final Answer:
   - Only provide the final answer after all sub-problems are resolved and all checks pass
   - Must include a line before the final answer: "✅ Verification passed. Final conclusion:"

Important:
- Do not fabricate information in Thought
- Wait for Observation after each Action
- If a path fails, backtrack and try an alternative
"""


class ThinkingEngine:
    """思维引擎 —— 支持 CoT / ToT / ReAct / direct 四种模式"""

    MODES = ["direct", "cot", "tot", "react"]

    def __init__(self):
        pass

    @staticmethod
    def is_valid_mode(mode):
        return mode in ThinkingEngine.MODES

    def analyze(self, state, user_input, mode, intent, lang="zh"):
        """
        根据思维模式对用户问题进行预处理分析。

        Returns:
            reasoning_text (str or None): 对于 cot/tot，返回思维推演文本；
                                          对于 react，返回 system prompt 增强片段；
                                          对于 direct，返回 None。
        """
        if mode == "direct" or mode not in self.MODES:
            return None

        if mode == "cot":
            return self._run_cot(state, user_input, lang)
        elif mode == "tot":
            return self._run_tot(state, user_input, lang)
        elif mode == "react":
            return self._get_react_enhancement(lang)

    def _run_cot(self, state, user_input, lang):
        """执行思维链推演（额外一次 LLM 调用）"""
        from fr_cli.core.stream import stream_cnt

        prompt_template = COT_PROMPT_ZH if lang == "zh" else COT_PROMPT_EN
        prompt = prompt_template.format(question=user_input)
        messages = [{"role": "user", "content": prompt}]

        txt, _, _ = stream_cnt(
            state.client, state.model_name, messages, lang,
            custom_prefix="", max_tokens=2048, silent=True
        )
        return txt.strip() if txt else None

    def _run_tot(self, state, user_input, lang):
        """执行思维树推演（额外一次 LLM 调用）"""
        from fr_cli.core.stream import stream_cnt

        prompt_template = TOT_PROMPT_ZH if lang == "zh" else TOT_PROMPT_EN
        prompt = prompt_template.format(question=user_input)
        messages = [{"role": "user", "content": prompt}]

        txt, _, _ = stream_cnt(
            state.client, state.model_name, messages, lang,
            custom_prefix="", max_tokens=2048, silent=True
        )
        return txt.strip() if txt else None

    def _get_react_enhancement(self, lang):
        """获取 ReAct system prompt 增强片段（不额外调用 LLM）"""
        if lang == "zh":
            return REACT_SYSTEM_ENHANCEMENT_ZH
        return REACT_SYSTEM_ENHANCEMENT_EN
