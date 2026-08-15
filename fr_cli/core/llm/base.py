"""LLM 客户端抽象基类"""
from abc import ABC, abstractmethod
from typing import Iterator


class BaseLLMClient(ABC):
    """大模型客户端抽象基类"""

    DEFAULT_TIMEOUT = 60  # 默认请求超时(秒)

    def __init__(self, api_key: str, **kwargs):
        self.api_key = api_key

    @abstractmethod
    def stream_chat(self, model: str, messages: list,
                    max_tokens: int = 4096, timeout: int = None) -> Iterator[dict]:
        """流式对话,yield 每个 token 块

        格式: {"content": str, "usage": dict or None}
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
        """
        for chunk in response:
            content = ""
            usage = None
            if chunk.choices and chunk.choices[0].delta:
                delta = chunk.choices[0].delta
                # 优先用 content,空时 fallback 到 reasoning_content
                content = (getattr(delta, "content", None)
                           or getattr(delta, "reasoning_content", None)
                           or "")
            if hasattr(chunk, 'usage') and chunk.usage:
                usage = (chunk.usage.model_dump()
                         if hasattr(chunk.usage, 'model_dump') else vars(chunk.usage))
            yield {"content": content, "usage": usage}
