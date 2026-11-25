"""LLM 客户端抽象基类"""
from abc import ABC, abstractmethod
from typing import Iterator, Optional


class BaseLLMClient(ABC):
    """大模型客户端抽象基类"""

    DEFAULT_TIMEOUT = 60  # 默认请求超时(秒)

    #: 是否支持原生 function calling（tools / tool_choice 参数）。
    #: v2.8.7(P0-3) 新增 —— 不支持的 provider 自动退回文本标记路径。
    SUPPORTS_TOOLS = False

    def __init__(self, api_key: str, **kwargs):
        self.api_key = api_key

    @abstractmethod
    def stream_chat(self, model: str, messages: list,
                    max_tokens: int = 4096, timeout: int = None,
                    tools: Optional[list] = None,
                    tool_choice: Optional[str] = None) -> Iterator[dict]:
        """流式对话,yield 每个 token 块

        格式: {"content": str, "usage": dict or None, "tool_calls": list | None}

        Args:
            tools: OpenAI 格式的 function schema 数组；None → 不启用原生工具调用
            tool_choice: "auto" / "none" / "required"；None → 由 provider 决定
        """
        pass

    @staticmethod
    def _yield_chunks(response) -> Iterator[dict]:
        """通用 chunk 解析生成器,供各子类复用

        兼容性:
        - 标准 OpenAI 格式:delta.content 有值
        - 火山方舟 coding endpoint (thinking/reasoning 模型如 glm-5.2/5.3、
          doubao-seed-2.x、deepseek-v4):delta.content 恒为 "",真实内容在
          delta.reasoning_content —— 火山方舟的 OpenAI 兼容实现差异
        - v2.8.7(P0-3):额外透出 delta.tool_calls（原生 function calling 的分片）

        v2.8.7(第四阶段):思考内容与答案分离
        ------------------------------------
        推理模型（stepfun step-5 / GLM thinking 系 / 火山方舟 thinking 系）会把
        **思考过程**下发到 ``delta.reasoning_content``,把**最终答案**下发到
        ``delta.content``。两者混在一起会导致「思考」被当成答案写进历史/记忆,
        并污染二次提问的上下文。

        这里保持 ``content`` 字段语义完全不变(兼容既有调用方与既有测试),
        但当正文实际取自 ``reasoning_content`` 时**追加** ``reasoning: True`` 标记,
        让上层把「思考」与「答案」分开处理（思考照常显示,但不进历史/记忆）。

        同一 delta 同时带 content 与 reasoning_content 时**以 content 为准**
        (content 才是答案),reasoning 部分丢弃 —— 实测 stepfun 边界分片
        两者只差一个标点,无语义损失。
        """
        for chunk in response:
            content = ""
            usage = None
            tool_calls = None
            is_reasoning = False
            if chunk.choices and chunk.choices[0].delta:
                delta = chunk.choices[0].delta
                raw_content = getattr(delta, "content", None)
                raw_reasoning = getattr(delta, "reasoning_content", None)
                if raw_content:
                    # 正文 —— 答案通道
                    content = raw_content
                elif raw_reasoning:
                    # 正文为空 → 这段是思考过程,打标记让上层与答案分离
                    content = raw_reasoning
                    is_reasoning = True
                else:
                    content = ""
                # 原生 function calling 的分片（provider 侧按 index 分片下发）
                raw_calls = getattr(delta, "tool_calls", None)
                if raw_calls:
                    tool_calls = list(raw_calls)
            if hasattr(chunk, 'usage') and chunk.usage:
                usage = (chunk.usage.model_dump()
                         if hasattr(chunk.usage, 'model_dump') else vars(chunk.usage))
            # 注意：reasoning / tool_calls 只在真的存在时才加进 dict ——
            # 保持既有 chunk 形状完全不变（非推理/非 function calling 场景零影响）
            payload = {"content": content, "usage": usage}
            if is_reasoning:
                payload["reasoning"] = True
            if tool_calls:
                payload["tool_calls"] = tool_calls
            yield payload
