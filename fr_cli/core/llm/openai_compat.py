"""OpenAI 兼容格式客户端(DeepSeek / Kimi / Qwen / StepFun / MiniMax / Spark / 小米 MiMo)"""
from typing import Iterator, Optional

from fr_cli.core.llm.base import BaseLLMClient


class OpenAICompatibleClient(BaseLLMClient):
    """OpenAI 兼容格式客户端

    覆盖:DeepSeek / Kimi(Moonshot) / 通义千问(Qwen) / StepFun / MiniMax / 讯飞星火(Spark) / 小米 MiMo
    """

    #: OpenAI 兼容端点原生支持 function calling
    #:
    #: 注意:个别厂商的兼容实现只支持部分模型（如老模型不支持 tools）。
    #: 上层在调用失败时会自动去掉 tools 重试一次并退回文本标记路径。
    SUPPORTS_TOOLS = True

    def __init__(self, api_key: str, base_url: str = None, **kwargs):
        super().__init__(api_key, **kwargs)
        from openai import OpenAI
        if base_url:
            self._client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            self._client = OpenAI(api_key=api_key)

    def stream_chat(self, model: str, messages: list,
                    max_tokens: int = 4096, timeout: int = None,
                    tools: Optional[list] = None,
                    tool_choice: Optional[str] = None) -> Iterator[dict]:
        kwargs = {}
        # 只在真正启用时才传 —— 传 None 可能被部分兼容实现拒绝
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
