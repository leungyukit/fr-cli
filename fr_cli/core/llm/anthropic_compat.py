"""Anthropic 兼容格式客户端(HTTP + SSE 直连,不依赖 anthropic SDK)"""

from fr_cli.core.llm.base import BaseLLMClient


class AnthropicCompatibleClient(BaseLLMClient):
    """Anthropic 兼容格式客户端(HTTP + SSE 直连,不依赖 anthropic SDK)

    覆盖:原生 Anthropic Messages API 及任何兼容 Anthropic 协议的厂商
    (如 kimi-code-anthropic、moonshot 自定义端点等)。

    请求格式(POST /v1/messages):
      Headers: x-api-key, anthropic-version, content-type
      Body:    {model, messages, max_tokens, stream}

    流式响应(SSE):
      event: message_start
      event: content_block_start
      event: content_block_delta    → delta.text 是真正的 token
      event: content_block_stop
      event: message_delta          → 包含 usage 信息
      event: message_stop
    """
    ANTHROPIC_VERSION = "2023-06-01"
    DEFAULT_BASE_URL = "https://api.anthropic.com"

    def __init__(self, api_key: str, base_url: str = None, **kwargs):
        super().__init__(api_key, **kwargs)
        # 去掉末尾斜杠,避免拼接出 //v1/messages
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        # 兼容 Anthropic 风格的 beta header(可由 provider 配置覆盖)
        self.extra_headers = kwargs.get("extra_headers") or {}

    def _build_payload(self, model, messages, max_tokens):
        """转换 OpenAI 风格 messages → Anthropic 风格 system+messages"""
        system_parts = []
        converted = []
        for m in messages:
            role = m.get("role")
            content = m.get("content", "")
            if role == "system":
                if content:
                    system_parts.append(content)
            else:
                converted.append({"role": role, "content": content})
        payload = {
            "model": model,
            "messages": converted,
            "max_tokens": max(1, int(max_tokens)),
            "stream": True,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        return payload

    def _build_headers(self):
        return {
            "x-api-key": self.api_key,
            "anthropic-version": self.ANTHROPIC_VERSION,
            "content-type": "application/json",
            "accept": "text/event-stream",
            **self.extra_headers,
        }

    def _parse_sse(self, response, timeout):
        """逐行解析 Anthropic SSE 流,yield 与 BaseLLMClient 一致的 chunk 格式"""
        usage = None
        for raw_line in response.iter_lines():
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", errors="replace")
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data or data == "[DONE]":
                continue
            try:
                import json as _json
                evt = _json.loads(data)
            except Exception:
                continue
            evt_type = evt.get("type", "")
            if evt_type == "content_block_delta":
                delta = evt.get("delta", {}) or {}
                text = delta.get("text", "")
                if text:
                    yield {"content": text, "usage": None}
            elif evt_type == "message_delta":
                # 包含 usage 信息(input/output tokens)
                u = evt.get("usage")
                if u:
                    usage = {
                        "input_tokens": u.get("input_tokens"),
                        "output_tokens": u.get("output_tokens"),
                    }
            elif evt_type == "message_stop":
                # 流结束,最后带上 usage
                yield {"content": "", "usage": usage}
                return
            elif evt_type == "error":
                err = evt.get("error", {}) or {}
                msg = err.get("message", "Anthropic API error")
                raise RuntimeError(f"Anthropic API error: {msg}")

    def stream_chat(self, model, messages, max_tokens=4096, timeout=None):
        import requests
        url = f"{self.base_url}/v1/messages"
        payload = self._build_payload(model, messages, max_tokens)
        headers = self._build_headers()
        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                stream=True,
                timeout=timeout or self.DEFAULT_TIMEOUT,
            )
        except requests.RequestException as e:
            raise RuntimeError(f"Anthropic 请求失败: {e}") from e

        if response.status_code >= 400:
            # 读取错误响应体(可能含详细错误信息)
            try:
                err_body = response.text[:500]
            except Exception:
                err_body = "<unreadable>"
            raise RuntimeError(
                f"Anthropic API 返回 {response.status_code}: {err_body}"
            )

        return self._parse_sse(response, timeout or self.DEFAULT_TIMEOUT)
