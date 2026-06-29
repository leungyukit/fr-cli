"""OpenAI 兼容格式客户端(DeepSeek / Kimi / Qwen / StepFun / MiniMax / Spark / 小米 MiMo)"""
from typing import Iterator

from fr_cli.core.llm.base import BaseLLMClient


class OpenAICompatibleClient(BaseLLMClient):
    """OpenAI 兼容格式客户端

    覆盖:DeepSeek / Kimi(Moonshot) / 通义千问(Qwen) / StepFun / MiniMax / 讯飞星火(Spark) / 小米 MiMo
    """

    def __init__(self, api_key: str, base_url: str = None, **kwargs):
        super().__init__(api_key, **kwargs)
        from openai import OpenAI
        if base_url:
            self._client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            self._client = OpenAI(api_key=api_key)

    def stream_chat(self, model: str, messages: list,
                    max_tokens: int = 4096, timeout: int = None) -> Iterator[dict]:
        response = self._client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            max_tokens=max_tokens,
            timeout=timeout or self.DEFAULT_TIMEOUT,
        )
        yield from self._yield_chunks(response)
