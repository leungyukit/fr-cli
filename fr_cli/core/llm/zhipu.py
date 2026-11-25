"""智谱 AI 客户端 (zhipuai SDK)"""
from typing import Iterator, Optional

from fr_cli.core.llm.base import BaseLLMClient


class ZhipuLLMClient(BaseLLMClient):
    """智谱 AI 客户端 (zhipuai SDK)"""

    #: 智谱兼容 OpenAI 协议，支持原生 function calling
    SUPPORTS_TOOLS = True

    def __init__(self, api_key: str, **kwargs):
        super().__init__(api_key, **kwargs)
        from zhipuai import ZhipuAI
        self._client = ZhipuAI(api_key=api_key)

    def stream_chat(self, model: str, messages: list,
                    max_tokens: int = 4096, timeout: int = None,
                    tools: Optional[list] = None,
                    tool_choice: Optional[str] = None) -> Iterator[dict]:
        kwargs = {}
        # 只在真正启用时才传 —— 传 None 可能被部分 SDK 版本拒绝
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice or "auto"
        response = self._client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            max_tokens=max_tokens,
            timeout=timeout or self.DEFAULT_TIMEOUT,
            **kwargs,
        )
        yield from self._yield_chunks(response)
