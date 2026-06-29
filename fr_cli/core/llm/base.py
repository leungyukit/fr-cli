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
        """通用 chunk 解析生成器,供各子类复用"""
        for chunk in response:
            content = ""
            usage = None
            if chunk.choices and chunk.choices[0].delta:
                content = chunk.choices[0].delta.content or ""
            if hasattr(chunk, 'usage') and chunk.usage:
                usage = (chunk.usage.model_dump()
                         if hasattr(chunk.usage, 'model_dump') else vars(chunk.usage))
            yield {"content": content, "usage": usage}
